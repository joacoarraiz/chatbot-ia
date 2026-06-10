"""
agents/pedido/pedido.py
Consulta el estado de pedidos ya armados.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI

from functions.order_tools import TOOLS_MAP


_AGENT_DIR = Path(__file__).parent
_PROMPT = (_AGENT_DIR / "prompt.md").read_text(encoding="utf-8")


TOOLS_DEF = [
    {
        "type": "function",
        "function": {
            "name": "consultar_pedido",
            "description": "Trae el estado actual de un pedido ya creado, con sus items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pedido_id": {"type": "integer", "description": "ID del pedido a consultar."},
                },
                "required": ["pedido_id"],
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

            if tool_name not in TOOLS_MAP:
                tool_result = {"error": f"Tool '{tool_name}' no existe"}
            else:
                try:
                    tool_result = TOOLS_MAP[tool_name](**tool_args)
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