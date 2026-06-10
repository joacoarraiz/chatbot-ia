"""
functions/faq_tools.py
Tool que usa el agente FAQ para leer la info del comercio.
La info vive en empresa.persona_config (JSONB).
"""
from __future__ import annotations

import os
from typing import Optional

from functions.db import get_client


def consultar_info_empresa(
    campo: Optional[str] = None,
    empresa_id: Optional[int] = None,
) -> dict:
    """
    Devuelve info del comercio (horarios, dirección, pagos, etc).

    Args:
        campo: si se pasa, devuelve solo ese campo (ej: 'horario').
               Si no, devuelve todos los campos disponibles.
        empresa_id: usa EMPRESA_ID_PILOTO del .env si no se pasa.
    """
    sb = get_client()
    empresa_id = empresa_id or int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

    response = (
        sb.table("empresa")
          .select("nombre, persona_config")
          .eq("id", empresa_id)
          .single()
          .execute()
    )

    if not response.data:
        return {"error": f"No se encontró la empresa con id={empresa_id}"}

    persona = response.data.get("persona_config", {}) or {}

    if campo:
        valor = persona.get(campo)
        if valor is None:
            return {
                "campo": campo,
                "valor": None,
                "mensaje": f"No tengo cargada la info de '{campo}'. Disponibles: {list(persona.keys())}",
            }
        return {"campo": campo, "valor": valor}

    # Sin campo específico: devolver toda la info "vendible" (oculto el tono)
    info_visible = {k: v for k, v in persona.items() if k not in ("tono", "permite_alternativas")}
    return {
        "nombre": response.data["nombre"],
        "info": info_visible,
    }


# Mapa de tools para registrar en el agente FAQ
TOOLS_MAP = {
    "consultar_info_empresa": consultar_info_empresa,
}