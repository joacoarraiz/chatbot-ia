"""
scripts/compute_scores.py
Job que evalúa conversaciones cerradas y les asigna un score 0-100.
4 componentes determinísticos + 1 que usa el LLM auditor.

Se corre como cron job una vez por noche.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Permitir imports desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from functions.db import get_client


def main():
    sb = get_client()

    # Conversaciones cerradas en las últimas 24 horas, sin score aún
    ayer = (datetime.utcnow() - timedelta(days=1)).isoformat()

    consultas = (
        sb.table("consulta")
          .select("*, conversacion(*)")
          .eq("estado", "cerrada")
          .gte("cerrada_at", ayer)
          .execute()
    )

    print(f"Encontradas {len(consultas.data or [])} consultas para scorear.")

    for c in consultas.data or []:
        # Acá iría la lógica completa de evaluación.
        # Por ahora dejamos el esqueleto.
        print(f"  Consulta {c['id']}: pendiente de implementación.")


if __name__ == "__main__":
    main()
