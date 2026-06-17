"""
dashboard/lib/invitaciones.py
Funciones para crear empresas, generar links de invitacion,
y aceptar invitaciones.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import create_client, Client


def get_supabase_admin() -> Client:
    """Cliente con service_role (bypassa RLS, para operaciones admin)."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan credenciales de Supabase.")
    return create_client(url, key)


def listar_empresas() -> list[dict]:
    """Devuelve todas las empresas. Solo accesible por super_admin."""
    sb = get_supabase_admin()
    response = sb.table("empresa").select("*").order("creado_at", desc=False).execute()
    return response.data or []


def crear_empresa(
    nombre: str,
    plan: str = "basico",
    consultas_limite: int = 1500,
) -> dict:
    """
    Crea una nueva empresa con configuracion minima.

    Args:
        nombre: nombre comercial (ej: "Repuestos Pepito").
        plan: plan inicial. Default: basico.
        consultas_limite: limite mensual de consultas.

    Returns:
        dict con el registro de la empresa creada (incluyendo el id).
    """
    sb = get_supabase_admin()

    persona_config_inicial = {
        "tono": "argentino_cercano",
        "permite_alternativas": True,
        "nombre_comercial": nombre,
    }

    response = sb.table("empresa").insert({
        "nombre": nombre,
        "plan": plan,
        "consultas_limite": consultas_limite,
        "persona_config": persona_config_inicial,
        "estado": "activa",
    }).execute()

    if not response.data:
        raise RuntimeError("No se pudo crear la empresa.")

    return response.data[0]


def generar_invitacion(
    empresa_id: int,
    email_invitado: str,
    rol: str,
    invitado_por_user_id: str,
    dias_validez: int = 7,
) -> dict:
    """
    Crea una invitacion en la base con un token unico.

    Args:
        empresa_id: empresa a la que se invita.
        email_invitado: email del que va a recibir la invitacion.
        rol: 'comercio_admin' | 'comercio_operador' | 'comercio_viewer'.
        invitado_por_user_id: UUID del super_admin/admin que la genera.
        dias_validez: cuantos dias dura el link (default 7).

    Returns:
        dict con: { id, token, url_completa, expira_at }.
    """
    if rol not in ("comercio_admin", "comercio_operador", "comercio_viewer"):
        raise ValueError(f"Rol invalido: {rol}")

    sb = get_supabase_admin()

    # Generar token unico
    token = str(uuid.uuid4())

    # Calcular fecha de expiracion
    expira_at = datetime.now(timezone.utc) + timedelta(days=dias_validez)

    # Insertar en la base
    response = sb.table("invitacion").insert({
        "empresa_id": empresa_id,
        "email": email_invitado.lower().strip(),
        "rol": rol,
        "token": token,
        "invitado_por": invitado_por_user_id,
        "expira_at": expira_at.isoformat(),
    }).execute()

    if not response.data:
        raise RuntimeError("No se pudo crear la invitacion.")

    invitacion = response.data[0]

    # Generar la URL completa
    base_url = os.environ.get("DASHBOARD_BASE_URL", "http://localhost:8501")
    url_completa = f"{base_url}/?invite={token}"

    return {
        "id": invitacion["id"],
        "token": token,
        "url_completa": url_completa,
        "expira_at": expira_at.isoformat(),
        "email_invitado": email_invitado,
        "empresa_id": empresa_id,
        "rol": rol,
    }


def listar_invitaciones_empresa(empresa_id: int) -> list[dict]:
    """Devuelve las invitaciones de una empresa, ordenadas por fecha."""
    sb = get_supabase_admin()
    response = (
        sb.table("invitacion")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("creado_at", desc=True)
        .execute()
    )
    return response.data or []


def validar_token_invitacion(token: str) -> Optional[dict]:
    """
    Valida si un token es valido (existe, no expiro, no fue usado).

    Returns:
        dict con datos de la invitacion si es valida, None si no.
    """
    sb = get_supabase_admin()

    response = (
        sb.table("invitacion")
        .select("*, empresa(nombre)")
        .eq("token", token)
        .is_("usada_at", "null")
        .execute()
    )

    if not response.data:
        return None

    invitacion = response.data[0]

    # Verificar expiracion
    expira_at = datetime.fromisoformat(invitacion["expira_at"].replace("Z", "+00:00"))
    if expira_at < datetime.now(timezone.utc):
        return None

    return invitacion


def aceptar_invitacion(
    token: str,
    password: str,
) -> dict:
    """
    Procesa la aceptacion de una invitacion:
      1. Valida el token.
      2. Crea el usuario en Supabase Auth.
      3. Le asigna el rol en empresa_usuario.
      4. Marca la invitacion como usada.

    Returns:
        dict con: { exito, user_id, mensaje }.
    """
    invitacion = validar_token_invitacion(token)
    if not invitacion:
        return {"exito": False, "mensaje": "Token invalido, expirado o ya usado."}

    sb = get_supabase_admin()

    # 1. Crear el usuario en Supabase Auth
    try:
        auth_response = sb.auth.admin.create_user({
            "email": invitacion["email"],
            "password": password,
            "email_confirm": True,
        })
        user_id = auth_response.user.id
    except Exception as e:
        # Si el usuario ya existe, ese caso lo manejamos despues
        return {"exito": False, "mensaje": f"Error creando usuario: {e}"}

    # 2. Asignar el rol en empresa_usuario
    try:
        sb.table("empresa_usuario").insert({
            "empresa_id": invitacion["empresa_id"],
            "user_id": user_id,
            "rol": invitacion["rol"],
            "invitado_por": invitacion.get("invitado_por"),
            "estado": "activo",
        }).execute()
    except Exception as e:
        # Si falla aca, deberiamos revertir la creacion del user, pero por ahora avisamos
        return {"exito": False, "mensaje": f"Usuario creado pero error asignando rol: {e}"}

    # 3. Marcar invitacion como usada
    sb.table("invitacion").update({
        "usada_at": datetime.now(timezone.utc).isoformat()
    }).eq("token", token).execute()

    return {
        "exito": True,
        "user_id": user_id,
        "mensaje": f"Cuenta creada para {invitacion['email']}.",
    }