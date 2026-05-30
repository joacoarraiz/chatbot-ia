"""
scripts/compute_scores.py
Job nocturno que puntúa todas las consultas cerradas que aún no tienen score.

Componentes determinísticos (los calcula Python sobre la BD):
  - score_resolucion (0-40)
  - score_datos     (0-20)
  - score_eficiencia(0-15)
  - score_conversion(0-10)

Componente subjetivo (lo calcula el agente Auditor con LLM):
  - score_tono     (0-15) + observaciones + oportunidades_mejora

Uso:
    python -m scripts.compute_scores
    python -m scripts.compute_scores --dias 7   # backfill 7 días
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic
from jsonschema import validate, ValidationError

from functions.db import get_client


# ---------- Config del auditor ----------

AGENTS_DIR = Path(__file__).parent.parent / "agents" / "auditor"
AUDITOR_PROMPT = (AGENTS_DIR / "prompt.md").read_text(encoding="utf-8")
AUDITOR_SCHEMA = json.loads((AGENTS_DIR / "schema.json").read_text(encoding="utf-8"))
AUDITOR_MODEL = os.getenv("LLM_MODEL_ESPECIALISTA", "claude-sonnet-4-5")


# ---------- Componentes determinísticos ----------

def score_resolucion(consulta: dict, derivacion: dict | None) -> int:
    """0-40 según el resultado de la consulta."""
    resultado = consulta.get("resultado")
    estado = consulta.get("estado")

    if resultado == "venta":
        return 40
    if resultado == "cotizacion":
        return 30
    if resultado == "derivacion":
        # Si derivó CON resumen completo, 20. Si pobre, 10.
        if derivacion and len((derivacion.get("resumen") or "").strip()) >= 80:
            return 20
        return 10
    if estado == "abandonada":
        return 0
    return 5  # caso raro / sin clasificar


def score_datos(mensajes: list[dict]) -> int:
    """
    0-20 según si las búsquedas devolvieron datos completos.
    Inspecciona el metadata de los mensajes del bot.
    """
    busquedas = [
        m for m in mensajes
        if m.get("emisor") == "bot" and (m.get("metadata") or {}).get("tool_calls")
    ]
    if not busquedas:
        # No hubo búsquedas: la consulta no era de catálogo. No penalizar.
        return 20

    completas = 0
    parciales = 0
    vacias = 0
    for m in busquedas:
        for tc in (m["metadata"].get("tool_calls") or []):
            result = tc.get("result") or {}
            if result.get("error") or not result.get("resultados"):
                vacias += 1
                continue
            # Chequear si la primera oferta tiene precio Y stock
            primera = (result.get("resultados") or [None])[0]
            if primera and primera.get("precio_min") and primera.get("stock_total"):
                completas += 1
            else:
                parciales += 1

    total = completas + parciales + vacias
    if total == 0:
        return 20
    if vacias > 0 and completas == 0:
        return 0
    if completas == total:
        return 20
    return 10  # mixto


def score_eficiencia(mensajes: list[dict]) -> int:
    """
    0-15. Cuenta cuántos turnos del bot fueron preguntas (desambiguación).
    Heurística simple: mensajes del bot que terminan en '?'.
    """
    preguntas_bot = sum(
        1 for m in mensajes
        if m.get("emisor") == "bot" and "?" in (m.get("contenido") or "")
    )
    if preguntas_bot <= 3:
        return 15
    if preguntas_bot <= 6:
        return 8
    return 0


def score_conversion(consulta: dict, pedido: dict | None) -> int:
    """0-10."""
    if pedido and pedido.get("estado") in ("confirmado", "pagado", "entregado"):
        return 10
    if consulta.get("resultado") == "cotizacion":
        return 5
    return 0


# ---------- Componente subjetivo (LLM) ----------

def score_tono_y_observaciones(
    consulta: dict, mensajes: list[dict]
) -> tuple[int, str, list[str]]:
    """Llama al auditor LLM y devuelve (tono, observaciones, oportunidades)."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    conversacion_texto = "\n".join(
        f"[{m['emisor']}]: {m.get('contenido','')}"
        for m in mensajes
    )

    user_content = (
        f"## Datos estructurados\n"
        f"intencion: {consulta.get('intencion')}\n"
        f"resultado: {consulta.get('resultado')}\n"
        f"estado: {consulta.get('estado')}\n"
        f"monto_cotizado: {consulta.get('monto_cotizado')}\n\n"
        f"## Conversación\n{conversacion_texto}\n\n"
        f"Devolvé SOLO el JSON con score_tono, observaciones y oportunidades_mejora."
    )

    response = client.messages.create(
        model=AUDITOR_MODEL,
        max_tokens=600,
        temperature=0.2,
        system=AUDITOR_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    data = _parse_json(raw)

    try:
        validate(instance=data, schema=AUDITOR_SCHEMA)
    except ValidationError:
        # Fallback conservador
        return 8, "Auditor devolvió JSON inválido; score neutral asignado.", []

    return data["score_tono"], data["observaciones"], data["oportunidades_mejora"]


def _parse_json(raw: str) -> dict:
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start : end + 1]
    return json.loads(raw)


