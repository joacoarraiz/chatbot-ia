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

Ademas del webhook, corre un scheduler interno (APScheduler) que dispara
tareas periodicas (ej: aviso de derivaciones) sin depender de N8N ni de
servicios externos. Esto viaja junto con el bot al deployar a Cloud Run.

Para correr localmente:
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import os
import sys
import inspect
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Response

from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

from functions.whatsapp import (
    enviar_mensaje, validar_firma, parsear_mensaje_entrante
)
from functions.audio_tools import (
    descargar_audio_whatsapp, transcribir_audio, subir_audio_a_storage
)

# Importar el cerebro del bot
from agents.router.router import clasificar
from agents.producto.producto import responder as responder_producto
from agents.faq.faq import responder as responder_faq
from agents.cotizacion.cotizacion import responder as responder_cotizacion
from agents.pedido.pedido import responder as responder_pedido
from agents.derivacion.derivacion import responder as responder_derivacion

# Tareas periodicas (jobs del scheduler interno)
from scripts.aviso_derivacion import avisar_derivaciones_pendientes

from functions.db import get_client


app = FastAPI(title="Toni", version="0.3.2")

EMPRESA_ID = int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

AGENTES = {
    "producto": responder_producto,
    "faq": responder_faq,
    "cotizacion": responder_cotizacion,
    "pedido": responder_pedido,
    "derivacion": responder_derivacion,
}


# ============ SCHEDULER INTERNO (reemplaza N8N) ============
# El scheduler vive adentro del bot. Cuando uvicorn arranca, lo prendemos;
# cuando se apaga, lo frenamos. Asi las tareas periodicas viajan junto con
# el bot cuando deployamos a Cloud Run (un solo paquete, sin N8N externo).
scheduler = BackgroundScheduler(timezone="America/Argentina/Buenos_Aires")


def job_aviso_derivaciones():
    """Wrapper del job de avisos. El scheduler lo llama cada 2 minutos."""
    try:
        avisar_derivaciones_pendientes(verbose=True)
    except Exception as e:
        print(f"[SCHEDULER][ERROR] job_aviso_derivaciones: {e}")


@app.on_event("startup")
def iniciar_scheduler():
    """Al arrancar uvicorn: registrar los jobs y prender el scheduler."""

    # --- Job 1: aviso de derivaciones (ACTIVO) ---
    # Cada 2 minutos revisa v_derivaciones_pendientes y avisa por WhatsApp.
    scheduler.add_job(
        job_aviso_derivaciones,
        trigger="interval",
        minutes=2,
        id="aviso_derivaciones",
        replace_existing=True,
        max_instances=1,          # que no se pisen dos corridas
        coalesce=True,            # si se atrasa, junta las pendientes en una
    )

    # --- Job 2: repregunta al cliente (APAGADO A PROPOSITO) ---
    # OJO: esto le manda un mensaje al CLIENTE FINAL por iniciativa del bot.
    # Eso requiere una plantilla de WhatsApp aprobada APARTE (distinta a
    # 'aviso_derivacion') y muy probablemente pasar por App Review de Meta.
    # La plantilla 'seguimiento_consulta' ya esta EN REVISION en Meta.
    # Cuando este aprobada + salgamos del sandbox:
    #   1) crear el script scripts/repregunta_inactivos.py
    #   2) importarlo arriba
    #   3) destapar estas lineas
    #
    # scheduler.add_job(
    #     job_repregunta_inactivos,
    #     trigger="interval",
    #     minutes=60,
    #     id="repregunta_inactivos",
    #     replace_existing=True,
    #     max_instances=1,
    #     coalesce=True,
    # )

    scheduler.start()
    print("[SCHEDULER] Iniciado. Jobs activos:", [j.id for j in scheduler.get_jobs()])


@app.on_event("shutdown")
def apagar_scheduler():
    """Al apagar uvicorn: frenar el scheduler prolijamente."""
    scheduler.shutdown(wait=False)
    print("[SCHEDULER] Detenido.")


# ============ ENDPOINTS BASICOS ============
@app.get("/")
async def root():
    return {"status": "ok", "service": "Toni", "version": "0.3.2"}


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

# ============ HISTORIAL CONVERSACIONAL ============
def get_historial_para_agente(conversacion_id, limite=10, excluir_wamid=None):
    """
    Lee los ultimos mensajes de una conversacion y los formatea
    como OpenAI los espera: [{"role": "user"/"assistant", "content": ...}].
    Traduce: emisor 'bot' -> 'assistant', emisor 'cliente' -> 'user'.
    Excluye el mensaje actual (que se pasa aparte como mensaje_cliente).
    """
    sb = get_client()
    msgs = (
        sb.table("mensaje")
        .select("emisor, contenido, whatsapp_msg_id, creado_at")
        .eq("conversacion_id", conversacion_id)
        .order("creado_at", desc=False)   # cronologico: viejo -> nuevo
        .limit(limite)
        .execute()
        .data or []
    )

    historial = []
    for m in msgs:
        # No incluir el mensaje actual (ya se pasa como mensaje_cliente)
        if excluir_wamid and m.get("whatsapp_msg_id") == excluir_wamid:
            continue
        contenido = m.get("contenido")
        if not contenido:
            continue
        rol = "assistant" if m.get("emisor") == "bot" else "user"
        historial.append({"role": rol, "content": contenido})

    return historial

