"""
functions/order_tools.py
Tools que usan los agentes Cotización, Pedido y Derivación.
"""
from __future__ import annotations

import os
from typing import Optional

from functions.db import get_client


def armar_pedido(
    cliente_id: int,
    items: list[dict],
    consulta_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
) -> dict:
    """
    Crea un pedido en estado 'borrador' con los items que el cliente quiere.

    Args:
        cliente_id: cliente que pide.
        items: lista de {producto_id, cantidad, precio_unitario}.
        consulta_id: la consulta de la que salió el pedido (opcional).
    """
    sb = get_client()
    empresa_id = empresa_id or int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

    total = sum(i["cantidad"] * i["precio_unitario"] for i in items)

    pedido = sb.table("pedido").insert({
        "empresa_id": empresa_id,
        "cliente_id": cliente_id,
        "consulta_id": consulta_id,
        "total": total,
        "estado": "borrador",
    }).execute()

    pedido_id = pedido.data[0]["id"]

    items_data = [{
        "pedido_id": pedido_id,
        "producto_id": i["producto_id"],
        "cantidad": i["cantidad"],
        "precio_unitario": i["precio_unitario"],
    } for i in items]

    sb.table("pedido_item").insert(items_data).execute()

    return {"pedido_id": pedido_id, "total": total, "items": len(items)}


def consultar_pedido(
    pedido_id: int,
    empresa_id: Optional[int] = None,
) -> Optional[dict]:
    """Estado actual de un pedido."""
    sb = get_client()
    empresa_id = empresa_id or int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

    pedido = (
        sb.table("pedido")
          .select("*, pedido_item(*)")
          .eq("id", pedido_id)
          .eq("empresa_id", empresa_id)
          .single()
          .execute()
    )
    return pedido.data


def derivar_humano(
    consulta_id: int,
    motivo: str,
    resumen_contexto: str,
    valor_cotizado: Optional[float] = None,
) -> dict:
    """
    Crear una derivación para que un humano retome la conversación.
    El resumen_contexto es CRÍTICO porque el vendedor lo lee antes
    de tomar la conversación.
    """
    sb = get_client()

    derivacion = sb.table("derivacion").insert({
        "consulta_id": consulta_id,
        "motivo": motivo,
        "resumen_contexto": resumen_contexto,
        "valor_cotizado": valor_cotizado,
        "estado": "pendiente",
    }).execute()

    return {"derivacion_id": derivacion.data[0]["id"], "estado": "pendiente"}


TOOLS_MAP = {
    "armar_pedido": armar_pedido,
    "consultar_pedido": consultar_pedido,
    "derivar_humano": derivar_humano,
}
