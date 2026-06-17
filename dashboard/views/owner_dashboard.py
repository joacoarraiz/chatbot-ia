"""
dashboard/views/owner_dashboard.py
Vista global para el dueño del producto (super_admin).
Metricas agregadas de todas las empresas.
"""
from __future__ import annotations

import streamlit as st
from dashboard.lib.db_dash import get_owner_metrics


st.title("👑 Vista de dueños")
st.caption("Metricas globales de Toni: todas las empresas del sistema.")
st.divider()

m = get_owner_metrics()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Empresas totales", m["total_empresas"])
col2.metric("Empresas activas", m["empresas_activas"])
col3.metric("Consultas totales", m["total_consultas"])
col4.metric("Costo IA total", f"US$ {m['costo_ia_total']}")

st.divider()

st.subheader("Empresas del sistema")
empresas = m["empresas"]
if empresas:
    data = [{
        "ID": e.get("id"),
        "Nombre": e.get("nombre"),
        "Plan": e.get("plan", "-"),
        "Estado": e.get("estado", "-"),
        "Limite consultas": e.get("consultas_limite", "-"),
        "Creada": e.get("creado_at", "")[:10] if e.get("creado_at") else "-",
    } for e in empresas]
    st.dataframe(data, use_container_width=True, hide_index=True)
else:
    st.info("No hay empresas.")

st.divider()
st.caption("💡 Proximamente: MRR, costo por consulta agregado, riesgo de churn por empresa.")