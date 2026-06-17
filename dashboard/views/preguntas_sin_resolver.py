"""
dashboard/views/preguntas_sin_resolver.py
Las consultas que el bot no pudo resolver o derivó.
Inteligencia de negocio: donde estas perdiendo ventas.
"""
from __future__ import annotations

import streamlit as st
from dashboard.lib.db_dash import get_preguntas_sin_resolver


def _empresa_id():
    roles = st.session_state.get("roles", [])
    for r in roles:
        if r.get("empresa_id"):
            return r["empresa_id"]
    import os
    return int(os.environ.get("EMPRESA_ID_PILOTO", "1"))


empresa_id = _empresa_id()

st.title("❓ Preguntas que el bot no supo")
st.caption("Estas consultas no se resolvieron solas. Son oportunidades: lo que tus clientes buscan y no encuentran.")
st.divider()

preguntas = get_preguntas_sin_resolver(empresa_id)

if not preguntas:
    st.success("El bot esta resolviendo todas las consultas. 🎉")
    st.stop()

st.caption(f"{len(preguntas)} consulta(s) para revisar")

for p in preguntas:
    with st.container(border=True):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**Intencion:** {p.get('intencion', '-')} · **Resultado:** {p.get('resultado', '-')}")
            st.caption(f"Fecha: {p.get('iniciada_at', '')[:16].replace('T', ' ')}")
            # Oportunidades de mejora (viene como lista JSON)
            oportunidades = p.get("oportunidades")
            if oportunidades:
                if isinstance(oportunidades, list):
                    for o in oportunidades:
                        st.info(o)
                else:
                    st.info(str(oportunidades))
        with col2:
            score = p.get("score")
            if score is not None:
                st.metric("Score", f"{score}")