# ---------- Pipeline ----------

def calcular_banda(total: int) -> str:
    if total <= 40:
        return "mala"
    if total <= 70:
        return "regular"
    return "buena"


def puntuar_consulta(consulta_id: int) -> dict:
    db = get_client()

    # Cargar consulta
    c = db.table("consulta").select("*").eq("id", consulta_id).execute().data
    if not c:
        return {"error": f"consulta {consulta_id} no existe"}
    consulta = c[0]

    # Cargar mensajes
    mensajes = db.table("mensaje").select("emisor, contenido, metadata, creado_at")\
                                  .eq("consulta_id", consulta_id)\
                                  .order("creado_at").execute().data or []

    # Cargar derivacion (si hay)
    deriv_data = db.table("derivacion").select("*")\
                                       .eq("consulta_id", consulta_id).execute().data
    derivacion = deriv_data[0] if deriv_data else None

    # Cargar pedido (si hay)
    pedido_data = db.table("pedido").select("*")\
                                    .eq("consulta_id", consulta_id).execute().data
    pedido = pedido_data[0] if pedido_data else None

    # Calcular cada componente
    s_res  = score_resolucion(consulta, derivacion)
    s_dat  = score_datos(mensajes)
    s_efi  = score_eficiencia(mensajes)
    s_conv = score_conversion(consulta, pedido)
    s_ton, obs, opps = score_tono_y_observaciones(consulta, mensajes)

    total = s_res + s_dat + s_efi + s_ton + s_conv
    banda = calcular_banda(total)

    # Upsert en score_consulta
    db.table("score_consulta").upsert({
        "consulta_id": consulta_id,
        "score_resolucion": s_res,
        "score_datos": s_dat,
        "score_eficiencia": s_efi,
        "score_tono": s_ton,
        "score_conversion": s_conv,
        "score_total": total,
        "banda": banda,
        "observaciones": obs,
        "oportunidades_mejora": opps,
        "evaluado_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="consulta_id").execute()

    return {
        "consulta_id": consulta_id,
        "total": total,
        "banda": banda,
        "componentes": {
            "resolucion": s_res, "datos": s_dat, "eficiencia": s_efi,
            "tono": s_ton, "conversion": s_conv,
        },
    }


def correr_batch(dias: int = 1) -> None:
    db = get_client()
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()

    # Consultas cerradas sin score aún
    consultas = db.table("consulta").select("id").in_(
        "estado", ["resuelta", "derivada", "abandonada"]
    ).gte("cerrada_at", desde).execute().data or []

    if not consultas:
        print("No hay consultas cerradas sin puntuar.")
        return

    ya_puntuadas = {
        s["consulta_id"]
        for s in (db.table("score_consulta").select("consulta_id")
                    .in_("consulta_id", [c["id"] for c in consultas])
                    .execute().data or [])
    }

    pendientes = [c["id"] for c in consultas if c["id"] not in ya_puntuadas]
    print(f"Puntuando {len(pendientes)} consultas...")

    for cid in pendientes:
        try:
            r = puntuar_consulta(cid)
            print(f"  ✓ consulta {cid}: {r['total']}/100 ({r['banda']})")
        except Exception as e:
            print(f"  ✗ consulta {cid}: {e}")


# ---------- CLI ----------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dias", type=int, default=1,
                        help="Cuántos días hacia atrás puntuar (default: 1)")
    parser.add_argument("--consulta", type=int, default=None,
                        help="Puntuar una consulta específica por id")
    args = parser.parse_args()

    if args.consulta:
        r = puntuar_consulta(args.consulta)
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        correr_batch(args.dias)
