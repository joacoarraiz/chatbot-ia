"""
functions/config_tools.py
Tool para que el agente FAQ lea la config del negocio (config_negocio):
horarios detallados, servicios, web, redes, feriados y dias cerrados puntuales.

Complementa a consultar_info_empresa (que lee empresa.persona_config con
envios, pagos, telefono, marcas). Linea divisoria: horarios y servicios
mandan desde ACA (config_negocio).
"""
from __future__ import annotations

from datetime import date, timedelta

from functions.db import get_client

# Mapa dias cortos -> nombre lindo, para armar respuestas legibles
_DIAS_LINDO = {
    "lun": "lunes", "mar": "martes", "mie": "miércoles",
    "jue": "jueves", "vie": "viernes", "sab": "sábado", "dom": "domingo",
}


def consultar_config_negocio(empresa_id, campo=None):
    """
    Devuelve la config del negocio desde config_negocio.
    - Sin 'campo': trae todo (horarios, servicios, web, instagram, feriados, dias_cerrados).
    - Con 'campo': trae solo ese ('horarios', 'servicios', 'web', 'instagram',
      'direccion', 'atiende_feriados', 'dias_cerrados').

    Ademas calcula si HOY y MAÑANA caen en un dia cerrado, asi el agente
    puede responder "abren mañana?" sin hacer cuentas de fechas.

    empresa_id lo pasa el agente desde el contexto de la conversacion.
    """
    sb = get_client()
    try:
        r = (
            sb.table("config_negocio")
            .select("web, instagram, direccion, horarios, atiende_feriados, servicios, dias_cerrados")
            .eq("empresa_id", empresa_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        return {"error": str(e)}

    if not r.data:
        return {"sin_config": True, "mensaje": "Este comercio todavia no cargo su configuracion."}

    cfg = r.data[0]

    # Servicios con dias en formato lindo
    servicios = cfg.get("servicios") or []
    for s in servicios:
        dias = s.get("dias") or []
        s["dias_texto"] = ", ".join(_DIAS_LINDO.get(d, d) for d in dias)

    # Dias cerrados puntuales + calculo de hoy/mañana
    dias_cerrados = cfg.get("dias_cerrados") or []
    hoy = date.today()
    manana = hoy + timedelta(days=1)
    hoy_str = hoy.isoformat()
    manana_str = manana.isoformat()

    resultado = {
        "web": cfg.get("web"),
        "instagram": cfg.get("instagram"),
        "direccion": cfg.get("direccion"),
        "horarios": cfg.get("horarios"),
        "atiende_feriados": cfg.get("atiende_feriados"),
        "servicios": servicios,
        "dias_cerrados": dias_cerrados,
        "fecha_hoy": hoy_str,
        "fecha_manana": manana_str,
        "cerrado_hoy": hoy_str in dias_cerrados,
        "cerrado_manana": manana_str in dias_cerrados,
    }

    if campo:
        return {campo: resultado.get(campo)}
    return resultado


TOOLS_MAP = {
    "consultar_config_negocio": consultar_config_negocio,
}