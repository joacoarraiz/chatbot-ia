"""
scripts/repregunta_inactivos.py
Reenganche: le recuerda al cliente una consulta que dejo sin responder.

Busca conversaciones "colgadas" (el ultimo mensaje fue de Toni y el cliente
no volvio) que ya superaron el tiempo configurado por el comercio, y les manda
la plantilla 'seguimiento_consulta'. Marca cada una para no repetir.

DOBLE CANDADO anti-molestia:
  1. Por conversacion (conversacion.repreguntada_at): no repite sobre la misma charla.
  2. Por cliente (cliente.ultima_repregunta_at): un cliente NO recibe mas de una
     repregunta cada 24 hs, aunque tenga varias conversaciones colgadas.

Cada comercio elige su tiempo en config_negocio.repregunta_horas
(NULL o 0 = desactivado).

OJO: esto le escribe al CLIENTE FINAL por iniciativa del bot. En sandbox solo
llega a numeros autorizados a mano. Para clientes reales hace falta salir del
sandbox (App Review). La plantilla 'seguimiento_consulta' ya esta aprobada.

Se puede correr a mano para probar:
    python scripts/repregunta_inactivos.py
En produccion lo dispara el scheduler interno (ver main.py).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from functions.db import get_client
from functions.whatsapp import enviar_plantilla


# ============ CONFIG ============
PLANTILLA_REPREGUNTA = "seguimiento_consulta"
IDIOMA_PLANTILLA = "es_AR"

# Texto generico para la variable {{2}} de la plantilla ("lo que consulto").
CONSULTA_GENERICA = "tu consulta"

# Ventana anti-molestia por cliente: no repreguntar mas de una vez cada X horas.
HORAS_MINIMAS_ENTRE_REPREGUNTAS = 24


def _numero_del_cliente(sb, cliente_id):
    """Numero de WhatsApp del cliente desde contact_channel. None si no hay."""
    try:
        r = (
            sb.table("contact_channel")
            .select("identificador")
            .eq("cliente_id", cliente_id)
            .eq("canal", "whatsapp")
            .limit(1)
            .execute()
        )
        if r.data:
            return r.data[0]["identificador"]
    except Exception as e:
        print(f"  [WARN] No pude obtener el numero del cliente {cliente_id}: {e}")
    return None


def _datos_cliente(sb, cliente_id):
    """Devuelve (nombre, ultima_repregunta_at) del cliente."""
    nombre = "Hola"
    ultima = None
    try:
        r = (
            sb.table("cliente")
            .select("nombre, ultima_repregunta_at")
            .eq("id", cliente_id)
            .limit(1)
            .execute()
        )
        if r.data:
            nombre = r.data[0].get("nombre") or "Hola"
            ultima = r.data[0].get("ultima_repregunta_at")
    except Exception:
        pass
    return nombre, ultima


def _phone_number_id_de_empresa(sb, empresa_id):
    """Numero propio por el que responde ese comercio (multi-comercio)."""
    try:
        r = (
            sb.table("numero_whatsapp")
            .select("phone_number_id")
            .eq("empresa_id", empresa_id)
            .eq("activo", True)
            .limit(1)
            .execute()
        )
        if r.data:
            return r.data[0]["phone_number_id"]
    except Exception:
        pass
    return None


def _repreguntado_hace_poco(ultima_repregunta_at, ahora):
    """True si al cliente ya se le repregunto dentro de la ventana anti-molestia."""
    if not ultima_repregunta_at:
        return False
    try:
        ultima = datetime.fromisoformat(ultima_repregunta_at.replace("Z", "+00:00"))
        return (ahora - ultima) < timedelta(hours=HORAS_MINIMAS_ENTRE_REPREGUNTAS)
    except Exception:
        return False


def repreguntar_inactivos(verbose: bool = True) -> int:
    """
    Busca conversaciones colgadas que superaron el tiempo configurado y
    manda la repregunta, respetando el doble candado. Devuelve cuantas se enviaron.
    """
    sb = get_client()
    ahora = datetime.now(timezone.utc)

    # 1. Config de repregunta por comercio (solo los que la tienen activa)
    configs = (
        sb.table("config_negocio")
        .select("empresa_id, repregunta_horas")
        .execute()
        .data or []
    )
    horas_por_empresa = {
        c["empresa_id"]: c["repregunta_horas"]
        for c in configs
        if c.get("repregunta_horas") and c["repregunta_horas"] > 0
    }

    if not horas_por_empresa:
        if verbose:
            print("  Ningun comercio tiene la repregunta activada.")
        return 0

    enviadas = 0
    # Clientes ya contactados EN ESTA corrida (evita doble envio si el cliente
    # tiene varias conversaciones colgadas en la misma pasada).
    clientes_ya_contactados = set()

    for empresa_id, horas in horas_por_empresa.items():
        limite_tiempo = (ahora - timedelta(hours=horas)).isoformat()

        convs = (
            sb.table("conversacion")
            .select("id, cliente_id, empresa_id")
            .eq("empresa_id", empresa_id)
            .eq("estado", "activa")
            .is_("repreguntada_at", "null")
            .lt("abierta_at", limite_tiempo)
            .execute()
            .data or []
        )

        if not convs:
            continue

        phone_number_id = _phone_number_id_de_empresa(sb, empresa_id)

        for conv in convs:
            conv_id = conv["id"]
            cliente_id = conv["cliente_id"]

            # CANDADO A: ya contactamos a este cliente en esta misma corrida
            if cliente_id in clientes_ya_contactados:
                continue

            # Ver el ULTIMO mensaje de la conversacion
            ult = (
                sb.table("mensaje")
                .select("emisor, creado_at")
                .eq("conversacion_id", conv_id)
                .order("creado_at", desc=True)
                .limit(1)
                .execute()
                .data or []
            )
            if not ult:
                continue
            ultimo = ult[0]

            # Solo si el ULTIMO fue del bot (el cliente no respondio)
            if ultimo["emisor"] != "bot":
                continue

            # Y si ese ultimo mensaje ya tiene mas horas que las configuradas
            creado = datetime.fromisoformat(ultimo["creado_at"].replace("Z", "+00:00"))
            if (ahora - creado) < timedelta(hours=horas):
                continue

            # Datos del cliente (nombre + ultima repregunta)
            nombre, ultima_repregunta = _datos_cliente(sb, cliente_id)

            # CANDADO B: al cliente ya se le repregunto hace menos de 24 hs
            if _repreguntado_hace_poco(ultima_repregunta, ahora):
                if verbose:
                    print(f"  [SKIP] Cliente {cliente_id}: ya repreguntado hace poco.")
                # Igual marcamos la conversacion para no re-evaluarla siempre
                sb.table("conversacion").update(
                    {"repreguntada_at": ahora.isoformat()}
                ).eq("id", conv_id).execute()
                continue

            numero = _numero_del_cliente(sb, cliente_id)
            if not numero:
                if verbose:
                    print(f"  [SKIP] Conversacion #{conv_id}: sin numero de cliente.")
                continue

            # Mandar la repregunta
            try:
                envio = enviar_plantilla(
                    numero_destino=numero,
                    nombre_plantilla=PLANTILLA_REPREGUNTA,
                    variables=[nombre, CONSULTA_GENERICA],
                    idioma=IDIOMA_PLANTILLA,
                    phone_number_id=phone_number_id,
                )
                if envio.get("exito"):
                    # Marcar LAS DOS cosas: la conversacion y el cliente
                    sb.table("conversacion").update(
                        {"repreguntada_at": ahora.isoformat()}
                    ).eq("id", conv_id).execute()
                    sb.table("cliente").update(
                        {"ultima_repregunta_at": ahora.isoformat()}
                    ).eq("id", cliente_id).execute()

                    clientes_ya_contactados.add(cliente_id)
                    enviadas += 1
                    if verbose:
                        print(f"  [OK] Repregunta enviada a {nombre} (conversacion #{conv_id}).")
            except Exception as e:
                # Si falla, NO marcamos: se reintenta en la proxima corrida.
                if verbose:
                    print(f"  [ERROR] Conversacion #{conv_id}: {e}")

    return enviadas


def main():
    print("=" * 60)
    print("  TONI - Repregunta a inactivos")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    enviadas = repreguntar_inactivos(verbose=True)

    print("=" * 60)
    if enviadas == 0:
        print("  OK - No habia conversaciones para repreguntar.")
    else:
        print(f"  OK - Se enviaron {enviadas} repregunta(s).")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())