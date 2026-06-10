"""
agents/producto/producto.py
El agente Producto razona sobre la consulta y decide qué tools usar.
Hace function calling con GPT-4.1 y conecta las 5 tools del catálogo.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI

from functions.catalog_tools import TOOLS_MAP


# Cargar el prompt del sistema desde el archivo
_AGENT_DIR = Path(__file__).parent
_PROMPT = (_AGENT_DIR / "prompt.md").read_text(encoding="utf-8")


# Definición de las tools en formato OpenAI
# Esto le dice al modelo qué funciones tiene disponibles y con qué parámetros
TOOLS_DEF = [
    {
        "type": "function",
        "function": {
            "name": "buscar_producto",
            "description": "Busca productos por descripción full-text. Útil cuando el cliente describe la pieza con palabras (ej: 'pastillas de freno', 'rótulas delanteras').",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto que describe la pieza buscada."},
                    "marca_pieza": {"type": "string", "description": "Filtrar por marca del fabricante (Bosch, Sachs, Monroe...). Opcional."},
                    "linea": {"type": "string", "description": "Filtrar por sistema vehicular: frenos, suspension, embrague, rodamientos. Opcional."},
                    "limit": {"type": "integer", "description": "Cuántos resultados devolver. Default 5."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_por_aplicacion",
            "description": "Busca productos compatibles con un vehículo específico. Es la tool MÁS USADA porque la mayoría de consultas son 'qué tengo para mi auto X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "marca": {"type": "string", "description": "Marca del auto. IMPORTANTE: usar 'VW' (no Volkswagen), 'Chevrolet' (no Chevy), etc. Forma corta estándar argentina."},
                    "modelo": {"type": "string", "description": "Modelo del auto. Ej: Gol, Fiesta, Corsa."},
                    "anio": {"type": "integer", "description": "Año del auto."},
                    "motor": {"type": "string", "description": "Cilindrada (1.6, 1.4 TDI). Opcional."},
                    "posicion": {"type": "string", "description": "delantera | trasera | superior | inferior. Opcional."},
                    "linea": {"type": "string", "description": "frenos | suspension | embrague | rodamientos. Opcional."},
                    "limit": {"type": "integer", "description": "Cuántos resultados devolver. Default 5."},
                },
                "required": ["marca", "modelo", "anio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_equivalencia",
            "description": "Busca por código OEM o cruzada. Útil cuando el cliente trae el código del fabricante original.",
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string", "description": "Código a buscar."},
                },
                "required": ["codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_precio",
            "description": "Devuelve el precio final del producto aplicando las reglas configuradas. Usar DESPUÉS de identificar un producto_id concreto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_id": {"type": "integer", "description": "ID del producto."},
                },
                "required": ["producto_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_stock",
            "description": "Devuelve el stock agregado del producto en todas las fuentes y depósitos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_id": {"type": "integer", "description": "ID del producto."},
                },
                "required": ["producto_id"],
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
    """
    El agente Producto procesa una consulta del cliente.

    Args:
        mensaje_cliente: el texto del cliente.
        contexto: opcional (datos del cliente, vehículo conocido, etc).
        historial: opcional, mensajes previos de la conversación.
        verbose: si True, imprime el razonamiento paso a paso.

    Returns:
        dict con: respuesta_texto, tools_usadas, tokens_usados.
    """
    client = get_openai_client()
    model = os.environ.get("MODEL_SPECIALIST", "gpt-4.1")

    # Armar los mensajes
    messages = [{"role": "system", "content": _PROMPT}]

    if contexto:
        messages.append({
            "role": "system",
            "content": f"Contexto del cliente: {json.dumps(contexto, ensure_ascii=False)}",
        })

    if historial:
        messages.extend(historial)

    messages.append({"role": "user", "content": mensaje_cliente})

    tools_usadas = []
    tokens_total = 0
    max_iteraciones = 5  # Por si el LLM entra en loop

    for iteracion in range(max_iteraciones):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_DEF,
            temperature=0.4,
        )
        tokens_total += response.usage.total_tokens

        msg = response.choices[0].message

        # Caso 1: el modelo NO pidió usar tools → es la respuesta final
        if not msg.tool_calls:
            if verbose:
                print(f"  💭 [iteración {iteracion + 1}] Respuesta final generada.")
            return {
                "respuesta_texto": msg.content,
                "tools_usadas": tools_usadas,
                "tokens_usados": tokens_total,
                "iteraciones": iteracion + 1,
            }

        # Caso 2: el modelo pidió usar tools → las ejecutamos
        messages.append(msg)  # agregar la respuesta del modelo al historial

        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            if verbose:
                print(f"  🔧 [iteración {iteracion + 1}] Tool: {tool_name}({tool_args})")

            tools_usadas.append({"nombre": tool_name, "args": tool_args})

            # Ejecutar la tool
            if tool_name not in TOOLS_MAP:
                tool_result = {"error": f"Tool '{tool_name}' no existe"}
            else:
                try:
                    result = TOOLS_MAP[tool_name](**tool_args)
                    tool_result = result if result is not None else {"sin_resultados": True}
                except Exception as e:
                    tool_result = {"error": str(e)}

            if verbose:
                preview = json.dumps(tool_result, ensure_ascii=False, default=str)[:120]
                print(f"     ✅ Resultado: {preview}...")

            # Pasar el resultado de vuelta al modelo
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(tool_result, ensure_ascii=False, default=str),
            })

    # Si llegamos acá, el modelo entró en loop
    return {
        "respuesta_texto": "Disculpá, tuve un problema procesando tu consulta. ¿Podés reformular?",
        "tools_usadas": tools_usadas,
        "tokens_usados": tokens_total,
        "iteraciones": max_iteraciones,
        "warning": "max_iteraciones_alcanzado",
    }