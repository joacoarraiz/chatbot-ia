"""
functions/db.py
Cliente Supabase compartido. Usar service_role_key porque las queries
las hace el backend en nombre del comercio.
"""
import os
from functools import lru_cache

from supabase import create_client, Client  # pip install supabase


@lru_cache(maxsize=1)
def get_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en el entorno"
        )
    return create_client(url, key)
