"""
main.py
Punto de entrada del servidor web. Aca vive el webhook de WhatsApp.

Flujo del webhook:
  1. Meta manda un POST cuando llega un mensaje.
  2. Validamos la firma (HMAC) para confirmar que viene de Meta.
  3. Parseamos el mensaje (texto, audio o imagen) y vemos por que numero entro.
  4. Buscamos a que comercio (empresa) corresponde ese numero.
  5. Guardamos/buscamos el cliente, abrimos/continuamos conversacion.
  6. Guardamos el mensaje entrante.
  7. Pasamos el texto al router -> agente -> generamos respuesta.
  8. Enviamos la respuesta por WhatsApp Cloud API (por la misma linea).
  9. Guardamos el mensaje saliente.

Ademas del webhook, corre un scheduler interno (APScheduler) que dispara
tareas periodicas (ej: aviso de derivaciones) sin depender de N8N ni de
servicios externos.

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
from functions.vision_tools import analizar_imagen

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


app = FastAPI(title="Toni", version="0.5.0")

# Comercio por defecto (fallback si un numero no esta mapeado en numero_whatsapp).
EMPRESA_ID_DEFAULT = int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

AGENTES = {
    "producto": responder_producto,
    "faq": responder_faq,
    "cotizacion": responder_cotizacion,
    "pedido": responder_pedido,
    "derivacion": responder_derivacion,
}


# ============ MULTI-COMERCIO: numero -> empresa ============
def resolver_empresa(phone_number_id):
    """
    Dado el numero propio por el que entro el mensaje, devuelve a que
    empresa (comercio) corresponde, mirando la tabla numero_whatsapp.

    Red de seguridad: si el numero no esta cargado (o no vino), usa el
    comercio por defecto (EMPRESA_ID_DEFAULT). Asi el bot nunca se queda
    sin comercio y no se rompe aunque falte cargar el numero.
    """
    if not phone_number_id:
        return EMPRESA_ID_DEFAULT
    try:
        sb = get_client()
        r = (
            sb.table("numero_whatsapp")
            .select("empresa_id")
            .eq("phone_number_id", phone_number_id)
            .eq("activo", True)
            .limit(1)
            .execute()
        )
        if r.data:
            return r.data[0]["empresa_id"]
    except Exception as e:
        print(f"[WARN] No pude resolver empresa por numero {phone_number_id}: {e}")
    return EMPRESA_ID_DEFAULT


# ============ SCHEDULER INTERNO (reemplaza N8N) ============
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
    scheduler.add_job(
        job_aviso_derivaciones,
        trigger="interval",
        minutes=2,
        id="aviso_derivaciones",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # --- Job 2: repregunta al cliente (APAGADO A PROPOSITO) ---
    # Requiere la plantilla 'seguimiento_consulta' aprobada + salir del sandbox.
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
    return {"status": "ok", "service": "Toni", "version": "0.5.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ============ WEBHOOK: VERIFICACION (GET) ============
@app.get("/webhook")
async def verificar_webhook(request: Request):
    params = request.query_params
    modo = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN")

    if modo == "subscribe" and token == verify_token:
        print("[OK] Webhook verificado por Meta.")
        return Response(content=challenge, media_type="text/plain")
    else:
        print(f"[ERROR] Verificacion fallida. modo={modo} token_match={token == verify_token}")
        return Response(content="Forbidden", status_code=403)


# ============ WEBHOOK: RECIBIR MENSAJES (POST) ============
@app.post("/webhook")
async def recibir_webhook(request: Request):
    body_bytes = await request.body()
    firma = request.headers.get("X-Hub-Signature-256")

    if not validar_firma(body_bytes, firma):
        print("[ERROR] Firma invalida. Rechazando request.")
        return Response(content="Forbidden", status_code=403)

    import json
    try:
        body = json.loads(body_bytes)
    except Exception as e:
        print(f"[ERROR] Body no es JSON valido: {e}")
        return Response(content="Bad Request", status_code=400)

    mensaje = parsear_mensaje_entrante(body)
    if not mensaje:
        return Response(content="OK", status_code=200)

    print(f"[MSG] De {mensaje['numero']} ({mensaje.get('nombre')}): tipo={mensaje['tipo']} linea={mensaje.get('phone_number_id')}")

    try:
        await procesar_mensaje(mensaje)
    except Exception as e:
        print(f"[ERROR] Procesando mensaje: {e}")
        import traceback
        traceback.print_exc()

    return Response(content="OK", status_code=200)


# ============ HISTORIAL CONVERSACIONAL ============
def get_historial_para_agente(conversacion_id, limite=10, excluir_wamid=None):
    """
    Lee los ultimos mensajes de una conversacion y los formatea como
    OpenAI los espera. Traduce: emisor 'bot' -> 'assistant', 'cliente' -> 'user'.
    """
    sb = get_client()
    msgs = (
        sb.table("mensaje")
        .select("emisor, contenido, whatsapp_msg_id, creado_at")
        .eq("conversacion_id", conversacion_id)
        .order("creado_at", desc=False)
        .limit(limite)
        .execute()
        .data or []
    )

    historial = []
    for m in msgs:
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
    de mostrador argentino, breve y con voseo. Usa el historial para contexto.
    Si el LLM falla, devuelve un saludo por defecto (nunca rompe el flujo).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "¡Hola! Soy Toni 👋 ¿Qué repuesto andás buscando?"

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
    Procesa un mensaje entrante: resuelve el comercio, lo guarda,
    lo pasa al bot, responde por la misma linea.
    """
    sb = get_client()
    numero = mensaje["numero"]
    nombre = mensaje.get("nombre") or "Cliente WhatsApp"

    # ===== Multi-comercio: por que linea entro y a que comercio va =====
    phone_number_id = mensaje.get("phone_number_id")
    empresa_id = resolver_empresa(phone_number_id)
    print(f"[EMPRESA] Mensaje ruteado a empresa_id={empresa_id}")

    # ===== Obtener el texto (transcribir audio / analizar imagen) =====
    texto = mensaje.get("texto")
    media_url_media = None       # link al audio o imagen original (para archivar)
    archivo_media_local = None   # archivo bajado (audio o imagen)
    tipo_media_guardar = "texto" # como se guarda en la tabla mensaje

    # --- AUDIO ---
    if mensaje["tipo"] == "audio" and mensaje.get("media_id"):
        print("[AUDIO] Descargando y transcribiendo...")
        tipo_media_guardar = "audio"
        try:
            carpeta_tmp = Path(tempfile.gettempdir())
            destino = carpeta_tmp / f"audio_{mensaje['media_id']}.ogg"
            archivo = descargar_audio_whatsapp(media_id=mensaje["media_id"], destino_local=destino)
            archivo_media_local = archivo
            transcripcion = transcribir_audio(archivo)
            if transcripcion["exito"]:
                texto = transcripcion["texto_transcrito"]
                print(f"[AUDIO] Transcrito: {texto}")
            else:
                texto = None
        except Exception as e:
            print(f"[ERROR] Transcribiendo audio: {e}")
            texto = None

    # --- IMAGEN ---
    elif mensaje["tipo"] == "image" and mensaje.get("media_id"):
        print("[IMAGEN] Descargando y analizando...")
        tipo_media_guardar = "imagen"
        caption = mensaje.get("texto")  # lo que el cliente escribio junto a la foto
        try:
            carpeta_tmp = Path(tempfile.gettempdir())
            destino = carpeta_tmp / f"imagen_{mensaje['media_id']}.jpg"
            # La misma funcion de descarga sirve para imagenes (mismo mecanismo de Meta)
            archivo = descargar_audio_whatsapp(media_id=mensaje["media_id"], destino_local=destino)
            archivo_media_local = archivo
            analisis = analizar_imagen(archivo)
            if analisis["exito"]:
                desc = analisis["descripcion"]
                print(f"[IMAGEN] Analisis: {desc}")
                # Armamos el texto que va al router: lo que se ve en la foto
                # + el caption del cliente si escribio algo.
                if caption:
                    texto = f"{caption}. (El cliente mando una foto: {desc})"
                else:
                    texto = f"El cliente mando una foto de un repuesto: {desc}"
            else:
                texto = None
        except Exception as e:
            print(f"[ERROR] Analizando imagen: {e}")
            texto = None

    if not texto:
        # No pudimos obtener texto (ni de audio, ni de imagen, ni escrito).
        # Toni pide amablemente que lo escriban.
        enviar_mensaje(
            numero,
            "Perdon, no pude leer bien lo que me mandaste. Me lo escribis como texto asi te ayudo?",
            phone_number_id=phone_number_id,
        )
        return

    # ===== Obtener o crear cliente =====
    try:
        cliente_resp = sb.rpc("fn_get_or_create_cliente", {
            "p_empresa_id": empresa_id,
            "p_canal": "whatsapp",
            "p_identificador": numero,
            "p_display_name": nombre,
        }).execute()
        cliente_id = cliente_resp.data
    except Exception as e:
        print(f"[WARN] No pude usar fn_get_or_create_cliente: {e}. Creando manual.")
        cli = sb.table("cliente").insert({
            "empresa_id": empresa_id,
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
        .eq("empresa_id", empresa_id)
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
            "empresa_id": empresa_id,
            "cliente_id": cliente_id,
            "canal": "whatsapp",
            "estado": "activa",
        }).execute().data[0]
        conversacion_id = conv["id"]

    # ===== Si vino audio o imagen, archivarlo en Storage (extra, no rompe el flujo) =====
    if archivo_media_local is not None:
        try:
            subida = subir_audio_a_storage(
                archivo_local=archivo_media_local,
                conversacion_id=conversacion_id,
                empresa_id=empresa_id,
            )
            media_url_media = subida.get("url_firmada")
            print(f"[MEDIA] Archivado en Storage: {subida.get('ruta_storage')}")
        except Exception as e:
            print(f"[WARN] No pude archivar el archivo en Storage: {e}")

    # ===== Guardar mensaje entrante =====
    sb.table("mensaje").insert({
        "conversacion_id": conversacion_id,
        "emisor": "cliente",
        "contenido": texto,
        "tipo_media": tipo_media_guardar,
        "media_url": media_url_media,
        "whatsapp_msg_id": mensaje.get("wamid"),
    }).execute()

    # ===== Leer historial (memoria) =====
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
        respuesta_texto = responder_social(texto, historial=historial)
    else:
        try:
            agente_fn = AGENTES[agente_elegido]
            kwargs = {
                "mensaje_cliente": texto,
                "contexto": {"canal": "whatsapp", "cliente_id": cliente_id, "empresa_id": empresa_id},
                "verbose": False,
            }
            params_del_agente = inspect.signature(agente_fn).parameters
            if "historial" in params_del_agente:
                kwargs["historial"] = historial

            resultado = agente_fn(**kwargs)
            respuesta_texto = resultado["respuesta_texto"]
        except Exception as e:
            print(f"[ERROR] Agente {agente_elegido}: {e}")
            respuesta_texto = "Disculpa, tuve un problema procesando tu consulta. Podes intentar de nuevo?"

    # ===== Enviar respuesta por WhatsApp (por la misma linea) =====
    envio = enviar_mensaje(numero, respuesta_texto, phone_number_id=phone_number_id)
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