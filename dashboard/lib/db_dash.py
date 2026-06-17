"""
dashboard/lib/db_dash.py
Queries del dashboard. Usan service_role para leer datos
(el control de acceso por empresa lo maneja la capa de auth + el filtro
explicito por empresa_id en cada query).
"""
from __future__ import annotations

import os
from supabase import create_client, Client


def _sb() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


# ============ DERIVACIONES ============
def get_derivaciones(empresa_id: int, solo_pendientes: bool = True) -> list[dict]:
    """
    Trae derivaciones de una empresa, con datos del cliente.
    Saltamos por conversacion -> cliente.
    """
    sb = _sb()
    # Primero las conversaciones de la empresa
    convs = sb.table("conversacion").select("id, cliente_id").eq("empresa_id", empresa_id).execute()
    conv_map = {c["id"]: c["cliente_id"] for c in (convs.data or [])}
    if not conv_map:
        return []

    q = sb.table("derivacion").select("*").in_("conversacion_id", list(conv_map.keys()))
    if solo_pendientes:
        q = q.is_("resuelta_at", "null")
    derivaciones = q.order("creado_at", desc=True).execute().data or []

    # Enriquecer con nombre de cliente
    cliente_ids = list({conv_map.get(d["conversacion_id"]) for d in derivaciones if conv_map.get(d["conversacion_id"])})
    clientes_map = {}
    if cliente_ids:
        clientes = sb.table("cliente").select("id, nombre, tipo").in_("id", cliente_ids).execute()
        clientes_map = {c["id"]: c for c in (clientes.data or [])}

    for d in derivaciones:
        cid = conv_map.get(d["conversacion_id"])
        cli = clientes_map.get(cid, {})
        d["cliente_nombre"] = cli.get("nombre", "Desconocido")
        d["cliente_tipo"] = cli.get("tipo", "-")
    return derivaciones


def marcar_derivacion_resuelta(derivacion_id: int, resolucion: str) -> bool:
    from datetime import datetime, timezone
    sb = _sb()
    sb.table("derivacion").update({
        "resuelta_at": datetime.now(timezone.utc).isoformat(),
        "resolucion": resolucion or "Resuelta desde el dashboard.",
    }).eq("id", derivacion_id).execute()
    return True


# ============ METRICAS ============
def get_metricas_resumen(empresa_id: int) -> dict:
    """Devuelve las metricas clave de una empresa."""
    sb = _sb()
    from datetime import datetime, timezone

    # Consultas del mes actual
    inicio_mes = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    consultas_mes = sb.table("consulta").select("id, costo_ia_usd, resultado, monto_cotizado", count="exact").eq("empresa_id", empresa_id).gte("iniciada_at", inicio_mes.isoformat()).execute()
    n_consultas = consultas_mes.count or 0

    # Costo IA total del mes
    costo_total = sum(float(c.get("costo_ia_usd") or 0) for c in (consultas_mes.data or []))

    # Derivaciones pendientes
    convs = sb.table("conversacion").select("id").eq("empresa_id", empresa_id).execute()
    conv_ids = [c["id"] for c in (convs.data or [])]
    n_derivaciones = 0
    if conv_ids:
        der = sb.table("derivacion").select("id", count="exact").in_("conversacion_id", conv_ids).is_("resuelta_at", "null").execute()
        n_derivaciones = der.count or 0

    # Score promedio
    consulta_ids_all = sb.table("consulta").select("id").eq("empresa_id", empresa_id).execute()
    cids = [c["id"] for c in (consulta_ids_all.data or [])]
    score_prom = 0
    if cids:
        scores = sb.table("score_consulta").select("score_total").in_("consulta_id", cids).execute()
        vals = [s["score_total"] for s in (scores.data or []) if s.get("score_total") is not None]
        score_prom = round(sum(vals) / len(vals)) if vals else 0

    # Total clientes
    n_clientes = sb.table("cliente").select("id", count="exact").eq("empresa_id", empresa_id).execute().count or 0

    # Pedidos y conversion
    pedidos = sb.table("pedido").select("id, monto_total, estado", count="exact").eq("empresa_id", empresa_id).execute()
    n_pedidos = pedidos.count or 0
    monto_pedidos = sum(float(p.get("monto_total") or 0) for p in (pedidos.data or []) if p.get("estado") in ("confirmado", "entregado"))

    return {
        "consultas_mes": n_consultas,
        "costo_ia_mes": round(costo_total, 2),
        "derivaciones_pendientes": n_derivaciones,
        "score_promedio": score_prom,
        "total_clientes": n_clientes,
        "total_pedidos": n_pedidos,
        "monto_pedidos": round(monto_pedidos, 2),
    }