# ============ RESPUESTA SOCIAL (saludos, gracias, despedidas) ============
def responder_social(mensaje_cliente, historial=None):
    """
    Genera una respuesta calida para la charla social que cae en 'ninguno'
    (saludos, "como estas", "gracias", "chau"). Toni responde como un vendedor
    de mostrador argentino, breve y con voseo, y deja la puerta abierta a que
    le pidan un repuesto. Usa el historial para tener contexto de la charla.

    Si por lo que sea el LLM falla, devuelve un saludo amable por defecto
    (nunca rompe el flujo, nunca se queda sin responder).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "¡Hola! Soy Toni 👋 ¿Qué repuesto andás buscando?"

    # Modelo chico y barato alcanza para un saludo. Toma MODEL_SOCIAL si existe,
    # sino MODEL_ROUTER, sino un default razonable.
    modelo = os.environ.get("MODEL_SOCIAL") or os.environ.get("MODEL_ROUTER") or "gpt-4.1-mini"

    sistema = (
        "Sos Toni, el asistente por WhatsApp de un comercio de autopartes en Argentina. "
        "El cliente te escribio algo social (un saludo, un 'como estas', un 'gracias' o una "
        "despedida), no un pedido concreto. Responde como un vendedor de mostrador argentino: "
        "calido, breve, con voseo, natural (una o dos frases como mucho). "
        "Si es un saludo o te pregunta como estas, devolve el saludo y ofrece ayuda con repuestos. "
        "Si es una despedida, despedite con buena onda. Si te agradece, responde con gusto. "
        "Siempre deja la puerta abierta a que te pidan un repuesto, sin ser insistente ni pesado. "
        "NO inventes precios, stock, horarios ni datos del negocio. Usa como mucho un emoji."
    )

    mensajes = [{"role": "system", "content": sistema}]
    if historial:
        mensajes.extend(historial)
    mensajes.append({"role": "user", "content": mensaje_cliente})

    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=modelo,
            messages=mensajes,
            temperature=0.7,
            max_tokens=120,
        )
        texto = (resp.choices[0].message.content or "").strip()
        return texto or "¡Hola! Soy Toni 👋 ¿Qué andás buscando?"
    except Exception as e:
        print(f"[WARN] responder_social fallo: {e}")
        return "¡Hola! Soy Toni 👋 ¿Qué repuesto andás buscando?"

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

    # Guardamos aca el link al audio original (si es audio) para archivarlo
    # despues en la tabla mensaje. Arranca en None (los mensajes de texto no
    # tienen audio).
    media_url_audio = None
    archivo_audio_local = None

    if mensaje["tipo"] == "audio" and mensaje.get("media_id"):
        print("[AUDIO] Descargando y transcribiendo...")
        try:
            # Carpeta temporal del sistema: funciona igual en Windows y Linux.
            # (Antes usabamos /tmp/ fijo, que no existe en Windows.)
            carpeta_tmp = Path(tempfile.gettempdir())
            destino = carpeta_tmp / f"audio_{mensaje['media_id']}.ogg"

            archivo = descargar_audio_whatsapp(
                media_id=mensaje["media_id"],
                destino_local=destino,
            )
            archivo_audio_local = archivo  # lo usamos mas abajo para subir a Storage

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
            "p_display_name": nombre,
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

    # ===== Si era audio, archivarlo en Storage (extra, no puede romper el flujo) =====
    # Ahora que tenemos conversacion_id, subimos el audio original al bucket "media"
    # y guardamos el link. Si algo falla aca, lo registramos pero seguimos igual:
    # el bot ya tiene el texto transcrito y va a responder normal.
    if archivo_audio_local is not None:
        try:
            subida = subir_audio_a_storage(
                archivo_local=archivo_audio_local,
                conversacion_id=conversacion_id,
                empresa_id=EMPRESA_ID,
            )
            media_url_audio = subida.get("url_firmada")
            print(f"[AUDIO] Archivado en Storage: {subida.get('ruta_storage')}")
        except Exception as e:
            # No rompemos la conversacion por un fallo de archivado.
            print(f"[WARN] No pude archivar el audio en Storage: {e}")

    # ===== Guardar mensaje entrante =====
    sb.table("mensaje").insert({
        "conversacion_id": conversacion_id,
        "emisor": "cliente",
        "contenido": texto,
        "tipo_media": "audio" if mensaje["tipo"] == "audio" else "texto",
        "media_url": media_url_audio,   # link al audio original (None si fue texto)
        "whatsapp_msg_id": mensaje.get("wamid"),
    }).execute()

    # ===== Leer historial de la conversacion (memoria) =====
    historial = get_historial_para_agente(
        conversacion_id,
        limite=10,
        excluir_wamid=mensaje.get("wamid"),
    )
    if historial:
        print(f"[MEMORIA] {len(historial)} mensaje(s) de contexto cargados.")

    # ===== Pasar al router (con memoria) =====
    clasificacion = clasificar(texto, contexto={"canal": "whatsapp"}, historial=historial)
    agente_elegido = clasificacion["agente"]
    print(f"[ROUTER] Agente: {agente_elegido}")

    # ===== Invocar agente =====
    if agente_elegido == "ninguno" or agente_elegido not in AGENTES:
        # Charla social (saludo, "como estas", "gracias", "chau"): Toni responde
        # calido y con contexto, en vez de la frase fija de antes.
        respuesta_texto = responder_social(texto, historial=historial)
    else:
        try:
            agente_fn = AGENTES[agente_elegido]
            # Armar los argumentos base
            kwargs = {
                "mensaje_cliente": texto,
                "contexto": {"canal": "whatsapp", "cliente_id": cliente_id},
                "verbose": False,
            }
            # Solo pasar 'historial' si el agente lo acepta (asi no rompemos los que no lo tienen)
            params_del_agente = inspect.signature(agente_fn).parameters
            if "historial" in params_del_agente:
                kwargs["historial"] = historial

            resultado = agente_fn(**kwargs)
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