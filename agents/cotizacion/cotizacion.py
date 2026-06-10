"""
agents/cotizacion/cotizacion.py
Cierra ventas: confirma productos, calcula totales, crea pedidos.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI

from functions.catalog_tools import TOOLS_MAP as CATALOG_TOOLS
from functions.order_tools import TOOLS_MAP as ORDER_TOOLS


_AGENT_DIR = Path(__file__).parent
_PROMPT = (_AGENT_DIR / "prompt.md").read_text(encoding="utf-8")

# Cotización necesita acceso a todo: buscar productos, consultar precio, armar pedido
ALL_TOOLS = {**CATALOG_TOOLS, **ORDER_TOOLS}


TOOLS_DEF = [
    {
        "type": "function",
        "function": {
            "name": "buscar_por_aplicacion",
            "description": "Busca productos compatibles con un vehículo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "marca": {"type": "string", "description": "VW, Ford, Renault, Chevrolet..."},
                    "modelo": {"type": "string"},
                    "anio": {"type": "integer"},
                    "motor": {"type": "string"},
                    "posicion": {"type": "string"},
                    "linea": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["marca", "modelo", "anio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_precio",
            "description": "Devuelve el precio final del producto. Usar SIEMPRE antes de confirmar pedido.",
            "parameters": {
                "type": "object",
                "properties": {"producto_id": {"type": "integer"}},
                "required": ["producto_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_stock",
            "description": "Verifica stock disponible. Obligatorio antes de armar pedido.",
            "parameters": {
                "type": "object",
                "properties": {"producto_id": {"type": "integer"}},
                "required": ["producto_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "armar_pedido",
            "description": "Crea el pedido en estado borrador. USAR SOLO después de confirmación explícita del cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_id": {"type": "integer"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "producto_id": {"type": "integer"},
                                "cantidad": {"type": "integer"},
                                "precio_unitario": {"type": "number"},
                            },
                            "required": ["producto_id", "cantidad", "precio_unitario"],
                        },
                    },
                },
                "required": ["cliente_id", "items"],
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

    for iteracion in range(8):  # Cotización puede necesitar más iteraciones
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

            if tool_name not in ALL_TOOLS:
                tool_result = {"error": f"Tool '{tool_name}' no existe"}
            else:
                try:
                    tool_result = ALL_TOOLS[tool_name](**tool_args)
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
        "iteraciones": 8,
    }