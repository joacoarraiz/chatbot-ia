"""
agents/faq/faq.py
El agente FAQ responde preguntas sobre el comercio:
horarios, ubicación, formas de pago, envíos, servicios, etc.

Usa DOS fuentes con linea divisoria clara:
  - consultar_info_empresa  -> empresa.persona_config (envios, pagos, telefono, marcas)
  - consultar_config_negocio -> config_negocio (horarios, servicios, web, redes, feriados)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI

from functions.faq_tools import TOOLS_MAP
from functions.config_tools import TOOLS_MAP as CONFIG_TOOLS_MAP


_AGENT_DIR = Path(__file__).parent
_PROMPT = (_AGENT_DIR / "prompt.md").read_text(encoding="utf-8")


# Juntamos las dos fuentes de tools sin tocar faq_tools (que ya anda).
TOOLS_MAP_COMBINADO = {**TOOLS_MAP, **CONFIG_TOOLS_MAP}


TOOLS_DEF = [
    {
        "type": "function",
        "function": {
            "name": "consultar_info_empresa",
            "description": "Info GENERAL del comercio: envíos, formas de pago, teléfono, marcas que trabajan, retiro en local. Sin parámetros trae todo. NO usar para horarios ni servicios (para eso está consultar_config_negocio).",
            "parameters": {
                "type": "object",
                "properties": {
                    "campo": {
                        "type": "string",
                        "description": "Opcional. Ej: 'formas_pago', 'envios', 'telefono', 'marcas_principales', 'retiro_en_local'."
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_config_negocio",
            "description": "HORARIOS de atención, SERVICIOS que hace el comercio (cambio de escobillas, alineación, etc. y qué días), página web, Instagram y qué hace en feriados. Usá SIEMPRE esta para horarios y servicios.",
            "parameters": {
                "type": "object",
                "properties": {
                    "empresa_id": {
                        "type": "integer",
                        "description": "ID del comercio. Tomalo del contexto de la conversación (viene como empresa_id)."
                    },
                    "campo": {
                        "type": "string",
                        "description": "Opcional. Ej: 'horarios', 'servicios', 'web', 'instagram', 'atiende_feriados'."
                    },
                },
                "required": ["empresa_id"],
            },
        },
    },
]


def get_openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en el .env.")
    return OpenAI(api_key=api_key)


def responder(
    mensaje_cliente: str,
    contexto: dict | None = None,
    historial: list | None = None,
    verbose: bool = False,
) -> dict:
    client = get_openai_client()
    model = os.environ.get("MODEL_SPECIALIST", "gpt-4.1")

    messages = [{"role": "system", "content": _PROMPT}]
    if contexto:
        messages.append({"role": "system", "content": f"Contexto: {json.dumps(contexto, ensure_ascii=False)}"})
    if historial:
        messages.extend(historial)
    messages.append({"role": "user", "content": mensaje_cliente})

    tools_usadas = []
    tokens_total = 0

    for iteracion in range(5):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_DEF,
            temperature=0.3,
        )
        tokens_total += response.usage.total_tokens
        msg = response.choices[0].message

        if not msg.tool_calls:
            if verbose:
                print(f"  💭 [iteración {iteracion + 1}] Respuesta final generada.")
            return {
                "respuesta_texto": msg.content,
                "tools_usadas": tools_usadas,
                "tokens_usados": tokens_total,
                "iteraciones": iteracion + 1,
            }

        messages.append(msg)
        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            if verbose:
                print(f"  🔧 [iteración {iteracion + 1}] Tool: {tool_name}({tool_args})")
            tools_usadas.append({"nombre": tool_name, "args": tool_args})

            if tool_name not in TOOLS_MAP_COMBINADO:
                tool_result = {"error": f"Tool '{tool_name}' no existe"}
            else:
                try:
                    tool_result = TOOLS_MAP_COMBINADO[tool_name](**tool_args)
                except Exception as e:
                    tool_result = {"error": str(e)}

            if verbose:
                preview = json.dumps(tool_result, ensure_ascii=False, default=str)[:100]
                print(f"     ✅ Resultado: {preview}...")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(tool_result, ensure_ascii=False, default=str),
            })

    return {
        "respuesta_texto": "Disculpá, hubo un problema procesando tu consulta.",
        "tools_usadas": tools_usadas,
        "tokens_usados": tokens_total,
        "iteraciones": 5,
    }