"""
dashboard/views/derivaciones.py
Bandeja de derivaciones: conversaciones que el bot paso a un humano.
Ordenadas por prioridad. El operador las marca como resueltas.
"""
from __future__ import annotations

import streamlit as st
from dashboard.lib.db_dash import get_derivaciones, marcar_derivacion_resuelta


# Detectar empresa del usuario
def _empresa_id():
    roles = st.session_state.get("roles", [])
    for r in roles:
        if r.get("empresa_id"):
            return r["empresa_id"]
    # super_admin sin empresa: usar piloto por defecto
    import os
    return int(os.environ.get("EMPRESA_ID_PILOTO", "1"))


empresa_id = _empresa_id()

st.title("🤝 Bandeja de derivaciones")
st.caption("Conversaciones que necesitan atencion humana.")

# Toggle pendientes / todas
col_f1, col_f2 = st.columns([1, 3])
with col_f1:
    solo_pendientes = st.toggle("Solo pendientes", value=True)

derivaciones = get_derivaciones(empresa_id, solo_pendientes=solo_pendientes)

if not derivaciones:
    st.success("No hay derivaciones pendientes. El bot esta resolviendo todo solo. 🎉")
    st.stop()

# Orden por prioridad
orden_prioridad = {"urgente": 0, "alta": 1, "normal": 2}
derivaciones.sort(key=lambda d: orden_prioridad.get(d.get("prioridad", "normal"), 3))

st.caption(f"{len(derivaciones)} derivacion(es)")
st.divider()

# Colores por prioridad
colores = {"urgente": "🔴", "alta": "🟠", "normal": "🔵"}

for d in derivaciones:
    prioridad = d.get("prioridad", "normal")
    emoji = colores.get(prioridad, "⚪")
    resuelta = d.get("resuelta_at") is not None

    with st.container(border=True):
        col_info, col_accion = st.columns([4, 1])

        with col_info:
            estado_txt = "✅ Resuelta" if resuelta else f"{emoji} {prioridad.upper()}"
            st.markdown(f"**{d.get('cliente_nombre', 'Cliente')}** · {estado_txt}")
            st.caption(f"Tipo cliente: {d.get('cliente_tipo', '-')} · Creada: {d.get('creado_at', '')[:16].replace('T', ' ')}")
            st.markdown(f"**Motivo:** {d.get('motivo', '-')}")
            st.info(d.get("resumen", "Sin resumen"))
            if resuelta and d.get("resolucion"):
                st.success(f"Resolucion: {d['resolucion']}")

        with col_accion:
            if not resuelta:
                if st.button("Marcar resuelta", key=f"resolver_{d['id']}", use_container_width=True):
                    st.session_state[f"resolviendo_{d['id']}"] = True

                if st.session_state.get(f"resolviendo_{d['id']}"):
                    nota = st.text_input("Nota (opcional)", key=f"nota_{d['id']}", placeholder="Como se resolvio")
                    if st.button("Confirmar", key=f"confirmar_{d['id']}", type="primary", use_container_width=True):
                        marcar_derivacion_resuelta(d["id"], nota)
                        st.session_state[f"resolviendo_{d['id']}"] = False
                        st.rerun()