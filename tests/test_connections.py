"""
tests/test_connections.py
Verifica que el entorno está bien configurado:
  1. Las variables del .env están cargadas.
  2. Se conecta a Supabase y puede leer la tabla empresa.
  3. Se conecta a OpenAI y obtiene respuesta del modelo router.
  4. Las RPC del catálogo están vivas (rpc_buscar_por_aplicacion).

Si todo pasa, queda confirmado que podemos arrancar a programar el bot.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Permitir imports desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


# ============ Helpers de output ============

def ok(msg: str): print(f"  ✅ {msg}")
def fail(msg: str): print(f"  ❌ {msg}")
def info(msg: str): print(f"  ℹ️  {msg}")
def step(n: int, total: int, title: str):
    print(f"\n[{n}/{total}] {title}")
    print("─" * 50)


# ============ TEST 1: variables del .env ============

def test_env_vars() -> bool:
    step(1, 4, "Verificando variables de entorno (.env)")

    requeridas = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "OPENAI_API_KEY",
        "EMPRESA_ID_PILOTO",
    ]
    opcionales = [
        "WHATSAPP_PHONE_NUMBER_ID",
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_APP_SECRET",
    ]

    todo_ok = True
    for var in requeridas:
        val = os.environ.get(var)
        if not val:
            fail(f"{var} FALTANTE (es obligatoria)")
            todo_ok = False
        elif val.startswith("TU_") or val == "sk-..." or val.startswith("eyJhbGc..."):
            fail(f"{var} tiene el valor de ejemplo, no la credencial real")
            todo_ok = False
        else:
            # Mostrar solo los primeros 10 chars de las keys para no leakear
            preview = val[:15] + "..." if len(val) > 20 else val
            ok(f"{var} = {preview}")

    for var in opcionales:
        val = os.environ.get(var)
        if val:
            preview = val[:15] + "..." if len(val) > 20 else val
            ok(f"{var} = {preview}  (opcional)")
        else:
            info(f"{var} vacía  (opcional, se completa cuando llegue de Meta)")

    return todo_ok


# ============ TEST 2: conexión a Supabase ============

def test_supabase() -> bool:
    step(2, 4, "Conectando a Supabase")

    try:
        from functions.db import get_client
        sb = get_client()

        # Leer la empresa piloto
        empresa_id = int(os.environ["EMPRESA_ID_PILOTO"])
        response = sb.table("empresa").select("*").eq("id", empresa_id).execute()

        if not response.data:
            fail(f"No encontré la empresa con id={empresa_id} en la tabla empresa.")
            return False

        empresa = response.data[0]
        ok(f"Empresa piloto encontrada: '{empresa['nombre']}' (id={empresa['id']}, plan={empresa['plan']})")

        # Contar productos
        prods = sb.table("producto_logico").select("id", count="exact").eq("empresa_id", empresa_id).execute()
        ok(f"Productos en catálogo: {prods.count or 0}")

        return True

    except Exception as e:
        fail(f"Error conectando a Supabase: {e}")
        return False


# ============ TEST 3: conexión a OpenAI ============

def test_openai() -> bool:
    step(3, 4, "Conectando a OpenAI")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        # Pedir una respuesta corta al modelo router
        model = os.environ.get("MODEL_ROUTER", "gpt-4.1-mini")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Decí solamente: hola toni"},
            ],
            max_tokens=20,
        )
        respuesta = response.choices[0].message.content.strip()
        ok(f"Modelo '{model}' respondió: '{respuesta}'")
        ok(f"Tokens usados: {response.usage.total_tokens}")
        return True

    except Exception as e:
        fail(f"Error conectando a OpenAI: {e}")
        info("Posibles causas:")
        info("  • API key inválida o expirada")
        info("  • Sin saldo cargado en la cuenta")
        info("  • Modelo no disponible para esta cuenta (probar con gpt-4o-mini)")
        return False


# ============ TEST 4: RPC del catálogo ============

def test_catalog_rpc() -> bool:
    step(4, 4, "Verificando RPC del catálogo")

    try:
        from functions.catalog_tools import buscar_por_aplicacion

        # Búsqueda de prueba: VW Gol 2010
        resultados = buscar_por_aplicacion(
            marca="VW",
            modelo="Gol",
            anio=2010,
            limit=3,
        )

        if not resultados:
            info("La RPC respondió pero no devolvió productos para VW Gol 2010.")
            info("Esto no es necesariamente un error: depende del catálogo.")
            return True

        ok(f"RPC funcionando, devolvió {len(resultados)} productos para VW Gol 2010:")
        for r in resultados[:3]:
            desc = r.get("descripcion", "")[:60]
            stock = r.get("stock_total", 0)
            ok(f"    • {desc}... (stock: {stock})")
        return True

    except Exception as e:
        fail(f"Error llamando a la RPC: {e}")
        return False


# ============ Main ============

def main():
    print("=" * 50)
    print("  TONI — Test de conexiones del entorno")
    print("=" * 50)

    resultados = {
        "env": test_env_vars(),
        "supabase": test_supabase(),
        "openai": test_openai(),
        "rpc": test_catalog_rpc(),
    }

    print()
    print("=" * 50)
    print("  RESUMEN")
    print("=" * 50)
    for nombre, ok_val in resultados.items():
        emoji = "✅" if ok_val else "❌"
        print(f"  {emoji} {nombre}")
    print()

    if all(resultados.values()):
        print("🎉 Todo OK. El entorno está listo para programar el bot.")
        sys.exit(0)
    else:
        print("⚠️  Hay algo que arreglar. Mirá los errores arriba.")
        sys.exit(1)


if __name__ == "__main__":
    main()
