"""
functions/whatsapp.py
Funciones para interactuar con WhatsApp Cloud API:
  - enviar_mensaje: manda un texto a un numero (normaliza numeros argentinos).
  - enviar_plantilla: manda una plantilla aprobada (para avisos fuera de la ventana de 24hs).
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


def _phone_number_id(override: Optional[str] = None) -> str:
    """
    Devuelve el phone_number_id a usar para enviar.
    - Si se pasa 'override' (el numero por el que entro el mensaje), usa ese.
    - Si no, cae al del .env (comportamiento de siempre).
    Asi el bot puede responder por el mismo numero que recibio el mensaje,
    sin romper el flujo de un solo numero.
    """
    if override:
        return override
    pid = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if not pid:
        raise RuntimeError("Falta WHATSAPP_PHONE_NUMBER_ID en el .env")
    return pid


def _access_token() -> str:
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Falta WHATSAPP_ACCESS_TOKEN en el .env")
    return token


# ============ NORMALIZAR NUMERO ARGENTINO ============
def normalizar_numero(numero: str) -> str:
    """
    WhatsApp a veces manda los numeros argentinos con un '9' extra
    despues del codigo de pais (549...) pero la API de envio los espera
    SIN ese 9 (54...). Esta funcion lo corrige.

    Ejemplo: 5492235984575 -> 542235984575

    Solo afecta numeros argentinos (que empiezan con 549). El resto
    se devuelve tal cual.
    """
    numero = numero.strip().replace("+", "").replace(" ", "").replace("-", "")

    # Si es argentino con el 9 extra: 549 + area + numero
    if numero.startswith("549"):
        # Sacar el 9 que va despues del 54
        numero = "54" + numero[3:]

    return numero


# ============ ENVIAR MENSAJE ============
def enviar_mensaje(numero_destino: str, texto: str, phone_number_id: Optional[str] = None) -> dict:
    """
    Envia un mensaje de texto por WhatsApp Cloud API.
    Normaliza el numero argentino antes de enviar.

    - phone_number_id (opcional): el numero PROPIO desde el que se envia.
      Sirve para multi-comercio: responder por la misma linea que recibio
      el mensaje. Si no se pasa, usa el del .env (comportamiento de siempre).

    Si Meta rechaza el envio, imprime el detalle EXACTO.
    """
    numero_normalizado = normalizar_numero(numero_destino)
    if numero_normalizado != numero_destino:
        print(f"[NUM] Numero normalizado: {numero_destino} -> {numero_normalizado}")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{_phone_number_id(phone_number_id)}/messages"
    headers = {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero_normalizado,
        "type": "text",
        "text": {"body": texto},
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)

        if resp.status_code >= 400:
            print("=" * 60)
            print(f"[ERROR WhatsApp] Meta rechazo el envio a: {numero_normalizado}")
            print(f"[ERROR WhatsApp] HTTP status: {resp.status_code}")
            try:
                error_data = resp.json()
                err = error_data.get("error", {})
                print(f"[ERROR WhatsApp] code:     {err.get('code')}")
                print(f"[ERROR WhatsApp] message:  {err.get('message')}")
                print(f"[ERROR WhatsApp] details:  {err.get('error_data', {}).get('details')}")
            except Exception:
                print(f"[ERROR WhatsApp] Respuesta cruda: {resp.text}")
            print("=" * 60)

        resp.raise_for_status()
        data = resp.json()

    wamid = None
    try:
        wamid = data["messages"][0]["id"]
    except (KeyError, IndexError):
        pass

    return {"exito": True, "wamid": wamid, "respuesta": data}


# ============ ENVIAR PLANTILLA (TEMPLATE) ============
def enviar_plantilla(
    numero_destino: str,
    nombre_plantilla: str,
    variables: Optional[list] = None,
    idioma: str = "es_AR",
    phone_number_id: Optional[str] = None,
) -> dict:
    """
    Envia una PLANTILLA aprobada por WhatsApp Cloud API.

    A diferencia de enviar_mensaje (texto libre), la plantilla es el unico
    tipo de mensaje que Meta permite mandar cuando el bot INICIA la conversacion
    (fuera de la ventana de 24hs). Tiene que estar aprobada de antemano.

    - numero_destino: numero destino (se normaliza igual que en enviar_mensaje).
    - nombre_plantilla: nombre exacto de la plantilla aprobada (ej: "aviso_derivacion").
    - variables: lista de textos que van en las {{1}}, {{2}}, {{3}}... del cuerpo,
                 EN ORDEN. Si la plantilla no tiene variables, pasar None o [].
    - idioma: codigo de idioma con el que se aprobo la plantilla (ej: "es_AR", "es").
    - phone_number_id (opcional): numero propio desde el que se envia (multi-comercio).

    Reusa normalizar_numero, el phone_number_id y el token.
    Si Meta rechaza el envio, imprime el detalle EXACTO (igual que enviar_mensaje).
    """
    numero_normalizado = normalizar_numero(numero_destino)
    if numero_normalizado != numero_destino:
        print(f"[NUM] Numero normalizado: {numero_destino} -> {numero_normalizado}")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{_phone_number_id(phone_number_id)}/messages"
    headers = {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
    }

    template_obj = {
        "name": nombre_plantilla,
        "language": {"code": idioma},
    }

    # Si hay variables, van como parametros del componente "body"
    if variables:
        template_obj["components"] = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(v)} for v in variables
                ],
            }
        ]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero_normalizado,
        "type": "template",
        "template": template_obj,
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)

        if resp.status_code >= 400:
            print("=" * 60)
            print(f"[ERROR WhatsApp] Meta rechazo la plantilla '{nombre_plantilla}' a: {numero_normalizado}")
            print(f"[ERROR WhatsApp] HTTP status: {resp.status_code}")
            try:
                error_data = resp.json()
                err = error_data.get("error", {})
                print(f"[ERROR WhatsApp] code:     {err.get('code')}")
                print(f"[ERROR WhatsApp] message:  {err.get('message')}")
                print(f"[ERROR WhatsApp] details:  {err.get('error_data', {}).get('details')}")
            except Exception:
                print(f"[ERROR WhatsApp] Respuesta cruda: {resp.text}")
            print("=" * 60)

        resp.raise_for_status()
        data = resp.json()

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
    """
    app_secret = os.environ.get("WHATSAPP_APP_SECRET")
    if not app_secret:
        print("[WARN] WHATSAPP_APP_SECRET no configurado. Saltando validacion HMAC (modo dev).")
        return True

    if not firma_header:
        print("[WARN] Request sin header de firma.")
        return False

    try:
        metodo, firma_recibida = firma_header.split("=", 1)
    except ValueError:
        return False

    if metodo != "sha256":
        return False

    firma_esperada = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(firma_recibida, firma_esperada)


