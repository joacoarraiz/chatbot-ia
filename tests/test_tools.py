"""
tests/test_tools.py
Prueba directa de las 5 tools del catálogo contra Supabase.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from functions.catalog_tools import (
    buscar_producto,
    buscar_por_aplicacion,
    buscar_equivalencia,
    consultar_precio,
    consultar_stock,
)


def section(num: int, total: int, title: str):
    print()
    print("=" * 60)
    print(f"  TEST {num}/{total}: {title}")
    print("=" * 60)


def show_results(results: list, max_items: int = 3):
    if not results:
        print("  ℹ️  La RPC respondió pero no devolvió resultados.")
        return
    print(f"  ✅ {len(results)} resultados:")
    for i, r in enumerate(results[:max_items], start=1):
        desc = r.get("descripcion", "")[:65]
        marca = r.get("marca_pieza", "—")
        stock = r.get("stock_total", 0)
        precio = r.get("precio_min")
        precio_txt = f"${precio:,.0f}" if precio else "sin precio"
        print(f"    {i}) {desc}...")
        print(f"       marca: {marca} | stock: {stock} | precio: {precio_txt}")
    if len(results) > max_items:
        print(f"    ... y {len(results) - max_items} más.")


def test_1_buscar_producto():
    section(1, 5, "buscar_producto: pastillas de freno")
    print("  → query='pastillas de freno', limit=5")
    results = buscar_producto(query="pastillas de freno", limit=5)
    show_results(results)


def test_2_buscar_por_aplicacion():
    section(2, 5, "buscar_por_aplicacion: VW Gol 2010")
    print("  → marca='VW', modelo='Gol', anio=2010")
    results = buscar_por_aplicacion(marca="VW", modelo="Gol", anio=2010, limit=5)
    show_results(results)


def test_3_buscar_otro_auto():
    section(3, 5, "buscar_por_aplicacion: Ford Fiesta 2015")
    print("  → marca='Ford', modelo='Fiesta', anio=2015")
    results = buscar_por_aplicacion(marca="Ford", modelo="Fiesta", anio=2015, limit=3)
    show_results(results)


def test_4_consultar_precio():
    section(4, 5, "consultar_precio: producto_id=1")
    print("  → producto_id=1")
    result = consultar_precio(producto_id=1)
    if result:
        print(f"  ✅ Precio devuelto:")
        print(f"     producto_id:   {result.get('producto_id')}")
        precio = result.get('precio_final')
        if precio:
            print(f"     precio_final:  ${precio:,.2f}")
        else:
            print(f"     precio_final:  (sin precio cargado)")
        print(f"     estrategia:    {result.get('estrategia', '—')}")
        print(f"     oferta_id:     {result.get('oferta_id', '—')}")
    else:
        print("  ℹ️  No se pudo calcular el precio (el producto no tiene oferta con stock).")
        print("      Es lo esperado para el catálogo del piloto: los precios aún no fueron cargados.")


def test_5_consultar_stock():
    section(5, 5, "consultar_stock: producto_id=1")
    print("  → producto_id=1")
    result = consultar_stock(producto_id=1)
    print(f"  ✅ Stock total: {result['stock_total']}")
    print(f"     Hay stock: {result['hay_stock']}")
    print(f"     Ofertas en el sistema: {len(result['ofertas'])}")
    for o in result['ofertas'][:3]:
        codigo = o.get('codigo_en_fuente', '—')
        stock = o.get('stock', 0)
        deposito = o.get('deposito', '—')
        print(f"       • código {codigo} | stock {stock} | depósito {deposito}")


def main():
    print()
    print("=" * 60)
    print("  🛠️  TONI — Test directo de las 5 tools del catálogo")
    print("  Conexión: Python → Supabase → catálogo del piloto")
    print("=" * 60)

    try:
        test_1_buscar_producto()
        test_2_buscar_por_aplicacion()
        test_3_buscar_otro_auto()
        test_4_consultar_precio()
        test_5_consultar_stock()

        print()
        print("=" * 60)
        print("  🎉 Las 5 tools funcionan. Listas para que el agente las use.")
        print("=" * 60)

    except Exception as e:
        print()
        print(f"  ❌ Error: {e}")
        print()
        raise


if __name__ == "__main__":
    main()