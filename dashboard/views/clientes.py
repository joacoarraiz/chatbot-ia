"""
dashboard/views/clientes.py
CRM: lista de clientes con buscador + ficha detallada con historial.
"""
from __future__ import annotations

import streamlit as st
from dashboard.lib.db_dash import (
    get_clientes, get_cliente_detalle, get_mensajes_conversacion
)


def _empresa_id():
    roles = st.session_state.get("roles", [])
    for r in roles:
        if r.get("empresa_id"):
            return r["empresa_id"]
    import os
    return int(os.environ.get("EMPRESA_ID_PILOTO", "1"))


empresa_id = _empresa_id()

st.title("👥 Clientes")

# Si hay un cliente seleccionado, mostrar la ficha
cliente_sel = st.session_state.get("cliente_seleccionado")

if cliente_sel:
    # ===== FICHA DEL CLIENTE =====
    if st.button("← Volver a la lista"):
        st.session_state["cliente_seleccionado"] = None
        st.rerun()

    detalle = get_cliente_detalle(cliente_sel)
    cli = detalle["cliente"]

    st.header(cli.get("nombre", "Cliente"))
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tipo", cli.get("tipo", "-").upper())
    col2.metric("Consultas", cli.get("total_consultas", 0))
    col3.metric("Compras", cli.get("total_compras", 0))
    col4.metric("Monto acumulado", f"$ {float(cli.get('monto_acumulado') or 0):,.0f}")

    # Etiquetas
    etiquetas = cli.get("etiquetas") or []
    if etiquetas:
        st.write("**Etiquetas:** " + " ".join(f"`{e}`" for e in etiquetas))

    st.divider()

    # Tabs de detalle
    tab_veh, tab_conv, tab_ped = st.tabs(["🚗 Vehiculos", "💬 Conversaciones", "📦 Pedidos"])

    with tab_veh:
        vehiculos = detalle["vehiculos"]
        if vehiculos:
            for v in vehiculos:
                st.write(f"• **{v.get('marca')} {v.get('modelo')}** {v.get('anio') or ''} {v.get('motor') or ''}")
        else:
            st.info("Este cliente no tiene vehiculos cargados.")

    with tab_conv:
        convs = detalle["conversaciones"]
        if convs:
            for c in convs:
                fecha = c.get("abierta_at", "")[:16].replace("T", " ")
                estado = c.get("estado", "-")
                with st.expander(f"Conversacion del {fecha} · {estado}"):
                    mensajes = get_mensajes_conversacion(c["id"])
                    if mensajes:
                        for m in mensajes:
                            emisor = m.get("emisor", "?")
                            quien = "🤖 Toni" if emisor == "bot" else "👤 Cliente"
                            st.markdown(f"**{quien}:** {m.get('contenido', '')}")
                    else:
                        st.caption("Sin mensajes.")
        else:
            st.info("Sin conversaciones.")

    with tab_ped:
        pedidos = detalle["pedidos"]
        if pedidos:
            data = [{
                "Numero": p.get("numero", "-"),
                "Estado": p.get("estado", "-"),
                "Monto": f"$ {float(p.get('monto_total') or 0):,.0f}",
                "Pago": p.get("metodo_pago", "-"),
                "Fecha": p.get("creado_at", "")[:10],
            } for p in pedidos]
            st.dataframe(data, use_container_width=True, hide_index=True)
        else:
            st.info("Sin pedidos.")

else:
    # ===== LISTA DE CLIENTES =====
    st.caption("Lista de clientes de tu negocio.")

    clientes = get_clientes(empresa_id)
    if not clientes:
        st.info("Todavia no hay clientes.")
        st.stop()

    # Buscador
    busqueda = st.text_input("🔍 Buscar por nombre", placeholder="Escribi un nombre...")
    if busqueda:
        clientes = [c for c in clientes if busqueda.lower() in (c.get("nombre") or "").lower()]

    # Filtro por etiqueta
    todas_etiquetas = sorted({e for c in clientes for e in (c.get("etiquetas") or [])})
    if todas_etiquetas:
        filtro_etiqueta = st.multiselect("Filtrar por etiqueta", todas_etiquetas)
        if filtro_etiqueta:
            clientes = [c for c in clientes if any(e in (c.get("etiquetas") or []) for e in filtro_etiqueta)]

    st.caption(f"{len(clientes)} cliente(s)")
    st.divider()

    # Lista
    for c in clientes:
        with st.container(border=True):
            col_info, col_stats, col_accion = st.columns([3, 2, 1])
            with col_info:
                etiquetas = " ".join(f"`{e}`" for e in (c.get("etiquetas") or []))
                st.markdown(f"**{c.get('nombre', 'Sin nombre')}** · {c.get('tipo', '-').upper()}")
                if etiquetas:
                    st.caption(etiquetas)
            with col_stats:
                st.caption(f"Consultas: {c.get('total_consultas', 0)} · Compras: {c.get('total_compras', 0)}")
                st.caption(f"Monto: $ {float(c.get('monto_acumulado') or 0):,.0f}")
            with col_accion:
                if st.button("Ver ficha", key=f"ver_{c['id']}", use_container_width=True):
                    st.session_state["cliente_seleccionado"] = c["id"]
                    st.rerun()