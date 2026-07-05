"""
functions/vehiculo_tools.py
Tools de vehiculos para el agente Producto.

Consultan la tabla de referencia parque_vehiculos (via las RPC
rpc_buscar_vehiculo y rpc_modelos_de_marca) para DESAMBIGUAR el auto del
cliente ANTES de buscar el repuesto en el catalogo.

Entienden modismos y marcas mal escritas: la RPC normaliza sola
('reno' -> RENAULT, 'vw' -> VOLKSWAGEN, 'bolbagen' -> VOLKSWAGEN, etc.).
"""
from __future__ import annotations

from functions.db import get_client


def ver_versiones_auto(marca, modelo=None, version=None, limit=25):
    """
    Devuelve las versiones/motores que existen para una marca (+ modelo),
    para que Toni pueda preguntar 'cual?' con opciones reales del parque.
    Saca duplicados de version/motor asi la lista queda limpia.
    """
    sb = get_client()
    try:
        r = sb.rpc("rpc_buscar_vehiculo", {
            "p_marca": marca,
            "p_modelo": modelo,
            "p_version": version,
            "p_limite": limit,
        }).execute()
        filas = r.data or []
    except Exception as e:
        return {"error": str(e)}

    vistos = set()
    opciones = []
    for f in filas:
        clave = (f.get("model_range"), f.get("version"), f.get("codigo_motor"), f.get("cilindrada_lts"))
        if clave in vistos:
            continue
        vistos.add(clave)
        opciones.append({
            "modelo": f.get("model_range") or f.get("modelo"),
            "version": f.get("version"),
            "motor": f.get("codigo_motor"),
            "cilindrada": f.get("cilindrada_lts"),
            "combustible": f.get("combustible"),
        })

    return {"cantidad": len(opciones), "opciones": opciones}


def ver_modelos_marca(marca):
    """
    Devuelve los modelos que tiene una marca (con cuantas versiones cada uno),
    para cuando el cliente solo nombra la marca ('tengo una Renault').
    """
    sb = get_client()
    try:
        r = sb.rpc("rpc_modelos_de_marca", {"p_marca": marca}).execute()
        return {"modelos": r.data or []}
    except Exception as e:
        return {"error": str(e)}


VEHICULO_TOOLS_MAP = {
    "ver_versiones_auto": ver_versiones_auto,
    "ver_modelos_marca": ver_modelos_marca,
}