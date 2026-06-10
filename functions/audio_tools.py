"""
functions/audio_tools.py
Funciones para manejar audios:
  1. descargar_audio_whatsapp - baja un audio desde Meta Cloud API
  2. subir_audio_a_storage    - guarda el audio en Supabase Storage
  3. transcribir_audio        - transcribe con GPT-4o Mini Transcribe

Notas:
  - descargar_audio_whatsapp requiere credenciales de Meta. Hasta tenerlas,
    podemos usar archivos locales directamente con transcribir_audio.
  - El bucket "media" tiene que existir en Supabase Storage (ya lo creamos).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI

from functions.db import get_client


# ============ DESCARGA DE WHATSAPP ============

def descargar_audio_whatsapp(media_id: str, destino_local: str | Path) -> Path:
    """
    Descarga un audio desde Meta Cloud API.

    Args:
        media_id: el ID del media que llega en el webhook de WhatsApp.
        destino_local: path donde guardar el archivo descargado.

    Returns:
        Path al archivo descargado.

    Raises:
        RuntimeError si faltan credenciales de Meta o si la descarga falla.
    """
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    if not access_token:
        raise RuntimeError(
            "Falta WHATSAPP_ACCESS_TOKEN en el .env. "
            "Las credenciales llegan despues de la Etapa 2 de Meta."
        )

    # Paso 1: pedir la URL del media a Meta
    url_meta = f"https://graph.facebook.com/v21.0/{media_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    with httpx.Client(timeout=30.0) as client:
        resp_metadata = client.get(url_meta, headers=headers)
        resp_metadata.raise_for_status()
        metadata = resp_metadata.json()
        media_url = metadata.get("url")
        if not media_url:
            raise RuntimeError(f"Meta no devolvio URL para media_id={media_id}")

        # Paso 2: bajar el archivo desde la URL temporal
        resp_audio = client.get(media_url, headers=headers)
        resp_audio.raise_for_status()

        destino = Path(destino_local)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(resp_audio.content)
        return destino


# ============ SUBIDA A SUPABASE STORAGE ============

def subir_audio_a_storage(
    archivo_local: str | Path,
    conversacion_id: int,
    empresa_id: Optional[int] = None,
) -> dict:
    """
    Sube un audio al bucket "media" de Supabase Storage.

    Args:
        archivo_local: path al archivo de audio en disco.
        conversacion_id: ID de la conversacion al que pertenece.
        empresa_id: si no se pasa, usa EMPRESA_ID_PILOTO.

    Returns:
        dict con la URL publica del archivo subido y la ruta interna.
    """
    sb = get_client()
    empresa_id = empresa_id or int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

    archivo = Path(archivo_local)
    if not archivo.exists():
        raise FileNotFoundError(f"No existe el archivo: {archivo}")

    # Path en el bucket: empresa_<id>/conversacion_<id>/<nombre_archivo>
    ruta_storage = f"empresa_{empresa_id}/conversacion_{conversacion_id}/{archivo.name}"

    # Subir
    with archivo.open("rb") as f:
        sb.storage.from_("media").upload(
            path=ruta_storage,
            file=f,
            file_options={"content-type": "audio/ogg", "upsert": "true"},
        )

    # URL para acceso interno (signed URL valida por 1 hora)
    signed = sb.storage.from_("media").create_signed_url(ruta_storage, 3600)
    url_firmada = signed.get("signedURL") or signed.get("signed_url")

    return {
        "ruta_storage": ruta_storage,
        "url_firmada": url_firmada,
        "tamanio_bytes": archivo.stat().st_size,
    }


# ============ TRANSCRIPCION CON OPENAI ============

def transcribir_audio(archivo_local: str | Path) -> dict:
    """
    Transcribe un audio usando el modelo configurado en MODEL_TRANSCRIBE.
    Por defecto: gpt-4o-mini-transcribe.

    Args:
        archivo_local: path al archivo de audio.

    Returns:
        dict con: texto_transcrito, modelo_usado, duracion_segundos (estimada),
        archivo_origen, exito (bool).
    """
    archivo = Path(archivo_local)
    if not archivo.exists():
        return {
            "exito": False,
            "error": f"No existe el archivo: {archivo}",
            "texto_transcrito": None,
        }

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "exito": False,
            "error": "Falta OPENAI_API_KEY en el .env",
            "texto_transcrito": None,
        }

    modelo = os.environ.get("MODEL_TRANSCRIBE", "gpt-4o-mini-transcribe")
    client = OpenAI(api_key=api_key)

    try:
        with archivo.open("rb") as f:
            response = client.audio.transcriptions.create(
                model=modelo,
                file=f,
                language="es",  # hint: el audio esta en espanol
                # response_format="text" es lo mas simple
                response_format="text",
            )

        # response puede ser string directo o objeto, dependiendo del modelo
        if isinstance(response, str):
            texto = response
        else:
            texto = getattr(response, "text", str(response))

        return {
            "exito": True,
            "texto_transcrito": texto.strip(),
            "modelo_usado": modelo,
            "archivo_origen": str(archivo),
            "tamanio_bytes": archivo.stat().st_size,
        }

    except Exception as e:
        return {
            "exito": False,
            "error": str(e),
            "texto_transcrito": None,
            "archivo_origen": str(archivo),
            "modelo_usado": modelo,
        }


# ============ FLUJO COMPLETO ============

def procesar_audio_local(
    archivo_local: str | Path,
    conversacion_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
    subir_a_storage: bool = False,
) -> dict:
    """
    Flujo completo para un audio que YA esta en disco (sin pasar por WhatsApp):
      1. (opcional) Sube el audio a Supabase Storage.
      2. Transcribe el audio con OpenAI.
      3. Devuelve todo junto.

    Args:
        archivo_local: path al audio.
        conversacion_id: si pasa, se usa para subir a Storage.
        empresa_id: igual.
        subir_a_storage: si True, sube tambien a Storage.

    Returns:
        dict con resultado completo.
    """
    resultado = {
        "archivo_origen": str(archivo_local),
        "subido_a_storage": False,
        "url_firmada": None,
        "transcripcion": None,
        "exito": False,
    }

    # Paso 1 (opcional): subir a Storage
    if subir_a_storage and conversacion_id:
        try:
            subida = subir_audio_a_storage(
                archivo_local=archivo_local,
                conversacion_id=conversacion_id,
                empresa_id=empresa_id,
            )
            resultado["subido_a_storage"] = True
            resultado["url_firmada"] = subida["url_firmada"]
            resultado["ruta_storage"] = subida["ruta_storage"]
        except Exception as e:
            resultado["error_storage"] = str(e)

    # Paso 2: transcribir
    transcripcion = transcribir_audio(archivo_local)
    resultado["transcripcion"] = transcripcion
    resultado["exito"] = transcripcion["exito"]

    return resultado


# Mapa para futuro uso
TOOLS_MAP = {
    "transcribir_audio": transcribir_audio,
    "procesar_audio_local": procesar_audio_local,
}