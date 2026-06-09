"""
functions/catalog_tools.py
Las 5 tools que el agente Producto puede invocar para responder al cliente.
Cada función llama a una RPC de Supabase (ya cargadas) y formatea la respuesta
en un dict serializable que el LLM pueda interpretar.
"""
from __future__ import annotations

import os
from typing import Optional

from functions.db import get_client


def buscar_producto(
    query: str,
    marca_pieza: Optional[str] = None,
    linea: Optional[str] = None,
    limit: int = 5,
    empresa_id: Optional[int] = None,
) -> list[dict]:
    """
    Búsqueda full-text por descripción del producto.

    Args:
        query: lo que el cliente busca, ej: "pastillas de freno cerámicas".
        marca_pieza: filtrar por marca del fabricante (Bosch, Sachs, ...).
        linea: filtrar por sistema (frenos, suspension, embrague, ...).
        limit: cuántos resultados devolver (default 5).
        empresa_id: si no se pasa, usa EMPRESA_ID_PILOTO del .env.

    Returns:
        Lista de productos matching, con stock y precio mínimo si están disponibles.
    """
    sb = get_client()
    empresa_id = empresa_id or int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

    response = sb.rpc("rpc_buscar_producto", {
        "p_empresa_id": empresa_id,
        "p_query": query,
        "p_marca_pieza": marca_pieza,
        "p_linea": linea,
        "p_limit": limit,
    }).execute()

    return response.data or []


def buscar_por_aplicacion(
    marca: str,
    modelo: str,
    anio: int,
    motor: Optional[str] = None,
    posicion: Optional[str] = None,
    linea: Optional[str] = None,
    limit: int = 5,
    empresa_id: Optional[int] = None,
) -> list[dict]:
    """
    Búsqueda por vehículo: "qué tengo para un VW Gol 2010".

    Args:
        marca: marca del auto (VW, Ford, Renault...).
        modelo: modelo (Gol, Fiesta, Clio...).
        anio: año del vehículo.
        motor: cilindrada/version opcional (1.6, 1.4 TDI).
        posicion: delantera/trasera/superior/inferior.
        linea: filtrar por sistema.
    """
    sb = get_client()
    empresa_id = empresa_id or int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

    response = sb.rpc("rpc_buscar_por_aplicacion", {
        "p_empresa_id": empresa_id,
        "p_marca": marca,
        "p_modelo": modelo,
        "p_anio": anio,
        "p_motor": motor,
        "p_posicion": posicion,
        "p_linea": linea,
        "p_limit": limit,
    }).execute()

    return response.data or []


def buscar_equivalencia(
    codigo: str,
    empresa_id: Optional[int] = None,
) -> list[dict]:
    """
    Buscar producto por código OEM o cruzada (ej: cliente trae el código del
    fabricante original y queremos saber qué producto del catálogo lo reemplaza).
    """
    sb = get_client()
    empresa_id = empresa_id or int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

    response = sb.rpc("rpc_buscar_equivalencia", {
        "p_empresa_id": empresa_id,
        "p_codigo": codigo,
    }).execute()

    return response.data or []


def consultar_precio(
    producto_id: int,
    empresa_id: Optional[int] = None,
) -> Optional[dict]:
    """
    Devolver el precio final aplicando las reglas configuradas
    (especificidad CSS-style: producto > marca > linea > global).
    """
    sb = get_client()
    empresa_id = empresa_id or int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

    response = sb.rpc("rpc_consultar_precio", {
        "p_empresa_id": empresa_id,
        "p_producto_id": producto_id,
    }).execute()

    if response.data:
        return response.data[0]
    return None


def consultar_stock(
    producto_id: int,
    empresa_id: Optional[int] = None,
) -> dict:
    """
    Stock agregado por todas las fuentes para un producto.
    """
    sb = get_client()
    empresa_id = empresa_id or int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

    # Sumar el stock de todas las ofertas del producto
    response = (
        sb.table("oferta")
          .select("stock, deposito, fuente_id, codigo_en_fuente")
          .eq("producto_id", producto_id)
          .execute()
    )
    ofertas = response.data or []
    total = sum(o.get("stock") or 0 for o in ofertas)

    return {
        "producto_id": producto_id,
        "stock_total": total,
        "ofertas": ofertas,
        "hay_stock": total > 0,
    }


# Mapa de tools para registrar en el agente
TOOLS_MAP = {
    "buscar_producto": buscar_producto,
    "buscar_por_aplicacion": buscar_por_aplicacion,
    "buscar_equivalencia": buscar_equivalencia,
    "consultar_precio": consultar_precio,
    "consultar_stock": consultar_stock,
}
