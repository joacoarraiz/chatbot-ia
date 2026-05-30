# Agentes

Cada agente vive en su propia carpeta y respeta el mismo contrato:

```
agents/<nombre>/
├── prompt.md       ← system prompt en español neutro
├── schema.json     ← formato JSON que debe devolver (si aplica)
└── README.md       ← cuándo se llama, qué tools usa, ejemplos
```

## Los 7 agentes

| Agente | Modelo | Devuelve | Tools |
|---|---|---|---|
| **router** | Haiku 4.5 (barato) | JSON estructurado | ninguna |
| **producto** | Sonnet 4 | texto + tool calls | buscar_producto, buscar_por_aplicacion, buscar_equivalencia, consultar_stock, consultar_precio |
| **cotizacion** | Sonnet 4 | texto + tool calls | aplicar_regla_precio, armar_pedido, reservar_stock |
| **pedido** | Haiku 4.5 (consulta simple) | texto + tool calls | consultar_pedido, consultar_estado_envio |
| **faq** | Haiku 4.5 | texto + tool calls | consultar_info_empresa |
| **derivacion** | Sonnet 4 (resumen crítico) | texto + tool calls | derivar_humano, generar_resumen_conversacion |
| **auditor** | Sonnet 4 (asincrónico) | JSON estructurado | ninguna |

## Quién llama a quién

```
mensaje entra → router → decide → especialista → responde al cliente
                                       ↓
                              tools de la BD (functions/)
```

El router NUNCA habla directo al cliente. Su salida (JSON) la consume el orquestador, que arma el contexto y llama al especialista que corresponda. El especialista sí responde al cliente.

El auditor es distinto: no es parte del flujo de respuesta. Corre como job nocturno sobre conversaciones ya cerradas y llena `score_consulta`.
