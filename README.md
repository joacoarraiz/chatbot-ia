# Toni — Chatbot de autopartes por WhatsApp

Bot multi-tenant para que comercios autopartistas atiendan a sus clientes finales por WhatsApp. Vive en Cloud Run (producción) y se desarrolla local con Python.

## Arquitectura rápida

- **Router** (GPT-4.1 Mini): clasifica la intención del mensaje y deriva al agente correcto.
- **6 agentes especialistas** (GPT-4.1): Producto, Cotización, Pedido, FAQ, Derivación, Auditor.
- **Base de datos**: Supabase (PostgreSQL en São Paulo).
- **STT**: GPT-4o Mini Transcribe para audios de WhatsApp.

## Setup local (primera vez)

```bash
# 1. Clonar el repo (ya hecho)
git clone https://github.com/joacoarraiz/chatbot-ia.git toni
cd toni

# 2. Crear entorno virtual aislado
python -m venv venv

# 3. Activarlo
# En Windows:
venv\Scripts\activate
# En Mac/Linux:
source venv/bin/activate

# 4. Instalar dependencias
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 5. Copiar plantilla de credenciales y completarla
copy .env.example .env
# (Windows; en Mac/Linux: cp .env.example .env)
# Después editar .env con las credenciales reales.

# 6. Verificar que todo está bien
python tests/test_connections.py
```

Si el último paso devuelve `✅ Todo OK`, el entorno está listo.

## Estructura

```
toni/
├── .env.example              ← plantilla de credenciales
├── .gitignore                ← protege el .env real y otros
├── requirements.txt          ← librerías de Python
├── README.md
├── main.py                   ← punto de entrada (servidor web)
│
├── db/                       ← SQL del esquema (ya corridos en Supabase)
│   ├── 01_catalog.sql
│   ├── 02_clients.sql
│   ├── 03_conversations.sql
│   ├── 04_orders_scoring.sql
│   └── 05_rls.sql
│
├── agents/                   ← prompts de los 7 agentes
│   ├── router/
│   │   ├── prompt.md         ← cómo clasifica intenciones
│   │   ├── schema.json       ← formato de output del router
│   │   └── router.py         ← código del router
│   ├── producto/prompt.md
│   ├── cotizacion/prompt.md
│   ├── pedido/prompt.md
│   ├── faq/prompt.md
│   ├── derivacion/prompt.md
│   └── auditor/prompt.md
│
├── functions/                ← código que conecta con Supabase
│   ├── db.py                 ← cliente Supabase
│   ├── catalog_tools.py      ← 5 tools de catálogo (buscar producto, stock, etc.)
│   ├── order_tools.py        ← tools de pedidos
│   └── _rpcs/
│       └── catalog_rpcs.sql  ← funciones RPC (ya cargadas en Supabase)
│
├── scripts/                  ← scripts auxiliares (cron jobs, scoring)
│   └── compute_scores.py     ← scoring nocturno de conversaciones
│
├── docs/                     ← documentación
│   ├── Diseno_Tecnico_Etapa1.md
│   ├── GUIA_GITHUB.md
│   └── GUIA_SUPABASE.md
│
└── tests/                    ← scripts para verificar que todo funciona
    └── test_connections.py   ← verifica Supabase + OpenAI
```

## Estado del proyecto

Ver `checklist_v2.html` en la raíz para el estado actualizado de los 12 frentes.

## Credenciales

Las credenciales reales viven en `.env` (que NUNCA se sube a GitHub — está en `.gitignore`).

Variables que necesita:
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`
- `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`
- `EMPRESA_ID_PILOTO` (= 1)
