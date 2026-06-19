"""
functions/whatsapp.py
Funciones para interactuar con WhatsApp Cloud API:
  - enviar_mensaje: manda un texto a un numero.
  - validar_firma: verifica que un request viene realmente de Meta (HMAC).
  - parsear_mensaje_entrante: extrae los datos de un webhook de Meta.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

import httpx


GRAPH_API_VERSION = "v21.0"


def _phone_number_id() -> str:
    pid = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if not pid:
        raise RuntimeError("Falta WHATSAPP_PHONE_NUMBER_ID en el .env")
    return pid


def _access_token() -> str:
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Falta WHATSAPP_ACCESS_TOKEN en el .env")
    return token


# ============ ENVIAR MENSAJE ============
def enviar_mensaje(numero_destino: str, texto: str) -> dict:
    """
    Envia un mensaje de texto por WhatsApp Cloud API.

    Args:
        numero_destino: numero del destinatario (formato internacional sin +, ej "5491128583204").
        texto: el mensaje a enviar.

    Returns:
        dict con la respuesta de Meta (incluye el wamid del mensaje enviado).
    """
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{_phone_number_id()}/messages"
    headers = {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero_destino,
        "type": "text",
        "text": {"body": texto},
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Extraer el wamid (id del mensaje en WhatsApp)
    wamid = None
    try:
        wamid = data["messages"][0]["id"]
    except (KeyError, IndexError):
        pass

    return {"exito": True, "wamid": wamid, "respuesta": data}


# ============ VALIDAR FIRMA (HMAC) ============
def validar_firma(payload_bytes: bytes, firma_header: Optional[str]) -> bool:
    """
    Valida que el request viene realmente de Meta usando HMAC SHA256.

    Args:
        payload_bytes: el body crudo del request (en bytes).
        firma_header: el valor del header X-Hub-Signature-256 (ej "sha256=abc123...").

    Returns:
        True si la firma es valida, False si no.
    """
    app_secret = os.environ.get("WHATSAPP_APP_SECRET")
    if not app_secret:
        # Si no hay app_secret configurado, modo desarrollo: no validamos.
        # ADVERTENCIA: en produccion esto SIEMPRE debe estar configurado.
        print("[WARN] WHATSAPP_APP_SECRET no configurado. Saltando validacion HMAC (modo dev).")
        return True

    if not firma_header:
        print("[WARN] Request sin header de firma.")
        return False

    # El header viene como "sha256=<hash>"
    try:
        metodo, firma_recibida = firma_header.split("=", 1)
    except ValueError:
        return False

    if metodo != "sha256":
        return False

    # Calcular el HMAC esperado
    firma_esperada = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Comparacion segura contra timing attacks
    return hmac.compare_digest(firma_recibida, firma_esperada)


# ============ PARSEAR MENSAJE ENTRANTE ============
def parsear_mensaje_entrante(body: dict) -> Optional[dict]:
    """
    Extrae los datos relevantes de un webhook de WhatsApp.

    Returns:
        dict con { numero, nombre, texto, wamid, tipo, media_id } o None si
        no es un mensaje de texto/audio procesable (ej: es un status update).
    """
    try:
        entry = body["entry"][0]
        change = entry["changes"][0]
        value = change["value"]

        # Los status updates (entregado, leido) no son mensajes
        if "messages" not in value:
            return None

        mensaje = value["messages"][0]
        numero = mensaje["from"]
        wamid = mensaje["id"]
        tipo = mensaje["type"]

        # Nombre del contacto (si viene)
        nombre = None
        if "contacts" in value and value["contacts"]:
            nombre = value["contacts"][0].get("profile", {}).get("name")

        resultado = {
            "numero": numero,
            "nombre": nombre,
            "wamid": wamid,
            "tipo": tipo,
            "texto": None,
            "media_id": None,
        }

        if tipo == "text":
            resultado["texto"] = mensaje["text"]["body"]
        elif tipo == "audio":
            resultado["media_id"] = mensaje["audio"]["id"]
        # otros tipos (image, video, etc.) los ignoramos por ahora

        return resultado

    except (KeyError, IndexError) as e:
        print(f"[WARN] No pude parsear el mensaje entrante: {e}")
        return None