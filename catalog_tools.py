"""
functions/catalog_tools.py
Tools de catálogo: búsqueda de productos, aplicaciones, equivalencias,
stock y precio. Las usan los agentes Producto y Cotización.

Cada función devuelve un dict JSON-serializable. Nunca lanza al agente.
"""
from __future__ import annotations

from typing import Any

from functions.db import get_client


# ---------- Búsqueda por texto ----------

def buscar_producto(
    empresa_id: int,
    descripcion: str,
    marca_pieza: str | None = None,
    linea: str | None = None,
    limit: int = 5,
) -> dict:
    """
    Búsqueda full-text en español sobre `producto_logico.descripcion`.
    Usa el índice GIN de tsvector definido en 01_catalog.sql.

    Devuelve top N matches con stock total y precio mínimo con stock.
    """
    try:
        db = get_client()
        # Llamamos a una RPC creada en Supabase (ver functions/_rpcs/search_products.sql)
        result = db.rpc(
            "rpc_buscar_producto",
            {
                "p_empresa_id": empresa_id,
                "p_query": descripcion,
                "p_marca_pieza": marca_pieza,
                "p_linea": linea,
                "p_limit": limit,
            },
        ).execute()
        return {"resultados": result.data or []}
    except Exception as e:
        return {"error": f"buscar_producto falló: {str(e)[:200]}"}


# ---------- Búsqueda por aplicación (la más usada) ----------

def buscar_por_aplicacion(
    empresa_id: int,
    auto_marca: str,
    modelo: str,
    anio: int,
    motor: str | None = None,
    posicion: str | None = None,
    linea: str | None = None,
    limit: int = 5,
) -> dict:
    """
    Busca productos compatibles con un vehículo específico.
    Joinea producto_logico ⨝ aplicacion con rango de años.
    """
    try:
        db = get_client()
        result = db.rpc(
            "rpc_buscar_por_aplicacion",
            {
                "p_empresa_id": empresa_id,
                "p_marca": auto_marca,
                "p_modelo": modelo,
                "p_anio": anio,
                "p_motor": motor,
                "p_posicion": posicion,
                "p_linea": linea,
                "p_limit": limit,
            },
        ).execute()
        return {"resultados": result.data or []}
    except Exception as e:
        return {"error": f"buscar_por_aplicacion falló: {str(e)[:200]}"}


# ---------- Búsqueda por código (equivalencias) ----------

def buscar_equivalencia(empresa_id: int, codigo_externo: str) -> dict:
    """
    Dado un código OEM o de marca externa, encuentra el producto lógico
    equivalente del catálogo del comercio.
    """
    try:
        db = get_client()
        result = db.rpc(
            "rpc_buscar_equivalencia",
            {"p_empresa_id": empresa_id, "p_codigo": codigo_externo},
        ).execute()
        return {"resultados": result.data or []}
    except Exception as e:
        return {"error": f"buscar_equivalencia falló: {str(e)[:200]}"}


# ---------- Stock ----------

def consultar_stock(producto_id: int) -> dict:
    try:
        db = get_client()
        result = (
            db.table("oferta")
              .select("fuente_id, codigo_en_fuente, stock, deposito")
              .eq("producto_id", producto_id)
              .gt("stock", 0)
              .execute()
        )
        ofertas = result.data or []
        total = sum(o["stock"] for o in ofertas)
        return {
            "producto_id": producto_id,
            "stock_total": total,
            "ofertas": ofertas,
        }
    except Exception as e:
        return {"error": f"consultar_stock falló: {str(e)[:200]}"}


# ---------- Precio (con reglas) ----------

def consultar_precio(empresa_id: int, producto_id: int) -> dict:
    """
    Aplica las reglas de precio del comercio y devuelve el precio recomendado.
    La lógica vive en una función Postgres (más rápida y atómica).
    """
    try:
        db = get_client()
        result = db.rpc(
            "rpc_consultar_precio",
            {"p_empresa_id": empresa_id, "p_producto_id": producto_id},
        ).execute()
        if not result.data:
            return {"error": "sin oferta disponible"}
        return result.data[0] if isinstance(result.data, list) else result.data
    except Exception as e:
        return {"error": f"consultar_precio falló: {str(e)[:200]}"}