# ============ PARSEAR MENSAJE ENTRANTE ============
def parsear_mensaje_entrante(body: dict) -> Optional[dict]:
    """
    Extrae los datos relevantes de un webhook de WhatsApp.

    Ahora tambien extrae 'phone_number_id': el numero PROPIO por el que
    entro el mensaje. Sirve para multi-comercio (saber a que comercio va
    y por que linea responder).
    """
    try:
        entry = body["entry"][0]
        change = entry["changes"][0]
        value = change["value"]

        if "messages" not in value:
            return None

        # Numero propio por el que entro el mensaje (multi-comercio).
        # Viene en value.metadata.phone_number_id. Si no esta, queda None.
        phone_number_id = None
        metadata = value.get("metadata") or {}
        phone_number_id = metadata.get("phone_number_id")

        mensaje = value["messages"][0]
        numero = mensaje["from"]
        wamid = mensaje["id"]
        tipo = mensaje["type"]

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
            "phone_number_id": phone_number_id,   # <-- nuevo
        }

        if tipo == "text":
            resultado["texto"] = mensaje["text"]["body"]
        elif tipo == "audio":
            resultado["media_id"] = mensaje["audio"]["id"]

        return resultado

    except (KeyError, IndexError) as e:
        print(f"[WARN] No pude parsear el mensaje entrante: {e}")
        return None
        