"""
main.py
Punto de entrada del servidor web. Aca vive el webhook de WhatsApp.

Flujo del webhook:
  1. Meta manda un POST cuando llega un mensaje.
  2. Validamos la firma (HMAC) para confirmar que viene de Meta.
  3. Parseamos el mensaje (texto o audio).
  4. Guardamos/buscamos el cliente, abrimos/continuamos conversacion.
  5. Guardamos el mensaje entrante.
  6. Pasamos el texto al router -> agente -> generamos respuesta.
  7. Enviamos la respuesta por WhatsApp Cloud API.
  8. Guardamos el mensaje saliente.

Para correr localmente:
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Response

from functions.whatsapp import (
    enviar_mensaje, validar_firma, parsear_mensaje_entrante
)
from functions.audio_tools import descargar_audio_whatsapp, transcribir_audio

# Importar el cerebro del bot
from agents.router.router import clasificar
from agents.producto.producto import responder as responder_producto
from agents.faq.faq import responder as responder_faq
from agents.cotizacion.cotizacion import responder as responder_cotizacion
from agents.pedido.pedido import responder as responder_pedido
from agents.derivacion.derivacion import responder as responder_derivacion

from functions.db import get_client


app = FastAPI(title="Toni", version="0.2.0")

EMPRESA_ID = int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

AGENTES = {
    "producto": responder_producto,
    "faq": responder_faq,
    "cotizacion": responder_cotizacion,
    "pedido": responder_pedido,
    "derivacion": responder_derivacion,
}


# ============ ENDPOINTS BASICOS ============
@app.get("/")
async def root():
    return {"status": "ok", "service": "Toni", "version": "0.2.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ============ WEBHOOK: VERIFICACION (GET) ============
@app.get("/webhook")
async def verificar_webhook(request: Request):
    """
    Meta hace un GET para verificar el webhook al configurarlo.
    Tenemos que devolver el hub.challenge si el verify_token coincide.
    """
    params = request.query_params
    modo = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN")

    if modo == "subscribe" and token == verify_token:
        print("[OK] Webhook verificado por Meta.")
        # Devolver el challenge como texto plano
        return Response(content=challenge, media_type="text/plain")
    else:
        print(f"[ERROR] Verificacion fallida. modo={modo} token_match={token == verify_token}")
        return Response(content="Forbidden", status_code=403)


# ============ WEBHOOK: RECIBIR MENSAJES (POST) ============
@app.post("/webhook")
async def recibir_webhook(request: Request):
    """
    Meta manda un POST cada vez que llega un mensaje.
    """
    # 1. Leer el body crudo (necesario para validar HMAC)
    body_bytes = await request.body()
    firma = request.headers.get("X-Hub-Signature-256")

    # 2. Validar firma
    if not validar_firma(body_bytes, firma):
        print("[ERROR] Firma invalida. Rechazando request.")
        return Response(content="Forbidden", status_code=403)

    # 3. Parsear el body
    import json
    try:
        body = json.loads(body_bytes)
    except Exception as e:
        print(f"[ERROR] Body no es JSON valido: {e}")
        return Response(content="Bad Request", status_code=400)

    # 4. Extraer el mensaje
    mensaje = parsear_mensaje_entrante(body)
    if not mensaje:
        # No es un mensaje procesable (puede ser un status update). Respondemos 200 igual.
        return Response(content="OK", status_code=200)

    print(f"[MSG] De {mensaje['numero']} ({mensaje.get('nombre')}): tipo={mensaje['tipo']}")

    # 5. Procesar el mensaje (en este punto respondemos 200 rapido a Meta
    #    y procesamos. Para simplificar, procesamos sincrono por ahora.)
    try:
        await procesar_mensaje(mensaje)
    except Exception as e:
        print(f"[ERROR] Procesando mensaje: {e}")
        import traceback
        traceback.print_exc()

    # 6. Siempre responder 200 a Meta (sino reintenta)
    return Response(content="OK", status_code=200)


# ============ LOGICA DE PROCESAMIENTO ============
async def procesar_mensaje(mensaje: dict):
    """
    Procesa un mensaje entrante: lo guarda, lo pasa al bot, responde.
    """
    sb = get_client()
    numero = mensaje["numero"]
    nombre = mensaje.get("nombre") or "Cliente WhatsApp"

    # ===== Obtener el texto (transcribir si es audio) =====
    texto = mensaje.get("texto")

    if mensaje["tipo"] == "audio" and mensaje.get("media_id"):
        print("[AUDIO] Descargando y transcribiendo...")
        try:
            archivo = descargar_audio_whatsapp(
                media_id=mensaje["media_id"],
                destino_local=f"/tmp/audio_{mensaje['media_id']}.ogg",
            )
            transcripcion = transcribir_audio(archivo)
            if transcripcion["exito"]:
                texto = transcripcion["texto_transcrito"]
                print(f"[AUDIO] Transcrito: {texto}")
            else:
                texto = None
        except Exception as e:
            print(f"[ERROR] Transcribiendo audio: {e}")
            texto = None

    if not texto:
        # No pudimos obtener texto. Respondemos pidiendo que escriba.
        enviar_mensaje(numero, "Perdon, no pude leer tu mensaje. Me lo escribis como texto?")
        return

    # ===== Obtener o crear cliente =====
    # Usamos la funcion fn_get_or_create_cliente que creamos en 02_clients.sql
    try:
        cliente_resp = sb.rpc("fn_get_or_create_cliente", {
            "p_empresa_id": EMPRESA_ID,
            "p_canal": "whatsapp",
            "p_identificador": numero,
            "p_nombre": nombre,
        }).execute()
        cliente_id = cliente_resp.data
    except Exception as e:
        print(f"[WARN] No pude usar fn_get_or_create_cliente: {e}. Creando manual.")
        # Fallback: crear cliente simple
        cli = sb.table("cliente").insert({
            "empresa_id": EMPRESA_ID,
            "nombre": nombre,
            "tipo": "b2c",
        }).execute().data[0]
        cliente_id = cli["id"]

    # ===== Abrir o continuar conversacion =====
    from datetime import datetime, timezone, timedelta
    hace_30 = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()

    conv_existente = (
        sb.table("conversacion")
        .select("id")
        .eq("empresa_id", EMPRESA_ID)
        .eq("cliente_id", cliente_id)
        .eq("estado", "activa")
        .gte("abierta_at", hace_30)
        .order("abierta_at", desc=True)
        .limit(1)
        .execute()
    )

    if conv_existente.data:
        conversacion_id = conv_existente.data[0]["id"]
    else:
        conv = sb.table("conversacion").insert({
            "empresa_id": EMPRESA_ID,
            "cliente_id": cliente_id,
            "canal": "whatsapp",
            "estado": "activa",
        }).execute().data[0]
        conversacion_id = conv["id"]

    # ===== Guardar mensaje entrante =====
    sb.table("mensaje").insert({
        "conversacion_id": conversacion_id,
        "emisor": "cliente",
        "contenido": texto,
        "tipo_media": "audio" if mensaje["tipo"] == "audio" else "texto",
        "whatsapp_msg_id": mensaje.get("wamid"),
    }).execute()

    # ===== Pasar al router =====
    clasificacion = clasificar(texto, contexto={"canal": "whatsapp"})
    agente_elegido = clasificacion["agente"]
    print(f"[ROUTER] Agente: {agente_elegido}")

    # ===== Invocar agente =====
    if agente_elegido == "ninguno" or agente_elegido not in AGENTES:
        respuesta_texto = "Hola! Soy Toni. En que te puedo ayudar con repuestos?"
    else:
        try:
            resultado = AGENTES[agente_elegido](
                mensaje_cliente=texto,
                contexto={"canal": "whatsapp", "cliente_id": cliente_id},
                verbose=False,
            )
            respuesta_texto = resultado["respuesta_texto"]
        except Exception as e:
            print(f"[ERROR] Agente {agente_elegido}: {e}")
            respuesta_texto = "Disculpa, tuve un problema procesando tu consulta. Podes intentar de nuevo?"

    # ===== Enviar respuesta por WhatsApp =====
    envio = enviar_mensaje(numero, respuesta_texto)
    print(f"[SENT] Respuesta enviada. wamid={envio.get('wamid')}")

    # ===== Guardar mensaje saliente =====
    sb.table("mensaje").insert({
        "conversacion_id": conversacion_id,
        "emisor": "bot",
        "agente": agente_elegido,
        "contenido": respuesta_texto,
        "tipo_media": "texto",
        "whatsapp_msg_id": envio.get("wamid"),
    }).execute()