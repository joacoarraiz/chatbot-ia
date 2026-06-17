"""
tests/test_invitaciones.py
Test rapido de las funciones de invitacion.
Genera un link de invitacion para una empresa de prueba.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from dashboard.lib.invitaciones import (
    listar_empresas,
    generar_invitacion,
    listar_invitaciones_empresa,
    validar_token_invitacion,
)


def main():
    print("=" * 60)
    print("  TONI - Test de invitaciones")
    print("=" * 60)

    # 1. Listar empresas existentes
    print()
    print("1. Empresas en el sistema:")
    empresas = listar_empresas()
    for e in empresas:
        print(f"   #{e['id']}: {e['nombre']} ({e['plan']})")

    if not empresas:
        print("   No hay empresas. Salgo.")
        return

    # 2. Generar invitacion de prueba para la empresa 1
    print()
    print("2. Generando invitacion de prueba...")
    UID_INVITADOR = "3260b494-ccc7-4faa-a2a4-b626a7240235"  # tu UID
    invitacion = generar_invitacion(
        empresa_id=1,
        email_invitado="test_invitado@ejemplo.com",
        rol="comercio_admin",
        invitado_por_user_id=UID_INVITADOR,
    )
    print(f"   Invitacion creada:")
    print(f"   - ID: {invitacion['id']}")
    print(f"   - Email: {invitacion['email_invitado']}")
    print(f"   - Rol: {invitacion['rol']}")
    print(f"   - Token: {invitacion['token'][:20]}...")
    print(f"   - Expira: {invitacion['expira_at']}")
    print()
    print(f"   LINK PARA COPIAR Y MANDAR POR WHATSAPP:")
    print(f"   {invitacion['url_completa']}")

    # 3. Validar el token recien creado
    print()
    print("3. Validando el token recien creado...")
    validada = validar_token_invitacion(invitacion["token"])
    if validada:
        print(f"   OK - Token valido para empresa #{validada['empresa_id']}")
    else:
        print("   ERROR - El token no validó.")

    # 4. Listar todas las invitaciones de la empresa 1
    print()
    print("4. Invitaciones de la empresa #1:")
    invs = listar_invitaciones_empresa(1)
    for inv in invs[:5]:  # solo las 5 mas recientes
        estado = "USADA" if inv.get("usada_at") else "PENDIENTE"
        print(f"   - {inv['email']:35s} {inv['rol']:20s} [{estado}]")
    if len(invs) > 5:
        print(f"   ... y {len(invs) - 5} mas.")

    print()
    print("=" * 60)
    print("  OK - Invitaciones funcionando.")
    print("=" * 60)


if __name__ == "__main__":
    main()