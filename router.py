"""
agents/router/router.py
Implementación del Router. Clasifica el mensaje del cliente y devuelve un
RouterOutput validado. NO responde al cliente.

Uso:
    from agents.router.router import clasificar
    out = clasificar(mensaje, historial, cliente, config_empresa)
    if out.confianza < 0.6:
        # pedir desambiguación
    if out.cuenta_como_consulta:
        # abrir/cerrar/continuar consulta según intencion
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import anthropic  # pip install anthropic
from jsonschema import validate, ValidationError  # pip install jsonschema


# ---------- Configuración ----------

MODELO = os.getenv("LLM_MODEL_ROUTER", "claude-haiku-4-5")
MAX_TOKENS = 400  # JSON corto, no hace falta más
TEMPERATURA = 0.0  # clasificación: determinístico

BASE_DIR = Path(__file__).parent
PROMPT_PATH = BASE_DIR / "prompt.md"
SCHEMA_PATH = BASE_DIR / "schema.json"

SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------- Tipos ----------

@dataclass
class DatosExtraidos:
    marca_auto: str | None = None
    modelo: str | None = None
    anio: int | None = None
    motor: str | None = None
    pieza: str | None = None
    posicion: str | None = None
    codigo: str | None = None
    cantidad: int | None = None


@dataclass
class RouterOutput:
    intencion: str
    especialista: str
    confianza: float
    datos_extraidos: DatosExtraidos
    cuenta_como_consulta: bool
    razon: str

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------- Función pública ----------

def clasificar(
    mensaje: str,
    historial: list[dict] | None = None,
    cliente: dict | None = None,
    consulta_abierta: dict | None = None,
) -> RouterOutput:
    """
    Clasifica un mensaje del cliente.

    Args:
        mensaje: el texto del cliente (post-STT si era audio).
        historial: lista de últimos N mensajes (cada uno {emisor, contenido}).
        cliente: info del cliente {nombre, vehiculo_default, etiquetas}.
        consulta_abierta: si hay una consulta abierta, info de ella
                          {intencion, datos_acumulados, ultimo_turno_bot}.

    Returns:
        RouterOutput validado.

    Raises:
        ValidationError: si el LLM devuelve algo que no cumple el schema.
                         (lo manejamos con un fallback abajo)
    """
    contexto = _armar_contexto(mensaje, historial, cliente, consulta_abierta)

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURA,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": contexto}],
    )

    raw = response.content[0].text.strip()
    data = _parse_json_robusto(raw)

    try:
        validate(instance=data, schema=SCHEMA)
    except ValidationError as e:
        # Fallback seguro: marcar como ambiguo y dejar que el orquestador
        # pida aclaración. Nunca tirar excepción al cliente.
        return _fallback_ambiguo(
            f"router devolvió JSON inválido: {e.message[:100]}"
        )

    return RouterOutput(
        intencion=data["intencion"],
        especialista=data["especialista"],
        confianza=data["confianza"],
        datos_extraidos=DatosExtraidos(**data["datos_extraidos"]),
        cuenta_como_consulta=data["cuenta_como_consulta"],
        razon=data["razon"],
    )


# ---------- Helpers privados ----------

def _armar_contexto(
    mensaje: str,
    historial: list[dict] | None,
    cliente: dict | None,
    consulta_abierta: dict | None,
) -> str:
    partes: list[str] = []

    if cliente:
        partes.append("## Cliente")
        partes.append(json.dumps(cliente, ensure_ascii=False, indent=2))

    if consulta_abierta:
        partes.append("\n## Consulta abierta actualmente")
        partes.append(json.dumps(consulta_abierta, ensure_ascii=False, indent=2))

    if historial:
        partes.append("\n## Últimos mensajes")
        for m in historial[-6:]:
            quien = m.get("emisor", "?")
            texto = m.get("contenido", "")
            partes.append(f"- [{quien}]: {texto}")

    partes.append("\n## Mensaje actual a clasificar")
    partes.append(mensaje)
    partes.append("\nDevolvé SOLO el JSON, sin markdown ni explicación.")

    return "\n".join(partes)


def _parse_json_robusto(raw: str) -> dict:
    """
    El modelo a veces envuelve la respuesta en ```json ... ``` aunque le pidamos
    que no lo haga. Limpiamos antes de parsear.
    """
    # Sacar bloques de código markdown si vinieron
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    # Sacar texto antes/después del JSON
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start : end + 1]
    return json.loads(raw)


def _fallback_ambiguo(razon: str) -> RouterOutput:
    return RouterOutput(
        intencion="ambiguo",
        especialista="ninguno",
        confianza=0.0,
        datos_extraidos=DatosExtraidos(),
        cuenta_como_consulta=False,
        razon=razon,
    )


# ---------- Test manual rápido ----------

if __name__ == "__main__":
    # Probá con:  python -m agents.router.router
    casos = [
        "hola",
        "necesito pastillas delanteras para un Gol 1.6 2010",
        "tenés el BP1234567?",
        "gracias!",
        "che, quiero hablar con alguien",
        "delanteras",  # respuesta a desambiguación
    ]
    for m in casos:
        try:
            out = clasificar(m)
            print(f"\n📨 {m!r}")
            print(json.dumps(out.to_dict(), indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"❌ Error con {m!r}: {e}")
