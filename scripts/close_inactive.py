"""
scripts/close_inactive.py
Cierra consultas abiertas que no tuvieron actividad por mas de 30 minutos.
Se corre como cron job cada 5 minutos.

En desarrollo, lo corres a mano:
    python scripts/close_inactive.py

En produccion, Cloud Scheduler lo dispara automaticamente.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from functions.db import get_client


def main():
    print("=" * 60)
    print("  TONI - Cierre de consultas inactivas")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    sb = get_client()

    # Contar consultas abiertas ANTES
    abiertas_antes = (
        sb.table("consulta")
          .select("id", count="exact")
          .eq("estado", "abierta")
          .execute()
    )
    n_antes = abiertas_antes.count or 0
    print(f"  Consultas abiertas antes:   {n_antes}")

    # Llamar a la funcion SQL que hace el trabajo
    cerradas = 0
    try:
        response = sb.rpc("fn_cerrar_consultas_inactivas", {}).execute()
        cerradas = response.data if response.data is not None else 0
        print(f"  Consultas cerradas ahora:   {cerradas}")
    except Exception as e:
        print(f"  ERROR llamando a fn_cerrar_consultas_inactivas: {e}")
        return 1

    # Contar consultas abiertas DESPUES
    abiertas_despues = (
        sb.table("consulta")
          .select("id", count="exact")
          .eq("estado", "abierta")
          .execute()
    )
    n_despues = abiertas_despues.count or 0
    print(f"  Consultas abiertas despues: {n_despues}")

    print("=" * 60)
    if cerradas == 0:
        print("  OK - No habia consultas inactivas para cerrar.")
    else:
        print(f"  OK - Se cerraron {cerradas} consultas inactivas.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())