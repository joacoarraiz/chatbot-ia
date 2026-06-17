"""
dashboard/lib/auth.py
Logica de autenticacion contra Supabase Auth.
"""
from __future__ import annotations

import os
from typing import Optional

from supabase import create_client, Client
import streamlit as st


def get_supabase_anon() -> Client:
    """Cliente con la anon_key (respeta RLS)."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_ANON_KEY en el .env.")
    return create_client(url, key)


def login(email: str, password: str) -> dict:
    """
    Intenta loguear al usuario contra Supabase Auth.
    Devuelve: { "exito": bool, "user": dict|None, "error": str|None }
    """
    sb = get_supabase_anon()
    try:
        response = sb.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        if response.user:
            return {
                "exito": True,
                "user": {
                    "id": response.user.id,
                    "email": response.user.email,
                },
                "session": {
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                },
                "error": None,
            }
        return {"exito": False, "user": None, "error": "Sin respuesta del servidor"}
    except Exception as e:
        return {"exito": False, "user": None, "error": str(e)}


def logout():
    """Cierra la sesion del usuario actual."""
    if "user" in st.session_state:
        del st.session_state["user"]
    if "session" in st.session_state:
        del st.session_state["session"]
    if "roles" in st.session_state:
        del st.session_state["roles"]


def get_roles_del_usuario(user_id: str, access_token: str) -> list[dict]:
    """
    Trae los roles del usuario logueado + el nombre de la empresa.
    Usa el access_token del usuario para respetar RLS.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    sb = create_client(url, key)

    # Setear la sesion del usuario
    sb.auth.set_session(access_token, "")

    # 1. Traer los roles
    response = sb.table("empresa_usuario").select(
        "id, empresa_id, rol, estado"
    ).eq("user_id", user_id).execute()

    roles = response.data or []

    # 2. Para cada rol con empresa_id, traer el nombre
    # Usamos un cliente con service_role para esto, porque la tabla empresa
    # puede tener RLS estricto que el usuario authenticated no puede pasar.
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if service_key:
        sb_admin = create_client(url, service_key)
        empresa_ids = list({r["empresa_id"] for r in roles if r.get("empresa_id")})
        if empresa_ids:
            empresas_resp = (
                sb_admin.table("empresa")
                .select("id, nombre")
                .in_("id", empresa_ids)
                .execute()
            )
            empresas_map = {e["id"]: e["nombre"] for e in (empresas_resp.data or [])}
            # Inyectar el nombre en cada rol
            for r in roles:
                eid = r.get("empresa_id")
                if eid and eid in empresas_map:
                    r["empresa"] = {"id": eid, "nombre": empresas_map[eid]}

    return roles


def usuario_logueado() -> Optional[dict]:
    """Devuelve el usuario actual de st.session_state, o None."""
    return st.session_state.get("user")


def es_super_admin() -> bool:
    """Devuelve True si el usuario logueado tiene rol super_admin."""
    roles = st.session_state.get("roles", [])
    return any(r["rol"] == "super_admin" for r in roles)