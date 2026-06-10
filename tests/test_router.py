"""
tests/test_router.py
Consola interactiva para probar el router en vivo.
Escribís un mensaje, el router te dice qué agente lo atendería.

Uso:
    python tests/test_router.py
    (Ctrl+C para salir)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Permitir imports desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents.router.router import clasificar


def main():
    print("=" * 60)
    print("  🤖 TONI — Modo prueba del Router")
    print("  Escribí un mensaje y veré cómo lo clasifica el bot.")
    print("  (Ctrl+C para salir)")
    print("=" * 60)
    print()

    # Sugerencias de mensajes de prueba para arrancar
    print("Ideas para probar:")
    print("  • 'necesito pastillas para mi gol 2010'")
    print("  • '¿a qué hora abren?'")
    print("  • 'cuanto sale el codigo AP9184?'")
    print("  • 'me llevo 2 amortiguadores'")
    print("  • 'hola'")
    print("  • 'quiero hablar con un vendedor'")
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
            resultado = clasificar(mensaje)
            print()
            print(f"  🎯 Agente elegido:   {resultado['agente']}")
            print(f"  🏷️  Intención:        {resultado['intencion']}")
            print(f"  📊 Confianza:        {resultado['confianza']:.0%}")
            print(f"  💭 Razonamiento:     {resultado['razonamiento']}")
            print(f"  📦 Datos extraídos:  {json.dumps(resultado['datos'], ensure_ascii=False)}")
            print(f"  💰 Cuenta consulta:  {resultado['cuenta_como_consulta']}")
            print()
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    main()
    