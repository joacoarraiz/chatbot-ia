"""
functions/config_tools.py
Tool para que el agente FAQ lea la config del negocio (config_negocio):
horarios detallados, servicios, web, redes y feriados.

Complementa a consultar_info_empresa (que lee empresa.persona_config con
envios, pagos, telefono, marcas). Linea divisoria: horarios y servicios
mandan desde ACA (config_negocio).
"""
from __future__ import annotations

from functions.db import get_client

# Mapa dias cortos -> nombre lindo, para armar respuestas legibles
_DIAS_LINDO = {
    "lun": "lunes", "mar": "martes", "mie": "miércoles",
    "jue": "jueves", "vie": "viernes", "sab": "sábado", "dom": "domingo",
}


def consultar_config_negocio(empresa_id, campo=None):
    """
    Devuelve la config del negocio desde config_negocio.
    - Sin 'campo': trae todo (horarios, servicios, web, instagram, feriados).
    - Con 'campo': trae solo ese ('horarios', 'servicios', 'web', 'instagram',
      'direccion', 'atiende_feriados').

    empresa_id lo pasa el agente desde el contexto de la conversacion.
    """
    sb = get_client()
    try:
        r = (
            sb.table("config_negocio")
            .select("web, instagram, direccion, horarios, atiende_feriados, servicios")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        return {"error": str(e)}

    if not r.data:
        return {"sin_config": True, "mensaje": "Este comercio todavia no cargo su configuracion."}

    cfg = r.data[0]

    # Enriquecemos los servicios con los dias en formato lindo, para que el
    # agente pueda decir "de lunes a sabado" sin tener que traducir el.
    servicios = cfg.get("servicios") or []
    for s in servicios:
        dias = s.get("dias") or []
        s["dias_texto"] = ", ".join(_DIAS_LINDO.get(d, d) for d in dias)

    resultado = {
        "web": cfg.get("web"),
        "instagram": cfg.get("instagram"),
        "direccion": cfg.get("direccion"),
        "horarios": cfg.get("horarios"),
        "atiende_feriados": cfg.get("atiende_feriados"),
        "servicios": servicios,
    }

    if campo:
        return {campo: resultado.get(campo)}
    return resultado


TOOLS_MAP = {
    "consultar_config_negocio": consultar_config_negocio,
}