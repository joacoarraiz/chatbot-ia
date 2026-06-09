"""
functions/db.py
Cliente unificado de Supabase. Otros módulos del bot importan
desde acá para hablar con la base de datos.
"""
from __future__ import annotations

import os
from functools import lru_cache

from supabase import create_client, Client


@lru_cache(maxsize=1)
def get_client() -> Client:
    """
    Devuelve un cliente de Supabase usando la service_role key.
    El bot usa service_role porque necesita bypassear RLS para
    operar como sistema (no como un usuario humano).
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise RuntimeError(
            "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en el .env. "
            "Revisá que el archivo .env exista y tenga las dos variables."
        )

    return create_client(url, key)


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    """
    Cliente con la anon key (sin permisos especiales). Útil para
    operaciones del dashboard que respetan RLS.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_ANON_KEY en el .env.")
    return create_client(url, key)
