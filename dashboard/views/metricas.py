"""
dashboard/views/metricas.py
Dashboard principal del comercio: metricas clave + graficos.
"""
from __future__ import annotations

import streamlit as st
from dashboard.lib.db_dash import (
    get_metricas_resumen, get_consultas_por_dia, get_intenciones_distribucion
)


def _empresa_id():
    roles = st.session_state.get("roles", [])
    for r in roles:
        if r.get("empresa_id"):
            return r["empresa_id"]
    import os
    return int(os.environ.get("EMPRESA_ID_PILOTO", "1"))


empresa_id = _empresa_id()

st.title("📊 Dashboard")
st.caption("Resumen de la actividad de tu bot.")
st.divider()

# ===== METRICAS PRINCIPALES =====
m = get_metricas_resumen(empresa_id)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Consultas este mes", m["consultas_mes"])
col2.metric("Score del bot", f"{m['score_promedio']}/100")
col3.metric("Derivaciones pendientes", m["derivaciones_pendientes"])
col4.metric("Costo IA del mes", f"US$ {m['costo_ia_mes']}")

col5, col6, col7, col8 = st.columns(4)
col5.metric("Clientes totales", m["total_clientes"])
col6.metric("Pedidos", m["total_pedidos"])
col7.metric("Ventas (pedidos)", f"$ {m['monto_pedidos']:,.0f}")
conversion = round(100 * m["total_pedidos"] / m["consultas_mes"]) if m["consultas_mes"] else 0
col8.metric("Conversion aprox", f"{conversion}%")

st.divider()

# ===== GRAFICO: consultas por dia =====
st.subheader("Consultas por dia (ultimos 14 dias)")
datos_dia = get_consultas_por_dia(empresa_id, dias=14)
if datos_dia:
    import pandas as pd
    df = pd.DataFrame(datos_dia)
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%d/%m")
    df = df.set_index("fecha")
    st.bar_chart(df["consultas"], height=250)
else:
    st.info("Sin datos de consultas todavia.")

st.divider()

# ===== GRAFICO: distribucion de intenciones =====
st.subheader("Que consultan tus clientes")
intenciones = get_intenciones_distribucion(empresa_id)
if intenciones:
    import pandas as pd
    df_int = pd.DataFrame(intenciones).set_index("intencion")
    st.bar_chart(df_int["cantidad"], height=250, horizontal=True)
else:
    st.info("Sin datos de intenciones todavia.")