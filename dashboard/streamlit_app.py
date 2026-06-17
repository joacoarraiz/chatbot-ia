"""
dashboard/streamlit_app.py
Router central del dashboard. Decide que paginas mostrar segun el rol.
Maneja login, aceptacion de invitaciones, y navegacion role-aware.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import streamlit as st
from dashboard.lib.auth import (
    login, logout, get_roles_del_usuario, usuario_logueado, es_super_admin
)
from dashboard.lib.invitaciones import validar_token_invitacion, aceptar_invitacion


st.set_page_config(page_title="Toni - Dashboard", page_icon="🤖", layout="wide")


# ============ HELPERS DE ROL ============
def empresa_id_activa() -> int | None:
    """Devuelve el empresa_id del primer rol de comercio del usuario."""
    roles = st.session_state.get("roles", [])
    for r in roles:
        if r.get("empresa_id"):
            return r["empresa_id"]
    return None


def tiene_rol(*roles_buscados) -> bool:
    roles = st.session_state.get("roles", [])
    return any(r["rol"] in roles_buscados for r in roles)


# ============ LOGIN ============
def pantalla_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🤖 Toni")
        st.caption("Dashboard de gestion")
        st.divider()
        email = st.text_input("Email", placeholder="tu@email.com", key="login_email")
        password = st.text_input("Contrasena", type="password", key="login_password")
        if st.button("Ingresar", use_container_width=True, type="primary"):
            if not email or not password:
                st.error("Completa email y contrasena.")
                return
            with st.spinner("Verificando..."):
                resultado = login(email, password)
            if resultado["exito"]:
                st.session_state["user"] = resultado["user"]
                st.session_state["session"] = resultado["session"]
                try:
                    st.session_state["roles"] = get_roles_del_usuario(
                        user_id=resultado["user"]["id"],
                        access_token=resultado["session"]["access_token"],
                    )
                except Exception as e:
                    st.session_state["roles"] = []
                    st.warning(f"No se pudieron cargar los roles: {e}")
                st.rerun()
            else:
                st.error(f"Error: {resultado['error']}")


# ============ ACEPTAR INVITACION ============
def pantalla_aceptar_invitacion(token: str):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🤖 Toni")
        st.caption("Aceptar invitacion")
        st.divider()
        invitacion = validar_token_invitacion(token)
        if not invitacion:
            st.error("Este link de invitacion no es valido.")
            st.caption("Puede estar usado, expirado o mal copiado.")
            if st.button("Ir al login"):
                st.query_params.clear()
                st.rerun()
            return

        empresa_data = invitacion.get("empresa")
        empresa_nombre = empresa_data.get("nombre", "una empresa") if empresa_data else "una empresa"
        st.success(f"Te invitaron a unirte a **{empresa_nombre}** como **{invitacion['rol']}**.")
        st.caption(f"Email asociado: {invitacion['email']}")
        st.divider()
        st.subheader("Crea tu contrasena")
        password = st.text_input("Contrasena nueva", type="password", key="invite_pwd1")
        password_confirm = st.text_input("Confirma la contrasena", type="password", key="invite_pwd2")
        if st.button("Crear cuenta y aceptar", type="primary", use_container_width=True):
            if not password or len(password) < 6:
                st.error("La contrasena tiene que tener al menos 6 caracteres.")
                return
            if password != password_confirm:
                st.error("Las contrasenas no coinciden.")
                return
            with st.spinner("Creando tu cuenta..."):
                resultado = aceptar_invitacion(token=token, password=password)
            if resultado["exito"]:
                st.success("Listo! Tu cuenta esta creada.")
                st.balloons()
                if st.button("Ir al login", type="primary", use_container_width=True):
                    st.query_params.clear()
                    st.rerun()
            else:
                st.error(f"Error: {resultado['mensaje']}")


# ============ MAIN ============
def main():
    invite_token = st.query_params.get("invite")

    if invite_token and not usuario_logueado():
        pantalla_aceptar_invitacion(invite_token)
        return

    if not usuario_logueado():
        pantalla_login()
        return

    # ===== Usuario logueado: armar navegacion segun rol =====
    user = usuario_logueado()

    # Sidebar: info del usuario
    with st.sidebar:
        st.write(f"**{user['email']}**")
        roles = st.session_state.get("roles", [])
        for r in roles:
            empresa_data = r.get("empresa")
            if empresa_data and isinstance(empresa_data, dict):
                nombre_emp = empresa_data.get("nombre", "(sin nombre)")
            elif r.get("empresa_id") is None:
                nombre_emp = "(global)"
            else:
                nombre_emp = f"empresa #{r.get('empresa_id')}"
            st.caption(f"• {r['rol']} en {nombre_emp}")
        st.divider()
        if st.button("Cerrar sesion", use_container_width=True):
            logout()
            st.rerun()

    # Construir lista de paginas segun rol
    paginas = []

    # Paginas de COMERCIO (admin, operador, viewer)
    if tiene_rol("comercio_admin", "comercio_operador", "comercio_viewer", "super_admin"):
        paginas.append(st.Page("views/metricas.py", title="Dashboard", icon="📊", default=True))
        paginas.append(st.Page("views/derivaciones.py", title="Derivaciones", icon="🤝"))
        paginas.append(st.Page("views/clientes.py", title="Clientes", icon="👥"))
        paginas.append(st.Page("views/preguntas_sin_resolver.py", title="Sin resolver", icon="❓"))

    # Solo comercio_admin y super_admin: configuracion
    if tiene_rol("comercio_admin", "super_admin"):
        paginas.append(st.Page("views/configuracion.py", title="Configuracion", icon="⚙️"))

    # Solo super_admin: empresas + owner dashboard
    if es_super_admin():
        paginas.append(st.Page("views/empresas.py", title="Empresas", icon="🏢"))
        paginas.append(st.Page("views/owner_dashboard.py", title="Vista dueños", icon="👑"))

    if not paginas:
        st.error("Tu usuario no tiene paginas asignadas. Contacta al administrador.")
        return

    nav = st.navigation(paginas)
    nav.run()


main()