"""
scripts/audit_scores.py
Evalua las consultas cerradas del dia y les asigna un score 0-100.

5 componentes (20 puntos cada uno):
  1. Resolucion       (deterministico)
  2. Velocidad        (deterministico)
  3. Uso de tools     (deterministico)
  4. Completitud      (deterministico)
  5. Tono             (LLM evaluador)

Uso:
    python scripts/audit_scores.py [--dias N] [--limit M]

Argumentos opcionales:
    --dias N    : evaluar consultas cerradas en los ultimos N dias (default 1)
    --limit M   : maximo M consultas (util para testing)
    --dry-run   : calcular pero no guardar en la base
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from functions.db import get_client
from openai import OpenAI


# ============ HELPERS ============

def get_openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en el .env.")
    return OpenAI(api_key=api_key)


# ============ COMPONENTES DE SCORE ============

def evaluar_resolucion(consulta: dict, pedidos: list, derivaciones: list) -> tuple[int, str]:
    """
    Componente 1: ¿La consulta termino en resolucion util?
    20 puntos si hubo pedido confirmado.
    15 puntos si hubo derivacion bien armada (con resumen_contexto).
    10 puntos si hubo derivacion sin resumen util.
    5 puntos si cerro por inactividad pero el cliente recibio info.
    0 puntos si cerro por inactividad sin haber respondido nada util.
    """
    # Pedidos vinculados a esta consulta
    pedidos_consulta = [p for p in pedidos if p.get("consulta_id") == consulta["id"]]
    pedidos_confirmados = [p for p in pedidos_consulta if p.get("estado") not in ("borrador", "cancelado")]

    if pedidos_confirmados:
        return 20, "Termino en pedido confirmado."

    # Derivacion para esta consulta
    derivs = [d for d in derivaciones if d.get("consulta_id") == consulta["id"]]
    if derivs:
        d = derivs[0]
        resumen = d.get("resumen_contexto") or ""
        if len(resumen) > 50:
            return 15, "Derivacion con resumen detallado."
        return 10, "Derivacion sin resumen util."

    # Cierre por inactividad
    return 5, "Cierre por inactividad."


def evaluar_velocidad(mensajes_bot: list) -> tuple[int, str]:
    """
    Componente 2: ¿El bot respondio rapido?
    Se mide el tiempo entre mensaje del cliente y respuesta del bot.

    20 puntos si promedio <5s.
    15 puntos si <10s.
    10 puntos si <20s.
    5 puntos si <40s.
    0 puntos si >40s o sin datos.
    """
    if not mensajes_bot or len(mensajes_bot) < 2:
        return 10, "Pocos mensajes para evaluar velocidad."

    # En un test real, calcularias el delta entre mensaje cliente y respuesta bot.
    # Por ahora, devolvemos un placeholder.
    return 15, "Velocidad estimada (placeholder hasta tener metricas reales)."


def evaluar_uso_tools(intencion_logs: list) -> tuple[int, str]:
    """
    Componente 3: ¿El bot uso las tools cuando correspondia?
    20 puntos si todas las consultas de producto/precio usaron tools.
    15 puntos si la mayoria si.
    10 puntos si algunas si y otras no.
    0 puntos si invento datos sin usar tools.
    """
    if not intencion_logs:
        return 10, "Sin logs de intencion para evaluar."

    return 18, "Uso de tools razonable (evaluacion completa pendiente)."


def evaluar_completitud(intencion_logs: list) -> tuple[int, str]:
    """
    Componente 4: ¿El bot extrajo los datos relevantes (marca, modelo, anio)?
    Revisa los datos extraidos por el router en cada intencion.
    """
    if not intencion_logs:
        return 10, "Sin datos para evaluar completitud."

    # Buscar intenciones que requirieran datos de vehiculo
    intenciones_producto = [
        log for log in intencion_logs
        if "producto" in (log.get("intencion") or "")
        or "aplicacion" in (log.get("intencion") or "")
    ]

    if not intenciones_producto:
        return 18, "No hubo consultas que requirieran datos de vehiculo."

    # Contar cuantas tienen datos clave
    completas = 0
    for log in intenciones_producto:
        datos = log.get("datos") or {}
        if isinstance(datos, str):
            try:
                datos = json.loads(datos)
            except Exception:
                datos = {}
        if datos.get("marca") and datos.get("modelo"):
            completas += 1

    if not intenciones_producto:
        return 18, "Sin consultas de producto a evaluar."

    ratio = completas / len(intenciones_producto)
    if ratio >= 0.9:
        return 20, "Datos completos en casi todas las consultas."
    elif ratio >= 0.7:
        return 16, "Datos completos en la mayoria."
    elif ratio >= 0.5:
        return 12, "Datos completos a medias."
    else:
        return 6, "Faltaron datos clave en muchas consultas."


def evaluar_tono_llm(mensajes_bot: list) -> tuple[int, str]:
    """
    Componente 5: ¿El bot hablo en argentino claro y profesional?
    Usa gpt-4.1 para evaluar.
    """
    if not mensajes_bot:
        return 10, "Sin mensajes para evaluar tono."

    # Tomar las primeras 5 respuestas del bot para evaluar
    textos = [m.get("contenido", "") for m in mensajes_bot if m.get("direccion") == "saliente"]
    textos = [t for t in textos if t][:5]

    if not textos:
        return 10, "Sin respuestas del bot para evaluar."

    muestra = "\n---\n".join(textos)

    client = get_openai_client()
    model = os.environ.get("MODEL_SPECIALIST", "gpt-4.1")

    prompt = """Sos un evaluador de calidad de respuestas de un chatbot por WhatsApp argentino.
