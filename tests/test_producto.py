"""
tests/test_producto.py
Consola interactiva para probar el agente Producto en vivo.
Vos escribís un mensaje, ves al agente razonar, usar tools, y responder.

Uso:
    python tests/test_producto.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents.producto.producto import responder


def main():
    print("=" * 60)
    print("  🤖 TONI — Agente Producto (modo prueba)")
    print("  Escribí una consulta y vé al agente trabajando.")
    print("  (Ctrl+C para salir)")
    print("=" * 60)
    print()
    print("Ideas para probar:")
    print("  • 'necesito pastillas para mi gol 2010'")
    print("  • 'que tenes para un ford fiesta 2015'")
    print("  • 'busco el codigo AP9184'")
    print("  • 'amortiguadores traseros para corsa 2005'")
    print("  • 'rodamientos para mi vw bora 1.8 2012'")
    print()

    while True:
        try:
            mensaje = input("📩 Vos: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Hasta luego!")
            break

        if not mensaje:
            continue

        if mensaje.lower() in ("salir", "exit", "quit"):
            print("\n👋 Hasta luego!")
            break

        try:
            print()
            print("  🤔 [Toni está pensando...]")
            resultado = responder(mensaje, verbose=True)

            print()
            print("─" * 60)
            print("  🤖 Toni:")
            print()
            for linea in resultado["respuesta_texto"].split("\n"):
                print(f"     {linea}")
            print()
            print("─" * 60)
            print(f"  📊 Tools usadas: {len(resultado['tools_usadas'])} | "
                  f"Iteraciones: {resultado['iteraciones']} | "
                  f"Tokens: {resultado['tokens_usados']}")
            print()
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()