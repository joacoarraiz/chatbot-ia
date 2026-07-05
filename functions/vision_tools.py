"""
functions/vision_tools.py
Analisis de imagenes que manda el cliente por WhatsApp.

El cliente saca una foto de la pieza que necesita (o de una vieja con un
codigo grabado) y el modelo con VISION la mira y nos dice que repuesto es
y si tiene algun codigo visible. Eso se convierte en texto para buscar en
el catalogo, igual que la transcripcion de un audio.

Reusa la descarga de audio_tools (el mecanismo de Meta es el mismo para
cualquier archivo). No necesita Google Lens: la vista es nativa del LLM.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from openai import OpenAI


def _detectar_mime(datos: bytes) -> str:
    """Detecta el tipo de imagen por los primeros bytes. Default: jpeg."""
    if datos[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def analizar_imagen(archivo_local) -> dict:
    """
    Analiza una imagen con el modelo con vision.

    Devuelve un dict con:
      - exito (bool)
      - descripcion: texto para buscar en el catalogo (tipo de pieza + codigo)
      - modelo_usado, archivo_origen
      - error (si fallo)
    """
    archivo = Path(archivo_local)
    if not archivo.exists():
        return {"exito": False, "error": f"No existe el archivo: {archivo}", "descripcion": None}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"exito": False, "error": "Falta OPENAI_API_KEY en el .env", "descripcion": None}

    # Modelo con vision: usa MODEL_VISION si esta, sino el especialista (gpt-4.1
    # es multimodal), sino gpt-4o por defecto.
    modelo = os.environ.get("MODEL_VISION") or os.environ.get("MODEL_SPECIALIST") or "gpt-4o"

    try:
        datos = archivo.read_bytes()
        mime = _detectar_mime(datos)
        b64 = base64.b64encode(datos).decode("utf-8")
        data_uri = f"data:{mime};base64,{b64}"

        prompt = (
            "Sos un experto en autopartes de una casa de repuestos en Argentina. "
            "El cliente mando esta foto. Decime de forma breve QUE repuesto es y, si se ve "
            "algun codigo o numero de parte grabado, transcribilo EXACTO. "
            "Devolve una linea corta para buscar la pieza en el catalogo, por ejemplo: "
            "'Pastilla de freno, codigo D1234' o 'Filtro de aceite, sin codigo visible'. "
            "Si no estas seguro de algo, decilo (no inventes). "
            "Si la foto NO parece ser de un repuesto de auto, responde exactamente: "
            "'La foto no parece ser de un repuesto.'"
        )

        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=modelo,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            max_tokens=200,
            temperature=0.2,
        )
        descripcion = (resp.choices[0].message.content or "").strip()

        if not descripcion:
            return {"exito": False, "error": "El modelo no devolvio descripcion", "descripcion": None}

        return {
            "exito": True,
            "descripcion": descripcion,
            "modelo_usado": modelo,
            "archivo_origen": str(archivo),
        }

    except Exception as e:
        return {"exito": False, "error": str(e), "descripcion": None, "archivo_origen": str(archivo)}
