"""
scripts/recompute_tags.py
Recalcula las etiquetas automaticas de todos los clientes.
Se corre como cron job 1 vez por dia.

Etiquetas:
  - recurrente:     compro 2+ veces
  - candidato_b2b:  compro >$500.000 en ultimos 90 dias
  - dormido:        ultimo contacto hace >90 dias
  - frio:           nunca compro nada

Uso:
    python scripts/recompute_tags.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from functions.db import get_client


# Umbrales (modificables)
MIN_COMPRAS_RECURRENTE = 2
UMBRAL_B2B_PESOS = 500_000.0
DIAS_DORMIDO = 90
DIAS_VENTANA_B2B = 90


def calcular_etiquetas_cliente(cliente: dict, pedidos_cliente: list) -> list[str]:
    """
    Recibe los datos de un cliente y sus pedidos, devuelve la lista
    de etiquetas que aplican.
    """
    etiquetas = []
    ahora = datetime.utcnow()
    hace_90_dias = ahora - timedelta(days=DIAS_DORMIDO)

    # Pedidos confirmados (no borradores)
    pedidos_confirmados = [
        p for p in pedidos_cliente
        if p.get("estado") not in ("borrador", "cancelado")
    ]

    cantidad_compras = len(pedidos_confirmados)

    # recurrente
    if cantidad_compras >= MIN_COMPRAS_RECURRENTE:
        etiquetas.append("recurrente")

    # candidato_b2b: total comprado en ventana B2B > umbral
    hace_b2b = ahora - timedelta(days=DIAS_VENTANA_B2B)
    total_b2b = sum(
        float(p.get("total") or 0)
        for p in pedidos_confirmados
        if p.get("creado_at") and datetime.fromisoformat(p["creado_at"].replace("Z", "+00:00")).replace(tzinfo=None) >= hace_b2b
    )
    if total_b2b > UMBRAL_B2B_PESOS:
        etiquetas.append("candidato_b2b")

    # dormido: ultimo contacto > DIAS_DORMIDO
    ultimo_contacto = cliente.get("ultimo_contacto_at")
    if ultimo_contacto:
        ultimo_dt = datetime.fromisoformat(ultimo_contacto.replace("Z", "+00:00")).replace(tzinfo=None)
        if ultimo_dt < hace_90_dias:
            etiquetas.append("dormido")

    # frio: nunca compro
    if cantidad_compras == 0:
        etiquetas.append("frio")

    return etiquetas


def main():
    print("=" * 60)
    print("  TONI - Recalculo de etiquetas de cliente")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    sb = get_client()

    # Traer todos los clientes (de todas las empresas, RLS bypassed con service_role)
    clientes_resp = sb.table("cliente").select("*").execute()
    clientes = clientes_resp.data or []
    print(f"  Clientes a procesar: {len(clientes)}")

    if not clientes:
        print("  No hay clientes en la base todavia.")
        print("  Esto es normal si el bot todavia no recibio conversaciones reales.")
        print("=" * 60)
        return 0

    # Traer todos los pedidos de una sola vez
    pedidos_resp = sb.table("pedido").select("*").execute()
    todos_pedidos = pedidos_resp.data or []

    # Indexar pedidos por cliente_id para acceso rapido
    pedidos_por_cliente = {}
    for p in todos_pedidos:
        cid = p["cliente_id"]
        pedidos_por_cliente.setdefault(cid, []).append(p)

    # Procesar cada cliente
    contador_etiquetas = {
        "recurrente": 0,
        "candidato_b2b": 0,
        "dormido": 0,
        "frio": 0,
    }
    actualizados = 0

    for cliente in clientes:
        cliente_id = cliente["id"]
        pedidos_cliente = pedidos_por_cliente.get(cliente_id, [])
        nuevas_etiquetas = calcular_etiquetas_cliente(cliente, pedidos_cliente)

        # Comparar con las etiquetas actuales
        etiquetas_actuales = cliente.get("etiquetas") or []
        if sorted(nuevas_etiquetas) != sorted(etiquetas_actuales):
            # Actualizar en la base
            sb.table("cliente").update({
                "etiquetas": nuevas_etiquetas
            }).eq("id", cliente_id).execute()
            actualizados += 1

        # Sumar al contador
        for etiq in nuevas_etiquetas:
            if etiq in contador_etiquetas:
                contador_etiquetas[etiq] += 1

    print(f"  Clientes actualizados (cambio de etiquetas): {actualizados}")
    print()
    print("  Etiquetas asignadas (total):")
    for etiq, count in contador_etiquetas.items():
        print(f"     {etiq:20s} {count}")
    print("=" * 60)
    print("  OK - Recalculo terminado.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())