# Toni — Bot de autopartes para WhatsApp

Asistente conversacional que entiende de autopartes, busca en el catálogo real del comercio y nunca inventa precios ni stock. Pensado multi-empresa (multi-tenant) desde el día uno.

## 🚀 Empezar

1. **Abrí `checklist.html` en Chrome.** Es tu mapa del proyecto: 9 secciones con todos los pasos, marcables, con notas. Se guarda solo en tu navegador.
2. **Leé `docs/Diseno_Tecnico_Etapa1.md`** antes de tocar código. Es la base — qué es una consulta, cómo identificamos clientes, arquitectura de agentes, scoring.
3. **Seguí las guías** en `docs/GUIA_GITHUB.md` y `docs/GUIA_SUPABASE.md` para setupear el ambiente.

## 📁 Estructura del repo

```
toni-bot/
├── checklist.html              ← ★ Abrí esto primero en Chrome
├── README.md
├── requirements.txt            ← Dependencias Python
├── .env.example                ← Plantilla de credenciales
├── .gitignore
│
├── docs/
│   ├── Diseno_Tecnico_Etapa1.md   ← El diseño completo
│   ├── GUIA_GITHUB.md             ← Cómo subir el repo
│   └── GUIA_SUPABASE.md           ← Cómo setupear la BD
│
├── db/                         ← Scripts SQL, correr en orden
│   ├── 01_catalog.sql             empresa + catálogo
│   ├── 02_clients.sql             clientes + identidades
│   ├── 03_conversations.sql       mensajes + consultas
│   ├── 04_orders_scoring.sql      pedidos + scoring
│   └── 05_rls.sql                 seguridad multi-tenant
│
├── agents/                     ← Los 7 agentes especializados
│   ├── README.md
│   ├── router/                    clasificador (Haiku)
│   │   ├── prompt.md
│   │   ├── schema.json
│   │   └── router.py              ★ implementación lista
│   ├── producto/                  buscar piezas (Sonnet)
│   ├── cotizacion/                cerrar venta (Sonnet)
│   ├── pedido/                    estado pedidos (Haiku)
│   ├── faq/                       info del comercio (Haiku)
│   ├── derivacion/                pasar a humano (Sonnet)
│   └── auditor/                   puntuar (Sonnet, async)
│
├── functions/                  ← Tools que usan los agentes
│   ├── README.md
│   ├── db.py                      cliente Supabase compartido
│   ├── catalog_tools.py           búsquedas en catálogo
│   ├── order_tools.py             pedidos + derivaciones
│   └── _rpcs/
│       └── catalog_rpcs.sql       funciones Postgres
│
└── scripts/
    └── compute_scores.py       ← Job nocturno de puntuación
```

## 🧠 Arquitectura en 30 segundos

```
WhatsApp → webhook → router (clasifica) → especialista (responde)
                                              ↓
                                       tools (consultan la BD)

Aparte (asincrónico):
  job nocturno → auditor → puntúa cada consulta cerrada
```

- **El router** es chico y barato. Clasifica intención y decide a quién derivar. No habla al cliente.
- **Los 6 especialistas** (producto, cotización, pedido, faq, derivación, auditor) tienen prompts enfocados y tools acotadas.
- **Las tools** son funciones Python que hablan con Postgres vía Supabase. Nunca inventan datos.

## 🔧 Stack

| Capa | Tecnología | Por qué |
|---|---|---|
| Base de datos | PostgreSQL en Supabase | Plan free generoso, multi-tenant con RLS, backups automáticos |
| Mensajería | WhatsApp Cloud API (Meta) | Único canal oficial de Meta para WA business |
| LLM razonamiento | Claude Sonnet 4 | Calidad alta de generación en español |
| LLM router | Claude Haiku 4.5 | Barato y rápido para clasificación |
| STT (audios) | Whisper (OpenAI) | Estándar de industria |
| Backend | Python + FastAPI | Familiar para el equipo |
| Hosting | A definir (Railway / Cloud Run / Render) | Lo más simple para empezar |

## 🎯 Estado del proyecto

Estamos en **Etapa 1**: bot funcional con catálogo, conversación, scoring y dashboard básico.

- [x] Diseño técnico
- [x] Esquema de base de datos
- [x] Prompts de los 7 agentes
- [x] Router implementado
- [x] Tools de catálogo (queries + RPCs)
- [x] Tools de pedidos y derivación
- [x] Job de scoring
- [ ] Webhook de WhatsApp
- [ ] Cargador de Excel del piloto
- [ ] Dashboard
- [ ] Deploy a producción

Tracking detallado en `checklist.html`.

## 📝 Convenciones

- **Idioma del código y commits**: inglés.
- **Idioma de docs, prompts y comentarios de negocio**: español.
- **Commits**: estilo conventional (`feat:`, `fix:`, `docs:`, `refactor:`).
- **Antes de mergear**: pull request con review de al menos 1 persona.

## 🆘 Algo no funciona

1. Si es de setup de Supabase → `docs/GUIA_SUPABASE.md`.
2. Si es de GitHub → `docs/GUIA_GITHUB.md`.
3. Si es de lógica del bot → `docs/Diseno_Tecnico_Etapa1.md`.
4. Si nada de eso ayuda → preguntarlo en el grupo del equipo.
