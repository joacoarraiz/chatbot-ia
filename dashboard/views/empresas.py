"""
dashboard/views/empresas.py
Gestion de empresas. Solo super_admin (el control de acceso lo hace
streamlit_app.py via st.navigation).
"""
from __future__ import annotations

import streamlit as st
from dashboard.lib.auth import usuario_logueado
from dashboard.lib.invitaciones import (
    listar_empresas,
    crear_empresa,
    generar_invitacion,
    listar_invitaciones_empresa,
)


st.title("🏢 Gestion de empresas")
st.caption("Como super admin, podes ver todas las empresas y crear nuevas.")
st.divider()

tab_lista, tab_crear, tab_invitar = st.tabs([
    "📋 Lista de empresas",
    "➕ Crear nueva",
    "📨 Invitar admin",
])


# ===== TAB 1: LISTA =====
with tab_lista:
    st.subheader("Empresas registradas")
    empresas = listar_empresas()
    if not empresas:
        st.info("No hay empresas todavia.")
    else:
        data = []
        for e in empresas:
            data.append({
                "ID": e.get("id", "-"),
                "Nombre": e.get("nombre", "(sin nombre)"),
                "Plan": e.get("plan", "-"),
                "Limite consultas": e.get("consultas_limite", "-"),
                "Estado": e.get("estado", "activa"),
                "Creada": e["creado_at"][:10] if e.get("creado_at") else "-",
            })
        st.dataframe(data, use_container_width=True, hide_index=True)


# ===== TAB 2: CREAR =====
with tab_crear:
    st.subheader("Crear nueva empresa")
    st.caption("Se va a crear con plan basico y limite de 1500 consultas mensuales.")
    nombre = st.text_input("Nombre comercial *", placeholder="Ej: Repuestos Pepito")
    col1, col2 = st.columns(2)
    with col1:
        plan = st.selectbox("Plan", ["basico", "intermedio", "avanzado"])
    with col2:
        limite = st.number_input("Limite consultas/mes", min_value=100, value=1500, step=100)

    if st.button("Crear empresa", type="primary", use_container_width=True):
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
        else:
            try:
                with st.spinner("Creando empresa..."):
                    empresa = crear_empresa(
                        nombre=nombre.strip(), plan=plan, consultas_limite=int(limite),
                    )
                st.success(f"Empresa creada: **{empresa['nombre']}** (id #{empresa['id']})")
                st.balloons()
            except Exception as e:
                st.error(f"Error: {e}")


# ===== TAB 3: INVITAR =====
with tab_invitar:
    st.subheader("Invitar admin a una empresa")
    st.caption("Generamos un link unico que tenes que mandar por WhatsApp al nuevo admin.")
    empresas = listar_empresas()
    if not empresas:
        st.info("Crea una empresa primero.")
    else:
        opciones = {f"#{e['id']} - {e['nombre']}": e["id"] for e in empresas}
        empresa_seleccion = st.selectbox("Empresa", list(opciones.keys()))
        empresa_id = opciones[empresa_seleccion]
        email_invitado = st.text_input("Email del invitado *", placeholder="admin@comercio.com")
        rol = st.selectbox("Rol", ["comercio_admin", "comercio_operador", "comercio_viewer"])

        if st.button("Generar link de invitacion", type="primary", use_container_width=True):
            if not email_invitado.strip():
                st.error("El email es obligatorio.")
            else:
                try:
                    user = usuario_logueado()
                    with st.spinner("Generando..."):
                        inv = generar_invitacion(
                            empresa_id=empresa_id,
                            email_invitado=email_invitado.strip(),
                            rol=rol,
                            invitado_por_user_id=user["id"],
                        )
                    st.success("Invitacion creada. Copialo y mandalo por WhatsApp:")
                    st.code(inv["url_completa"], language=None)
                    st.caption(f"Expira el: {inv['expira_at'][:19].replace('T', ' a las ')}")
                except Exception as e:
                    st.error(f"Error: {e}")

        st.divider()
        st.subheader(f"Invitaciones pendientes")
        invs = listar_invitaciones_empresa(empresa_id)
        pendientes = [i for i in invs if not i.get("usada_at")]
        if pendientes:
            for inv in pendientes:
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.write(f"📧 {inv['email']}")
                c2.caption(f"Rol: {inv['rol']}")
                c3.caption(f"Expira: {inv['expira_at'][:10]}")
        else:
            st.info("No hay invitaciones pendientes.")