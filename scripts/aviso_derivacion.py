"""
scripts/aviso_derivacion.py
Avisa por WhatsApp (plantilla aprobada) cada vez que hay una derivacion nueva.

Reemplaza el workflow de N8N. Lee la vista v_derivaciones_pendientes
(que ya filtra avisado=false), manda la plantilla 'aviso_derivacion' al
operador, y marca cada derivacion como avisada=true para no repetir.

Se puede correr a mano para probar:
    python scripts/aviso_derivacion.py

En produccion lo dispara el scheduler interno (ver main.py), cada 2 minutos.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from functions.db import get_client
from functions.whatsapp import enviar_plantilla


# ============ CONFIG ============
# Numero del operador que recibe los avisos de derivacion.
# Lo tomamos del .env; si no esta, usamos el numero del piloto como fallback.
NUMERO_OPERADOR = os.environ.get("NUMERO_OPERADOR_DERIVACIONES", "542235984575")

# Nombre e idioma de la plantilla aprobada en Meta.
PLANTILLA_DERIVACION = "aviso_derivacion"
IDIOMA_PLANTILLA = "es_AR"


def avisar_derivaciones_pendientes(verbose: bool = True) -> int:
    """
    Busca derivaciones sin avisar y manda un aviso por cada una.
    Devuelve la cantidad de avisos enviados con exito.
    """
    sb = get_client()

    # 1. Leer derivaciones pendientes (la vista ya filtra avisado=false)
    pendientes = (
        sb.table("v_derivaciones_pendientes")
        .select("*")
        .execute()
        .data or []
    )

    if not pendientes:
        if verbose:
            print("  No hay derivaciones pendientes de avisar.")
        return 0

    if verbose:
        print(f"  Encontradas {len(pendientes)} derivacion(es) pendiente(s).")

    enviados = 0

    # 2. Por cada derivacion, mandar la plantilla y marcar avisado=true
    for d in pendientes:
        derivacion_id = d.get("id")
        cliente_nombre = d.get("cliente_nombre") or "Cliente"
        motivo = d.get("motivo") or "Sin motivo"
        resumen = d.get("resumen") or "Sin resumen"

        try:
            envio = enviar_plantilla(
                numero_destino=NUMERO_OPERADOR,
                nombre_plantilla=PLANTILLA_DERIVACION,
                variables=[cliente_nombre, motivo, resumen],
                idioma=IDIOMA_PLANTILLA,
            )

            if envio.get("exito"):
                # 3. Marcar como avisada SOLO si el envio salio bien
                sb.table("derivacion").update({"avisado": True}).eq("id", derivacion_id).execute()
                enviados += 1
                if verbose:
                    print(f"  [OK] Aviso enviado para derivacion #{derivacion_id} ({cliente_nombre}).")
            else:
                if verbose:
                    print(f"  [WARN] No se pudo enviar el aviso para derivacion #{derivacion_id}.")

        except Exception as e:
            # Si una falla, seguimos con las demas. No marcamos avisado
            # asi se reintenta en la proxima corrida.
            if verbose:
                print(f"  [ERROR] Derivacion #{derivacion_id}: {e}")

    return enviados


def main():
    print("=" * 60)
    print("  TONI - Aviso de derivaciones")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    enviados = avisar_derivaciones_pendientes(verbose=True)

    print("=" * 60)
    if enviados == 0:
        print("  OK - No se envio ningun aviso nuevo.")
    else:
        print(f"  OK - Se enviaron {enviados} aviso(s).")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())