def get_consultas_por_dia(empresa_id: int, dias: int = 14) -> list[dict]:
    """Cuenta consultas por dia de los ultimos N dias."""
    sb = _sb()
    from datetime import datetime, timezone, timedelta
    from collections import defaultdict

    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    consultas = sb.table("consulta").select("iniciada_at").eq("empresa_id", empresa_id).gte("iniciada_at", desde.isoformat()).execute()

    conteo = defaultdict(int)
    for c in (consultas.data or []):
        fecha = c["iniciada_at"][:10]
        conteo[fecha] += 1

    # Rellenar dias sin consultas con 0
    resultado = []
    for i in range(dias, -1, -1):
        dia = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        resultado.append({"fecha": dia, "consultas": conteo.get(dia, 0)})
    return resultado


def get_intenciones_distribucion(empresa_id: int) -> list[dict]:
    """Cuenta consultas por tipo de intencion."""
    sb = _sb()
    from collections import defaultdict
    consultas = sb.table("consulta").select("intencion").eq("empresa_id", empresa_id).execute()
    conteo = defaultdict(int)
    for c in (consultas.data or []):
        conteo[c.get("intencion", "desconocida")] += 1
    return [{"intencion": k, "cantidad": v} for k, v in sorted(conteo.items(), key=lambda x: -x[1])]


# ============ CLIENTES ============
def get_clientes(empresa_id: int) -> list[dict]:
    sb = _sb()
    clientes = sb.table("cliente").select("*").eq("empresa_id", empresa_id).order("ultima_actividad_at", desc=True).execute()
    return clientes.data or []


def get_cliente_detalle(cliente_id: int) -> dict:
    """Trae un cliente con sus vehiculos, canales, conversaciones y pedidos."""
    sb = _sb()
    cliente = sb.table("cliente").select("*").eq("id", cliente_id).single().execute().data

    vehiculos = sb.table("vehiculo_cliente").select("*").eq("cliente_id", cliente_id).execute().data or []
    canales = sb.table("contact_channel").select("*").eq("cliente_id", cliente_id).execute().data or []
    convs = sb.table("conversacion").select("*").eq("cliente_id", cliente_id).order("abierta_at", desc=True).execute().data or []
    pedidos = sb.table("pedido").select("*").eq("cliente_id", cliente_id).order("creado_at", desc=True).execute().data or []

    return {
        "cliente": cliente,
        "vehiculos": vehiculos,
        "canales": canales,
        "conversaciones": convs,
        "pedidos": pedidos,
    }


def get_mensajes_conversacion(conversacion_id: int) -> list[dict]:
    sb = _sb()
    msgs = sb.table("mensaje").select("*").eq("conversacion_id", conversacion_id).order("creado_at", desc=False).execute()
    return msgs.data or []


# ============ PREGUNTAS SIN RESOLVER ============
def get_preguntas_sin_resolver(empresa_id: int) -> list[dict]:
    """Consultas con resultado sin_resolver o score bajo, con oportunidades de mejora."""
    sb = _sb()
    cids_resp = sb.table("consulta").select("id, intencion, resultado, iniciada_at").eq("empresa_id", empresa_id).in_("resultado", ["sin_resolver", "derivada"]).order("iniciada_at", desc=True).execute()
    consultas = cids_resp.data or []

    # Traer oportunidades de mejora del score
    cids = [c["id"] for c in consultas]
    oportunidades_map = {}
    if cids:
        scores = sb.table("score_consulta").select("consulta_id, oportunidades_mejora, score_total").in_("consulta_id", cids).execute()
        for s in (scores.data or []):
            oportunidades_map[s["consulta_id"]] = {
                "oportunidades": s.get("oportunidades_mejora"),
                "score": s.get("score_total"),
            }

    for c in consultas:
        info = oportunidades_map.get(c["id"], {})
        c["oportunidades"] = info.get("oportunidades")
        c["score"] = info.get("score")
    return consultas


# ============ CONFIGURACION ============
def get_persona_config(empresa_id: int) -> dict:
    sb = _sb()
    emp = sb.table("empresa").select("persona_config").eq("id", empresa_id).single().execute().data
    return emp.get("persona_config") or {}


def update_persona_config(empresa_id: int, config: dict) -> bool:
    sb = _sb()
    sb.table("empresa").update({"persona_config": config}).eq("id", empresa_id).execute()
    return True


# ============ OWNER (super_admin) ============
def get_owner_metrics() -> dict:
    """Metricas globales para el dueño del producto."""
    sb = _sb()
    empresas = sb.table("empresa").select("*").execute().data or []
    n_empresas = len(empresas)
    activas = len([e for e in empresas if e.get("estado") == "activa"])

    # Consultas totales del sistema
    total_consultas = sb.table("consulta").select("id", count="exact").execute().count or 0

    # Costo IA total
    consultas_costo = sb.table("consulta").select("costo_ia_usd").execute().data or []
    costo_total = sum(float(c.get("costo_ia_usd") or 0) for c in consultas_costo)

    return {
        "total_empresas": n_empresas,
        "empresas_activas": activas,
        "total_consultas": total_consultas,
        "costo_ia_total": round(costo_total, 2),
        "empresas": empresas,
    }