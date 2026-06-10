"""
agents/router/router.py
El Router clasifica cada mensaje del cliente y decide qué agente
especialista lo va a atender. Usa GPT-4.1 Mini (modelo barato y rápido).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI


# Cargar prompt y schema desde los archivos
_AGENT_DIR = Path(__file__).parent
_PROMPT = (_AGENT_DIR / "prompt.md").read_text(encoding="utf-8")
_SCHEMA = json.loads((_AGENT_DIR / "schema.json").read_text(encoding="utf-8"))


def get_openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en el .env.")
    return OpenAI(api_key=api_key)


def clasificar(
    mensaje: str,
    contexto: dict | None = None,
) -> dict:
    """
    Clasifica un mensaje y devuelve la intención + el agente que debería tomarlo.

    Args:
        mensaje: el texto del cliente.
        contexto: info opcional (cliente recurrente, vehiculo conocido, etc).

    Returns:
        Dict con: { "agente": "producto", "intencion": "buscar_producto",
                    "confianza": 0.95, "razonamiento": "...", "datos": {...} }
    """
    client = get_openai_client()
    model = os.environ.get("MODEL_ROUTER", "gpt-4.1-mini")

    contexto_txt = ""
    if contexto:
        contexto_txt = f"\n\nContexto del cliente:\n{json.dumps(contexto, ensure_ascii=False, indent=2)}"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": f"Mensaje del cliente:\n{mensaje}{contexto_txt}"},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "router_output",
                "schema": _SCHEMA,
                "strict": False,
            },
        },
        temperature=0.2,
    )

    content = response.choices[0].message.content
    return json.loads(content)
