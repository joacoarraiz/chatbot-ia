"""
functions/order_tools.py
Tools que tocan pedidos y derivaciones.
"""
from __future__ import annotations

from datetime import datetime, timezone

from functions.db import get_client
from functions.catalog_tools import consultar_precio


def armar_pedido(
    empresa_id: int,
    cliente_id: int,
    consulta_id: int | None,
    items: list[dict],
    metodo_pago: str | None = None,
    metodo_entrega: str | None = None,
    direccion: str | None = None,
) -> dict:
    """
    Crea un pedido en estado `borrador`.

    items = [{ "producto_id": int, "cantidad": int, "precio_unitario": Decimal }]
    """
    try:
        db = get_client()
        total = sum(it["cantidad"] * float(it["precio_unitario"]) for it in items)

        # 1) Insertar pedido
        pedido_resp = db.table("pedido").insert({
            "empresa_id": empresa_id,
            "cliente_id": cliente_id,
            "consulta_id": consulta_id,
            "estado": "borrador",
            "monto_total": total,
            "metodo_pago": metodo_pago,
            "metodo_entrega": metodo_entrega,
            "direccion_envio": direccion,
        }).execute()
        pedido_id = pedido_resp.data[0]["id"]

        # 2) Insertar items
        for it in items:
            db.table("pedido_item").insert({
                "pedido_id": pedido_id,
                "producto_id": it["producto_id"],
                "oferta_id": it.get("oferta_id"),
                "cantidad": it["cantidad"],
                "precio_unitario": it["precio_unitario"],
                "subtotal": it["cantidad"] * float(it["precio_unitario"]),
            }).execute()

        return {"pedido_id": pedido_id, "estado": "borrador", "total": total}
    except Exception as e:
        return {"error": f"armar_pedido falló: {str(e)[:200]}"}


def confirmar_pedido(pedido_id: int) -> dict:
    try:
        db = get_client()
        db.table("pedido").update({
            "estado": "confirmado",
            "confirmado_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", pedido_id).execute()
        # Generar número de pedido legible
        db.rpc("rpc_asignar_numero_pedido", {"p_pedido_id": pedido_id}).execute()
        result = db.table("pedido").select("numero, estado, monto_total")\
                                   .eq("id", pedido_id).execute()
        return result.data[0] if result.data else {"error": "no encontrado"}
    except Exception as e:
        return {"error": f"confirmar_pedido falló: {str(e)[:200]}"}


def consultar_pedido(cliente_id: int, numero_pedido: str | None = None) -> dict:
    try:
        db = get_client()
        q = db.table("pedido").select(
            "id, numero, estado, monto_total, metodo_entrega, "
            "creado_at, confirmado_at, entregado_at, "
            "pedido_item(producto_id, cantidad, precio_unitario, subtotal)"
        ).eq("cliente_id", cliente_id)

        if numero_pedido:
            q = q.eq("numero", numero_pedido)
        else:
            q = q.order("creado_at", desc=True).limit(5)

        result = q.execute()
        return {"pedidos": result.data or []}
    except Exception as e:
        return {"error": f"consultar_pedido falló: {str(e)[:200]}"}


def consultar_info_empresa(empresa_id: int) -> dict:
    try:
        db = get_client()
        result = db.table("empresa").select(
            "nombre, persona_config, horario_atencion, zona_horaria, plan"
        ).eq("id", empresa_id).execute()
        if not result.data:
            return {"error": "empresa no encontrada"}
        return result.data[0]
    except Exception as e:
        return {"error": f"consultar_info_empresa falló: {str(e)[:200]}"}


def derivar_humano(
    conversacion_id: int,
    consulta_id: int,
    motivo: str,
    resumen: str,
    prioridad: str = "normal",
) -> dict:
    try:
        db = get_client()
        # 1) crear derivacion
        deriv = db.table("derivacion").insert({
            "conversacion_id": conversacion_id,
            "consulta_id": consulta_id,
            "motivo": motivo,
            "resumen": resumen,
            "prioridad": prioridad,
        }).execute()

        # 2) marcar conversacion como derivada
        db.table("conversacion").update({"estado": "derivada"})\
            .eq("id", conversacion_id).execute()

        # 3) marcar consulta como derivada
        db.table("consulta").update({
            "estado": "derivada",
            "resultado": "derivacion",
            "cerrada_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", consulta_id).execute()

        return {
            "derivacion_id": deriv.data[0]["id"],
            "estado": "derivada",
            "prioridad": prioridad,
        }
    except Exception as e:
        return {"error": f"derivar_humano falló: {str(e)[:200]}"}


def generar_resumen_conversacion(consulta_id: int) -> dict:
    """
    Devuelve un dict estructurado con todo el contexto de la consulta.
    El agente Derivación lo usa de base para escribir el resumen final.
    """
    try:
        db = get_client()

        # Datos de la consulta
        consulta = db.table("consulta").select(
            "id, intencion, productos_consultados, monto_cotizado, "
            "vehiculo_id, conversacion_id, cliente_id, iniciada_at"
        ).eq("id", consulta_id).execute().data
        if not consulta:
            return {"error": "consulta no encontrada"}
        consulta = consulta[0]

        # Cliente
        cliente = db.table("cliente").select(
            "nombre, etiquetas, total_consultas, total_compras"
        ).eq("id", consulta["cliente_id"]).execute().data
        cliente = cliente[0] if cliente else {}

        # Vehículo
        vehiculo = None
        if consulta.get("vehiculo_id"):
            v = db.table("vehiculo_cliente").select(
                "marca, modelo, anio, motor"
            ).eq("id", consulta["vehiculo_id"]).execute().data
            vehiculo = v[0] if v else None

        # Productos consultados
        productos = []
        if consulta.get("productos_consultados"):
            p = db.table("producto_logico").select(
                "id, descripcion, marca_pieza"
            ).in_("id", consulta["productos_consultados"]).execute().data
            productos = p or []

        # Mensajes
        mensajes = db.table("mensaje").select(
            "emisor, contenido, creado_at"
        ).eq("consulta_id", consulta_id).order("creado_at").execute().data

        return {
            "consulta": consulta,
            "cliente": cliente,
            "vehiculo": vehiculo,
            "productos_consultados": productos,
            "mensajes": mensajes or [],
        }
    except Exception as e:
        return {"error": f"generar_resumen_conversacion falló: {str(e)[:200]}"}
