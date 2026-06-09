# Toni — Diseño Técnico Etapa 1

Este documento es el resumen del diseño técnico aprobado en mayo 2026.
Para el detalle completo, ver el archivo original en el proyecto.

## Decisiones clave

- **Definición de consulta**: ventana de 30 minutos, agrupa mensajes de una misma intención.
- **Arquitectura**: Router + 6 agentes especialistas.
- **Base de datos**: 17 tablas en 4 bloques (catálogo, clientes, conversaciones, scoring).
- **Scoring**: 5 componentes (4 determinísticos + 1 LLM auditor).

## Tablas principales

Ver `db/` para los SQL completos.

| Bloque | Tablas |
|---|---|
| Catálogo | empresa, fuente_catalogo, producto_logico, oferta, aplicacion, equivalencia, regla_precio |
| Clientes | cliente, contact_channel, vehiculo_cliente |
| Conversaciones | conversacion, mensaje, consulta, intencion_log |
| Scoring | pedido, pedido_item, derivacion, score_consulta |