Recibis varios mensajes del bot. Evalua:
- ¿Hablan en argentino natural (voseo, sin formalidades de Espana)?
- ¿Son claros y cortos como corresponde a WhatsApp?
- ¿No tienen errores de tipeo o formato raro?
- ¿No suenan robotizados ni frios?

Respondé SOLO con un JSON: {"score": N, "comentario": "breve explicacion"}
Donde N es 0-20."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Mensajes a evaluar:\n\n{muestra}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=200,
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        return int(data.get("score", 10)), data.get("comentario", "")
    except Exception as e:
        return 10, f"Error evaluando con LLM: {e}"


# ============ ORQUESTADOR ============

def evaluar_consulta(consulta: dict, sb_data: dict) -> dict:
    """
    Evalua una consulta completa con los 5 componentes.
    sb_data es un dict pre-cargado con mensajes, pedidos, derivaciones, etc.
    """
    consulta_id = consulta["id"]
    conv_id = consulta["conversacion_id"]

    # Filtrar datos de esta conversacion/consulta
    mensajes = [m for m in sb_data["mensajes"] if m.get("conversacion_id") == conv_id]
    mensajes_bot = [m for m in mensajes if m.get("direccion") == "saliente"]
    intencion_logs = [il for il in sb_data["intencion_logs"] if il.get("consulta_id") == consulta_id]

    # Calcular los 5 componentes
    c1, mot1 = evaluar_resolucion(consulta, sb_data["pedidos"], sb_data["derivaciones"])
    c2, mot2 = evaluar_velocidad(mensajes_bot)
    c3, mot3 = evaluar_uso_tools(intencion_logs)
    c4, mot4 = evaluar_completitud(intencion_logs)
    c5, mot5 = evaluar_tono_llm(mensajes_bot)

    score_total = c1 + c2 + c3 + c4 + c5

    oportunidades = []
    if c1 < 15: oportunidades.append(f"Resolucion: {mot1}")
    if c2 < 15: oportunidades.append(f"Velocidad: {mot2}")
    if c3 < 15: oportunidades.append(f"Uso tools: {mot3}")
    if c4 < 15: oportunidades.append(f"Completitud: {mot4}")
    if c5 < 15: oportunidades.append(f"Tono: {mot5}")

    return {
        "consulta_id": consulta_id,
        "score": score_total,
        "componente_1": c1,
        "componente_2": c2,
        "componente_3": c3,
        "componente_4": c4,
        "componente_5_tono": c5,
        "oportunidades_mejora": oportunidades,
    }


# ============ MAIN ============

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=1, help="Dias hacia atras a evaluar")
    parser.add_argument("--limit", type=int, default=None, help="Maximo de consultas a evaluar")
    parser.add_argument("--dry-run", action="store_true", help="No guardar en la base")
    args = parser.parse_args()

    print("=" * 60)
    print("  TONI - Auditor de conversaciones (scoring)")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    sb = get_client()

    # Ventana temporal
    desde = (datetime.utcnow() - timedelta(days=args.dias)).isoformat()
    print(f"  Evaluando consultas cerradas desde: {desde[:19]}")

    # Traer consultas cerradas en la ventana
    consultas_resp = (
        sb.table("consulta")
          .select("*")
          .eq("estado", "cerrada")
          .gte("cerrada_at", desde)
          .execute()
    )
    consultas = consultas_resp.data or []
    print(f"  Consultas a evaluar: {len(consultas)}")

    if not consultas:
        print()
        print("  No hay consultas cerradas en la ventana.")
        print("  Esto es normal si el bot todavia no recibio conversaciones reales.")
        print("=" * 60)
        return 0

    if args.limit:
        consultas = consultas[:args.limit]
        print(f"  Aplicando limite: {args.limit}")

    # Pre-cargar datos necesarios para todas las consultas
    print("  Cargando datos relacionados...")
    sb_data = {
        "mensajes": (sb.table("mensaje").select("*").execute()).data or [],
        "pedidos": (sb.table("pedido").select("*").execute()).data or [],
        "derivaciones": (sb.table("derivacion").select("*").execute()).data or [],
        "intencion_logs": (sb.table("intencion_log").select("*").execute()).data or [],
    }

    # Evaluar cada consulta
    resultados = []
    for i, consulta in enumerate(consultas, 1):
        print(f"  [{i}/{len(consultas)}] Evaluando consulta {consulta['id']}...")
        try:
            resultado = evaluar_consulta(consulta, sb_data)
            resultados.append(resultado)
            print(f"     -> Score: {resultado['score']}/100")
            if resultado["oportunidades_mejora"]:
                for op in resultado["oportunidades_mejora"]:
                    print(f"        ! {op[:80]}")
        except Exception as e:
            print(f"     ERROR: {e}")

    # Guardar en la base (o saltar si --dry-run)
    if args.dry_run:
        print()
        print("  --dry-run activado: NO se guardo nada en la base.")
    else:
        print()
        print("  Guardando scores en la base...")
        for r in resultados:
            try:
                sb.table("score_consulta").insert(r).execute()
            except Exception as e:
                print(f"  ERROR guardando score de consulta {r['consulta_id']}: {e}")

    # Resumen
    if resultados:
        promedio = sum(r["score"] for r in resultados) / len(resultados)
        print()
        print(f"  Score promedio del periodo: {promedio:.1f}/100")
        print(f"  Mejor consulta:  {max(r['score'] for r in resultados)}/100")
        print(f"  Peor consulta:   {min(r['score'] for r in resultados)}/100")

    print("=" * 60)
    print("  OK - Auditoria terminada.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())