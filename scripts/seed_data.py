"""
scripts/seed_data.py
Genera datos de prueba realistas para la empresa piloto (id=1),
para poder ver los dashboards con datos reales antes de conectar WhatsApp.

Es IDEMPOTENTE: borra los datos de prueba previos (marcados con notas
especiales o por rango de fechas) y vuelve a cargar. No toca el catalogo.

Uso:
    python scripts/seed_data.py
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import os
from supabase import create_client

EMPRESA_ID = int(os.environ.get("EMPRESA_ID_PILOTO", "1"))

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
sb = create_client(url, key)

# Marca para identificar datos de prueba (asi los podemos borrar despues)
SEED_TAG = "[SEED]"

random.seed(42)  # reproducible


# ============ DATOS BASE ============
NOMBRES = [
    "Carlos Gomez", "Maria Lopez", "Juan Perez", "Ana Martinez", "Luis Garcia",
    "Sofia Rodriguez", "Diego Fernandez", "Laura Sanchez", "Pablo Diaz", "Lucia Romero",
    "Taller El Rapido", "Repuestos San Jorge", "Mecanica Hnos Ruiz", "AutoFix SRL",
    "Gabriel Torres", "Valentina Cruz", "Martin Acosta", "Camila Benitez",
    "Federico Sosa", "Julieta Medina",
]

TELEFONOS_BASE = 5492230000000  # Mar del Plata-ish

ETIQUETAS_POSIBLES = ["recurrente", "candidato_b2b", "dormido", "frio", "nuevo"]
TIPOS = ["b2c", "b2c", "b2c", "b2b"]  # mas b2c que b2b

INTENCIONES = [
    "buscar_producto", "buscar_por_aplicacion", "consultar_precio",
    "consultar_stock", "cotizar", "faq", "pedido",
]

MOTIVOS_DERIVACION = [
    "Cliente pide algo que no esta en catalogo",
    "Consulta tecnica compleja sobre compatibilidad",
    "Cliente quiere negociar precio por cantidad",
    "Reclamo sobre un pedido anterior",
    "Cliente pide factura A y datos fiscales",
]

RESUMENES_DERIVACION = [
    "Busca paragolpe delantero para Amarok 2018, no tenemos en catalogo. Quiere saber si se consigue.",
    "Pregunta si las pastillas Gol sirven para Saveiro mismo motor. Necesita confirmacion tecnica.",
    "Quiere 10 juegos de pastillas, pide descuento por volumen. Cotizar B2B.",
    "Dice que el ultimo pedido vino incompleto, falta un disco. Revisar pedido #1234.",
    "Taller que quiere cuenta corriente y factura A. Derivar a admin.",
]


def ahora():
    return datetime.now(timezone.utc)


def hace_dias(d):
    return ahora() - timedelta(days=d)


# ============ LIMPIEZA DE SEED PREVIO ============
def limpiar_seed():
    print("Limpiando datos de prueba previos...")
    # Buscar clientes de prueba (los que tienen [SEED] en notas)
    clientes = sb.table("cliente").select("id").eq("empresa_id", EMPRESA_ID).ilike("notas", f"%{SEED_TAG}%").execute()
    cliente_ids = [c["id"] for c in (clientes.data or [])]

    if cliente_ids:
        # Buscar conversaciones de esos clientes
        convs = sb.table("conversacion").select("id").in_("cliente_id", cliente_ids).execute()
        conv_ids = [c["id"] for c in (convs.data or [])]

        consultas = sb.table("consulta").select("id").in_("cliente_id", cliente_ids).execute()
        consulta_ids = [c["id"] for c in (consultas.data or [])]

        pedidos = sb.table("pedido").select("id").in_("cliente_id", cliente_ids).execute()
        pedido_ids = [p["id"] for p in (pedidos.data or [])]

        # Borrar en orden (hijos primero)
        if conv_ids:
            mensajes = sb.table("mensaje").select("id").in_("conversacion_id", conv_ids).execute()
            mensaje_ids = [m["id"] for m in (mensajes.data or [])]
            if mensaje_ids:
                sb.table("intencion_log").delete().in_("mensaje_id", mensaje_ids).execute()
            sb.table("derivacion").delete().in_("conversacion_id", conv_ids).execute()
            sb.table("mensaje").delete().in_("conversacion_id", conv_ids).execute()
        if consulta_ids:
            sb.table("score_consulta").delete().in_("consulta_id", consulta_ids).execute()
        if pedido_ids:
            sb.table("pedido_item").delete().in_("pedido_id", pedido_ids).execute()
            sb.table("pedido").delete().in_("id", pedido_ids).execute()
        if consulta_ids:
            sb.table("consulta").delete().in_("id", consulta_ids).execute()
        if conv_ids:
            sb.table("conversacion").delete().in_("id", conv_ids).execute()

        sb.table("vehiculo_cliente").delete().in_("cliente_id", cliente_ids).execute()
        sb.table("contact_channel").delete().in_("cliente_id", cliente_ids).execute()
        sb.table("cliente").delete().in_("id", cliente_ids).execute()

    print(f"  Limpiados {len(cliente_ids)} clientes de prueba y sus datos.")


# ============ CARGA DE DATOS ============
def crear_clientes():
    print("Creando clientes...")
    clientes_creados = []
    for i, nombre in enumerate(NOMBRES):
        tipo = "b2b" if ("Taller" in nombre or "Repuestos" in nombre or "SRL" in nombre or "Hnos" in nombre or "Mecanica" in nombre) else random.choice(TIPOS)
        n_etiquetas = random.randint(1, 2)
        etiquetas = random.sample(ETIQUETAS_POSIBLES, n_etiquetas)
        total_consultas = random.randint(1, 25)
        total_compras = random.randint(0, min(total_consultas, 8))
        monto = round(total_compras * random.uniform(8000, 45000), 2)
        dias_primera = random.randint(30, 180)
        dias_ultima = random.randint(0, 29)

        cliente = sb.table("cliente").insert({
            "empresa_id": EMPRESA_ID,
            "nombre": nombre,
            "tipo": tipo,
            "notas": f"{SEED_TAG} Cliente de prueba generado automaticamente.",
            "total_consultas": total_consultas,
            "total_compras": total_compras,
            "monto_acumulado": monto,
            "primera_actividad_at": hace_dias(dias_primera).isoformat(),
            "ultima_actividad_at": hace_dias(dias_ultima).isoformat(),
            "etiquetas": etiquetas,
        }).execute().data[0]

        clientes_creados.append(cliente)

        # Canal de contacto (WhatsApp)
        sb.table("contact_channel").insert({
            "cliente_id": cliente["id"],
            "canal": "whatsapp",
            "identificador": str(TELEFONOS_BASE + i),
            "display_name": nombre,
            "verificado": True,
        }).execute()

        # Algunos clientes tienen vehiculo cargado
        if random.random() > 0.4:
            marcas = [("VW", "Gol", 2010), ("Ford", "Fiesta", 2015), ("Chevrolet", "Corsa", 2008),
                      ("Fiat", "Palio", 2012), ("Renault", "Clio", 2011), ("Peugeot", "208", 2018)]
            marca, modelo, anio = random.choice(marcas)
            # vehiculo_cliente: insertamos defensivamente
            try:
                sb.table("vehiculo_cliente").insert({
                    "cliente_id": cliente["id"],
                    "marca": marca,
                    "modelo": modelo,
                    "anio": anio,
                }).execute()
            except Exception as e:
                # Si la estructura es distinta, lo omitimos sin romper
                pass

    print(f"  Creados {len(clientes_creados)} clientes.")
    return clientes_creados


def crear_conversaciones_y_consultas(clientes):
    print("Creando conversaciones, consultas, mensajes...")
    total_conv = 0
    total_consultas = 0
    total_derivaciones = 0
    consultas_creadas = []

    for cliente in clientes:
        n_conv = random.randint(1, 4)
        for _ in range(n_conv):
            dias = random.randint(0, 40)
            abierta = hace_dias(dias)
            estado_conv = random.choice(["cerrada", "cerrada", "cerrada", "activa"])
            cerrada = (abierta + timedelta(minutes=random.randint(5, 50))) if estado_conv == "cerrada" else None

            conv = sb.table("conversacion").insert({
                "empresa_id": EMPRESA_ID,
                "cliente_id": cliente["id"],
                "canal": "whatsapp",
                "abierta_at": abierta.isoformat(),
                "cerrada_at": cerrada.isoformat() if cerrada else None,
                "cerrada_por": "sistema" if cerrada else None,
                "estado": estado_conv,
            }).execute().data[0]
            total_conv += 1

            intencion = random.choice(INTENCIONES)
            monto_cot = round(random.uniform(10000, 60000), 2) if intencion in ("cotizar", "pedido") else None
            tokens_in = random.randint(200, 1500)
            tokens_out = random.randint(100, 800)
            costo = round((tokens_in * 0.4 + tokens_out * 1.6) / 1_000_000, 5)

            consulta = sb.table("consulta").insert({
                "empresa_id": EMPRESA_ID,
                "conversacion_id": conv["id"],
                "cliente_id": cliente["id"],
                "intencion": intencion,
                "estado": "cerrada" if cerrada else "abierta",
                "resultado": random.choice(["resuelta", "resuelta", "derivada", "sin_resolver"]),
                "monto_cotizado": monto_cot,
                "iniciada_at": abierta.isoformat(),
                "cerrada_at": cerrada.isoformat() if cerrada else None,
                "tokens_input": tokens_in,
                "tokens_output": tokens_out,
                "costo_ia_usd": costo,
            }).execute().data[0]
            total_consultas += 1
            consultas_creadas.append(consulta)

            # Mensajes de la conversacion
            msg_cliente = sb.table("mensaje").insert({
                "conversacion_id": conv["id"],
                "consulta_id": consulta["id"],
                "emisor": "cliente",
                "contenido": random.choice([
                    "hola, tenes pastillas para gol 2010?",
                    "necesito un filtro de aceite",
                    "cuanto sale el kit de embrague?",
                    "tenes amortiguadores para corsa?",
                    "a que hora abren?",
                ]),
                "tipo_media": "texto",
                "creado_at": abierta.isoformat(),
            }).execute().data[0]

            sb.table("mensaje").insert({
                "conversacion_id": conv["id"],
                "consulta_id": consulta["id"],
                "emisor": "bot",
                "agente": "producto",
                "contenido": "Si, tengo varias opciones. Te paso precios y stock...",
                "tipo_media": "texto",
                "creado_at": (abierta + timedelta(seconds=30)).isoformat(),
            }).execute()

            # intencion_log para el mensaje del cliente
            sb.table("intencion_log").insert({
                "mensaje_id": msg_cliente["id"],
                "intencion_detectada": intencion,
                "confianza": round(random.uniform(0.7, 0.98), 2),
                "agente_asignado": "producto",
                "cuenta_como_consulta": True,
            }).execute()

            # Algunas consultas se derivan
            if consulta["resultado"] == "derivada":
                idx = random.randint(0, len(MOTIVOS_DERIVACION) - 1)
                prioridad = random.choice(["normal", "normal", "alta", "urgente"])
                resuelta = random.random() > 0.5
                sb.table("derivacion").insert({
                    "conversacion_id": conv["id"],
                    "consulta_id": consulta["id"],
                    "motivo": MOTIVOS_DERIVACION[idx],
                    "resumen": RESUMENES_DERIVACION[idx],
                    "prioridad": prioridad,
                    "creado_at": abierta.isoformat(),
                    "resuelta_at": (abierta + timedelta(hours=random.randint(1, 48))).isoformat() if resuelta else None,
                    "resolucion": "Atendido por vendedor, cliente conforme." if resuelta else None,
                }).execute()
                total_derivaciones += 1

    print(f"  Creadas {total_conv} conversaciones, {total_consultas} consultas, {total_derivaciones} derivaciones.")
    return consultas_creadas


def crear_scores(consultas):
    print("Creando scores de consultas...")
    n = 0
    oportunidades = [
        "El cliente pregunto por un producto que no esta en catalogo.",
        "Demoro en entender la consulta inicial.",
        "Buena resolucion, sin observaciones.",
        "Podria haber ofrecido productos complementarios.",
        "No detecto que el cliente buscaba por codigo OEM.",
    ]
    for consulta in consultas:
        # No todas las consultas tienen score
        if random.random() > 0.3:
            # 5 componentes determinísticos
            s_resolucion = random.randint(50, 100)
            s_datos = random.randint(60, 100)
            s_eficiencia = random.randint(40, 100)
            s_tono = random.randint(70, 100)
            s_conversion = random.randint(20, 100)
            score_total = round(
                s_resolucion * 0.30 + s_datos * 0.20 + s_eficiencia * 0.15
                + s_tono * 0.15 + s_conversion * 0.20
            )
            if score_total >= 80:
                banda = "verde"
            elif score_total >= 55:
                banda = "amarillo"
            else:
                banda = "rojo"

            try:
                sb.table("score_consulta").insert({
                    "consulta_id": consulta["id"],
                    "score_resolucion": s_resolucion,
                    "score_datos": s_datos,
                    "score_eficiencia": s_eficiencia,
                    "score_tono": s_tono,
                    "score_conversion": s_conversion,
                    "score_total": score_total,
                    "banda": banda,
                    "observaciones": "Score generado automaticamente (seed).",
                    "oportunidades_mejora": [random.choice(oportunidades)],
                }).execute()
                n += 1
            except Exception as e:
                print(f"    (omitido un score: {e})")
    print(f"  Creados {n} scores.")


def crear_pedidos(clientes, consultas):
    print("Creando pedidos...")
    n = 0
    # Algunos clientes con compras tienen pedidos
    consultas_con_monto = [c for c in consultas if c.get("monto_cotizado")]
    for consulta in consultas_con_monto:
        if random.random() > 0.5:
            estado = random.choice(["confirmado", "confirmado", "entregado", "borrador"])
            creado = hace_dias(random.randint(0, 30))
            try:
                sb.table("pedido").insert({
                    "empresa_id": EMPRESA_ID,
                    "cliente_id": consulta["cliente_id"],
                    "consulta_id": consulta["id"],
                    "numero": f"P-{random.randint(1000, 9999)}",
                    "estado": estado,
                    "monto_total": consulta["monto_cotizado"],
                    "metodo_pago": random.choice(["efectivo", "transferencia", "tarjeta"]),
                    "metodo_entrega": random.choice(["retiro_local", "envio"]),
                    "creado_at": creado.isoformat(),
                    "confirmado_at": creado.isoformat() if estado != "borrador" else None,
                    "entregado_at": (creado + timedelta(days=2)).isoformat() if estado == "entregado" else None,
                }).execute()
                n += 1
            except Exception as e:
                print(f"    (omitido un pedido: {e})")
    print(f"  Creados {n} pedidos.")


def main():
    print("=" * 60)
    print(f"  SEED de datos de prueba - empresa #{EMPRESA_ID}")
    print("=" * 60)
    print()

    limpiar_seed()
    print()
    clientes = crear_clientes()
    consultas = crear_conversaciones_y_consultas(clientes)
    crear_scores(consultas)
    crear_pedidos(clientes, consultas)

    print()
    print("=" * 60)
    print("  SEED COMPLETO")
    print("=" * 60)
    print(f"  Clientes:      {len(clientes)}")
    print(f"  Consultas:     {len(consultas)}")
    print("  Ahora los dashboards van a tener datos reales para mostrar.")
    print("=" * 60)


if __name__ == "__main__":
    main()