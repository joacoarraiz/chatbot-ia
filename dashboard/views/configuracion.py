"""
dashboard/views/configuracion.py
Editar el persona_config del bot: tono, datos del negocio.
Solo comercio_admin y super_admin.
"""
from __future__ import annotations

import json
import streamlit as st
from dashboard.lib.db_dash import get_persona_config, update_persona_config


def _empresa_id():
    roles = st.session_state.get("roles", [])
    for r in roles:
        if r.get("empresa_id"):
            return r["empresa_id"]
    import os
    return int(os.environ.get("EMPRESA_ID_PILOTO", "1"))


empresa_id = _empresa_id()

st.title("⚙️ Configuracion del bot")
st.caption("Editá como se comporta y que datos conoce tu bot.")
st.divider()

config = get_persona_config(empresa_id)

# Campos comunes (con defaults si no existen)
st.subheader("Datos del negocio")
nombre_comercial = st.text_input("Nombre comercial", value=config.get("nombre_comercial", ""))
horario = st.text_input("Horario de atencion", value=config.get("horario", ""), placeholder="Ej: Lun a Vie 9 a 18hs")
direccion = st.text_input("Direccion", value=config.get("direccion", ""), placeholder="Ej: Av. Colon 1234, Mar del Plata")
telefono = st.text_input("Telefono de contacto", value=config.get("telefono", ""))

st.subheader("Formas de pago y envio")
formas_pago = st.text_area("Formas de pago", value=config.get("formas_pago", ""), placeholder="Efectivo, transferencia, tarjetas...")
envios = st.text_area("Politica de envios", value=config.get("envios", ""), placeholder="Envios a domicilio, retiro en local...")

st.subheader("Personalidad del bot")
tono = st.selectbox(
    "Tono",
    ["argentino_cercano", "formal", "neutro"],
    index=["argentino_cercano", "formal", "neutro"].index(config.get("tono", "argentino_cercano")) if config.get("tono") in ["argentino_cercano", "formal", "neutro"] else 0,
)
permite_alternativas = st.toggle(
    "Permitir que ofrezca productos alternativos",
    value=config.get("permite_alternativas", True),
)

st.divider()

if st.button("Guardar configuracion", type="primary", use_container_width=True):
    nuevo_config = dict(config)  # preservar campos que no editamos
    nuevo_config.update({
        "nombre_comercial": nombre_comercial,
        "horario": horario,
        "direccion": direccion,
        "telefono": telefono,
        "formas_pago": formas_pago,
        "envios": envios,
        "tono": tono,
        "permite_alternativas": permite_alternativas,
    })
    try:
        update_persona_config(empresa_id, nuevo_config)
        st.success("Configuracion guardada. El bot ya usa estos datos.")
    except Exception as e:
        st.error(f"Error: {e}")

# Ver el JSON completo (para debug / avanzados)
with st.expander("Ver configuracion completa (JSON)"):
    st.json(config)