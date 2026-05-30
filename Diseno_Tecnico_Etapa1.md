# Diseño técnico Etapa 1 — Toni
**Cinco decisiones que sostienen todo el motor**

Este documento cierra las definiciones que faltaban para arrancar a construir: qué cuenta como "consulta" (clave porque ahí se cobra), cómo reconocemos a un cliente recurrente, la base de datos completa, la arquitectura de agentes especializados y cómo puntuamos las conversaciones. Está pensado para que el equipo de ingeniería (Eze, Seba, Fran) lo lea, lo discuta y lo baje a tickets.

---

## 1. ¿Qué es una consulta?

Esta es la decisión más cargada del producto, porque de acá cuelgan los planes (100, 1.500, sin tope), el costo de IA por consulta del dashboard del dueño, y la sensación de "justicia" del cliente. Si la definimos mal, pasa una de dos cosas: o el cliente la "rompe" mandando todo separado y nos comemos costos, o lo penalizamos por charlar normal y el plan se siente mezquino.

### Definición

> **Una consulta es un intento de resolver una necesidad concreta del cliente final, agrupando todos los mensajes que pertenecen a esa misma intención dentro de una ventana de actividad continua.**

No es "un mensaje", no es "una conversación entera", no es "una llamada al LLM". Es una **unidad de negocio**: el cliente quiere algo, y todo el ida y vuelta hasta resolverlo (o frustrarse, o derivar) es **una sola** consulta.

### Reglas operativas

**Arranca una consulta cuando:**
- El cliente expresa una necesidad nueva que requiere trabajo del bot: buscar una pieza, cotizar, consultar estado de pedido, preguntar algo del comercio (horarios, ubicación, formas de pago), pedir hablar con humano.
- O cuando, dentro de una conversación abierta, el cliente claramente cambia de tema (de pastillas a baterías, de un auto a otro).

**Agrupa en la misma consulta:**
- Los mensajes de desambiguación ("¿1.4 o 1.6?", "¿delanteras o traseras?").
- Las re-formulaciones del cliente del mismo pedido.
- Las respuestas a opciones que el bot le mostró.
- Las correcciones ("ah no, era el del 2012").

**Cierra la consulta cuando** pasa primero alguno de estos:
- **30 minutos sin mensajes** del cliente (ventana de inactividad).
- **Se concreta una acción terminal**: reserva, pedido confirmado, derivación a humano, o el cliente dice explícitamente "gracias / nada más / listo".
- **Cambio claro de intención** detectado por el router (ver sección 5): pasa de "pastillas Gol" a "amortiguadores Fiesta" → cierra la primera, abre la segunda.

**NO cuentan como consulta** (no consumen del plan):
- Saludos puros: "hola", "buen día", "che".
- Cierres: "gracias", "ok", "perfecto", "👍".
- Confirmaciones cortas dentro de una consulta ya abierta.
- Mensajes donde el bot **se equivocó** y rehizo (no le cobramos al comercio nuestros errores).
- Mensajes fuera de horario que solo disparan auto-respuesta.

### Casos límite (cómo se resuelve cada uno)

| Situación | Cuántas consultas |
|---|---|
| Cliente pregunta por pastillas, las cotiza, las reserva | **1** |
| Cliente pregunta por pastillas y al rato por batería | **2** (cambio de intención) |
| Cliente saluda, espera, recién a la hora dice qué quiere | **1** (el saludo no contó; la consulta arranca cuando hay necesidad real) |
| Cliente abandona a la mitad sin responder | **1** (igual cuenta — el bot trabajó) |
| Cliente vuelve al día siguiente sobre el mismo tema | **2** (pasó la ventana de 30 min) |
| Cliente pide cosas raras 8 veces, el bot no resuelve nada | **1** (frustrada, pero 1) |
| Bot derivó mal y un humano tiene que rehacer todo | **1** (cuenta, pero el score va a ser bajo) |

### Transparencia hacia el comercio

- En el dashboard del comercio: contador en vivo "X / 1.500 consultas este mes" + alertas a 80% y 100%.
- Cada consulta tiene un `id` y se puede abrir y ver los mensajes que la componen — auditable.
- Si el cliente excede el plan, dos opciones a definir con ellos: bloquear hasta el próximo ciclo, o cobrar overage por consulta extra (recomiendo overage, no querés cortar el servicio).

### Por qué esta definición y no otra

Otras opciones que descartamos:
- **"1 mensaje = 1 consulta"**: gameable y castiga al cliente que chatea natural. El usuario que escribe en 3 burbujas paga 3, el que escribe en 1 paga 1. Injusto.
- **"1 conversación = 1 consulta"**: ¿cuándo termina una conversación? Es ambiguo y el cliente lo puede estirar para siempre.
- **"1 intent detectado = 1 consulta"**: técnicamente limpio pero opaco al cliente.

La nuestra ata el contador al **valor entregado**, que es lo que el comercio realmente compra.

---

## 2. Reconocer al cliente: misma persona, varias visitas

El cliente final no se loguea — entra por WhatsApp con su número y listo. La identidad la tenemos que armar nosotros. Y hay tres complicaciones que vale la pena tener desde el día uno:

1. **Multi-tenant.** El mismo número de teléfono puede ser cliente de varios comercios distintos. Su identidad es **por comercio**, no global.
2. **Multi-canal (a futuro).** El mismo cliente puede aparecer por WhatsApp, después por Mercado Libre, después por widget web. Tenemos que poder unirlos.
3. **B2B.** Un cliente empresa puede tener varios números (el dueño, el operativo). Mismo cliente, varios canales.

### El modelo de identidad

Tres tablas:

- **`cliente`** — una fila por (empresa, identidad). Acá viven las **estadísticas agregadas** que respondan "¿cuántas veces compró/consultó este?".
- **`contact_channel`** — los identificadores por canal (número de WA, user_id de ML, session_id web). Múltiples canales pueden apuntar al mismo cliente.
- **`vehiculo_cliente`** — los autos asociados (memoria del bot). Un cliente puede tener varios autos.

El primer mensaje desde un número desconocido **crea** el `cliente` y el `contact_channel`. A partir de ahí, cada nueva consulta/compra **actualiza** las stats agregadas.

### Reglas de detección

| Etiqueta | Criterio | Para qué sirve |
|---|---|---|
| **Recurrente** | ≥2 consultas en últimos 90 días | El bot lo saluda por su nombre y le pregunta "¿es para el Gol de siempre?" |
| **Comprador habitual** | ≥3 compras en últimos 12 meses | Trato preferencial, candidato a campaña de re-enganche |
| **Candidato B2B** | ≥5 compras en 6 meses Y patrón mayorista (compras de 5+ unidades, ítems repetidos) | Marcar en el CRM para que el comercio le ofrezca lista de taller / cuenta corriente |
| **Dormido** | Sin actividad >120 días, con ≥1 compra previa | Audiencia para campaña de plantilla de WhatsApp |
| **Frío** | 1 sola consulta, sin compra, >60 días | No invertir mensajes pagos acá |

Estas etiquetas se calculan con un job nocturno (no en cada mensaje) sobre los campos agregados — barato.

### Memoria conversacional (lo que el bot "se acuerda")

Por cada cliente guardamos:
- Vehículos conocidos (con el último usado marcado como "default").
- Nombre real si lo dio.
- Preferencias detectadas: "prefiere original", "prefiere retirar por el local", "siempre paga en efectivo".
- Notas del agente auditor: "candidato B2B", "se quejó de demora la última vez".

Esto es lo que aparece en la ficha del CRM y lo que el agente le pasa al bot en el `system prompt` de cada conversación: "este es Javier, tiene un Gol 1.6 2010, ya compró 3 veces, prefiere Bosch".

---

## 3. Base de datos completa (Postgres)

Acá está todo el esquema. Lo agrupé en cuatro bloques: catálogo (ya teníamos), clientes, conversaciones y métricas. Está pensado multi-tenant desde el principio (la mayoría de las tablas tienen `empresa_id`, indexado).

> **Recomendación de stack**: PostgreSQL (Supabase o RDS), con `pgvector` para búsqueda semántica de productos a futuro y Row Level Security activado por `empresa_id` desde el día uno.

### Bloque A — Catálogo (recap)

Estas ya las habíamos definido. Las incluyo completas para que el equipo tenga un solo archivo.

```sql
-- Cada empresa que contrata el bot (multi-tenant)
CREATE TABLE empresa (
  id BIGSERIAL PRIMARY KEY,
  nombre TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'prueba',     -- 'prueba'|'basico'|'pro'
  consultas_limite INT NOT NULL DEFAULT 100,
  persona_config JSONB,                    -- tono, jerga, branding, derivación
  whatsapp_phone_id TEXT,                  -- el ID de Meta de su WABA
  creado_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE fuente_catalogo (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  nombre TEXT,
  tipo TEXT,                               -- 'api'|'excel'|'csv'|'drive'|'scraping'
  mapeo JSONB,                             -- plantilla columna→campo
  sincronizado_at TIMESTAMPTZ
);

CREATE TABLE producto_logico (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  descripcion TEXT NOT NULL,
  marca_pieza TEXT,
  linea TEXT,                              -- frenos, motor, suspensión...
  atributos JSONB
);
CREATE INDEX idx_producto_empresa ON producto_logico(empresa_id);
CREATE INDEX idx_producto_descripcion ON producto_logico USING gin(to_tsvector('spanish', descripcion));

CREATE TABLE oferta (
  id BIGSERIAL PRIMARY KEY,
  producto_id BIGINT REFERENCES producto_logico ON DELETE CASCADE,
  fuente_id BIGINT REFERENCES fuente_catalogo,
  codigo_en_fuente TEXT,
  precio NUMERIC(12,2),
  costo NUMERIC(12,2),
  stock INT DEFAULT 0,
  deposito TEXT,
  actualizado_at TIMESTAMPTZ
);
CREATE INDEX idx_oferta_codigo ON oferta(codigo_en_fuente);

CREATE TABLE aplicacion (
  id BIGSERIAL PRIMARY KEY,
  producto_id BIGINT REFERENCES producto_logico ON DELETE CASCADE,
  auto_marca TEXT, modelo TEXT,
  anio_desde INT, anio_hasta INT,
  motor TEXT, posicion TEXT
);
CREATE INDEX idx_aplic_auto ON aplicacion(auto_marca, modelo, anio_desde, anio_hasta);

CREATE TABLE equivalencia (
  id BIGSERIAL PRIMARY KEY,
  producto_id BIGINT REFERENCES producto_logico ON DELETE CASCADE,
  tipo TEXT,                               -- 'oem'|'cruzada'
  codigo_externo TEXT,
  marca_externa TEXT,
  confianza NUMERIC(3,2)                   -- 0..1
);
CREATE INDEX idx_equiv_codigo ON equivalencia(codigo_externo);

CREATE TABLE regla_precio (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  ambito TEXT,                             -- 'producto'|'marca'|'linea'|'global'
  ambito_valor TEXT,
  estrategia TEXT,                         -- 'lista_fija'|'menor_precio'|'mayor_margen'|'fallback'
  fuente_preferida_id BIGINT,
  orden_fallback BIGINT[],
  requiere_stock BOOLEAN DEFAULT true,
  prioridad INT
);
```

### Bloque B — Clientes e identidad

```sql
-- El cliente final, con sus stats agregadas
CREATE TABLE cliente (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  nombre TEXT,                             -- si lo dio
  tipo TEXT DEFAULT 'b2c',                 -- 'b2c'|'b2b'
  notas TEXT,                              -- texto libre del CRM
  preferencias JSONB,                      -- 'prefiere original', etc.
  -- Agregados (recalculados por job nocturno)
  total_consultas INT DEFAULT 0,
  total_compras INT DEFAULT 0,
  monto_acumulado NUMERIC(14,2) DEFAULT 0,
  primera_actividad_at TIMESTAMPTZ,
  ultima_actividad_at TIMESTAMPTZ,
  etiquetas TEXT[],                        -- ['recurrente','candidato_b2b']
  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_cliente_empresa ON cliente(empresa_id);
CREATE INDEX idx_cliente_ultima ON cliente(empresa_id, ultima_actividad_at DESC);
CREATE INDEX idx_cliente_etiquetas ON cliente USING gin(etiquetas);

-- Identificadores del cliente en distintos canales
CREATE TABLE contact_channel (
  id BIGSERIAL PRIMARY KEY,
  cliente_id BIGINT REFERENCES cliente ON DELETE CASCADE,
  canal TEXT NOT NULL,                     -- 'whatsapp'|'ml'|'web'|'instagram'
  identificador TEXT NOT NULL,             -- E.164, user_id, session_id
  verificado BOOLEAN DEFAULT true,
  UNIQUE(canal, identificador)
);
CREATE INDEX idx_cc_cliente ON contact_channel(cliente_id);

-- Los autos del cliente (memoria)
CREATE TABLE vehiculo_cliente (
  id BIGSERIAL PRIMARY KEY,
  cliente_id BIGINT REFERENCES cliente ON DELETE CASCADE,
  marca TEXT, modelo TEXT,
  anio INT, motor TEXT, version TEXT,
  patente TEXT,
  es_default BOOLEAN DEFAULT false,
  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_veh_cliente ON vehiculo_cliente(cliente_id);
```

### Bloque C — Conversaciones, mensajes y consultas

```sql
-- Una "sesión" de chat abierta con un cliente
CREATE TABLE conversacion (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  cliente_id BIGINT REFERENCES cliente,
  canal TEXT NOT NULL,
  abierta_at TIMESTAMPTZ DEFAULT now(),
  cerrada_at TIMESTAMPTZ,
  cerrada_por TEXT,                        -- 'inactividad'|'cliente'|'derivacion'|'venta'
  estado TEXT DEFAULT 'activa'             -- 'activa'|'derivada'|'cerrada'
);
CREATE INDEX idx_conv_empresa_estado ON conversacion(empresa_id, estado);
CREATE INDEX idx_conv_cliente ON conversacion(cliente_id);

-- Cada mensaje individual (cliente o bot o humano)
CREATE TABLE mensaje (
  id BIGSERIAL PRIMARY KEY,
  conversacion_id BIGINT REFERENCES conversacion ON DELETE CASCADE,
  consulta_id BIGINT,                      -- nullable: saludos/gracias no atan a consulta
  emisor TEXT NOT NULL,                    -- 'cliente'|'bot'|'humano'
  agente TEXT,                             -- qué especialista lo produjo (ver §4)
  contenido TEXT,
  tipo_media TEXT,                         -- 'texto'|'audio'|'imagen'|'documento'
  media_url TEXT,
  metadata JSONB,                          -- tokens usados, latencia, etc.
  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_msg_conv ON mensaje(conversacion_id, creado_at);
CREATE INDEX idx_msg_consulta ON mensaje(consulta_id);

-- ★ La unidad de facturación
CREATE TABLE consulta (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  conversacion_id BIGINT REFERENCES conversacion,
  cliente_id BIGINT REFERENCES cliente,
  intencion TEXT NOT NULL,                 -- 'buscar_producto'|'estado_pedido'|'faq'|'humano'|'cotizacion'
  estado TEXT DEFAULT 'abierta',           -- 'abierta'|'resuelta'|'derivada'|'abandonada'
  resultado TEXT,                          -- 'venta'|'cotizacion'|'derivacion'|'sin_resultado'
  productos_consultados BIGINT[],
  monto_cotizado NUMERIC(12,2),
  iniciada_at TIMESTAMPTZ DEFAULT now(),
  cerrada_at TIMESTAMPTZ,
  -- Métrica de costo
  tokens_usados INT DEFAULT 0,
  costo_ia_usd NUMERIC(8,4) DEFAULT 0
);
CREATE INDEX idx_consulta_empresa_mes ON consulta(empresa_id, iniciada_at);
CREATE INDEX idx_consulta_cliente ON consulta(cliente_id);

-- Log del router: qué intent detectó, con qué confianza
CREATE TABLE intencion_log (
  id BIGSERIAL PRIMARY KEY,
  mensaje_id BIGINT REFERENCES mensaje,
  intencion_detectada TEXT,
  confianza NUMERIC(3,2),
  agente_asignado TEXT,
  datos_extraidos JSONB
);
```

### Bloque D — Pedidos, derivaciones y scoring

```sql
CREATE TABLE pedido (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  cliente_id BIGINT REFERENCES cliente,
  consulta_id BIGINT REFERENCES consulta,
  estado TEXT DEFAULT 'borrador',          -- 'borrador'|'confirmado'|'pagado'|'entregado'|'cancelado'
  monto_total NUMERIC(12,2),
  metodo_pago TEXT,
  metodo_entrega TEXT,                     -- 'retira'|'envio'
  notas TEXT,
  creado_at TIMESTAMPTZ DEFAULT now(),
  confirmado_at TIMESTAMPTZ
);

CREATE TABLE pedido_item (
  id BIGSERIAL PRIMARY KEY,
  pedido_id BIGINT REFERENCES pedido ON DELETE CASCADE,
  producto_id BIGINT REFERENCES producto_logico,
  oferta_id BIGINT REFERENCES oferta,
  cantidad INT NOT NULL,
  precio_unitario NUMERIC(12,2),
  subtotal NUMERIC(12,2)
);

CREATE TABLE derivacion (
  id BIGSERIAL PRIMARY KEY,
  conversacion_id BIGINT REFERENCES conversacion,
  consulta_id BIGINT REFERENCES consulta,
  motivo TEXT,                             -- 'cliente_pidio'|'baja_confianza'|'fuera_alcance'|'fuera_horario'
  resumen TEXT,                            -- el contexto armado por el agente derivador
  asignado_a BIGINT,                       -- user_id del vendedor
  creado_at TIMESTAMPTZ DEFAULT now(),
  resuelta_at TIMESTAMPTZ
);

-- ★ Puntuación de cada consulta cerrada
CREATE TABLE score_consulta (
  id BIGSERIAL PRIMARY KEY,
  consulta_id BIGINT REFERENCES consulta ON DELETE CASCADE UNIQUE,
  score_total INT,                         -- 0-100
  score_resolucion INT,                    -- 0-40
  score_datos INT,                         -- 0-20
  score_eficiencia INT,                    -- 0-15
  score_tono INT,                          -- 0-15
  score_conversion INT,                    -- 0-10
  banda TEXT,                              -- 'mala'|'regular'|'buena'
  observaciones TEXT,                      -- redactadas por el agente auditor
  oportunidades_mejora JSONB,              -- ['falta_catalogo:pastilla_kangoo_diesel', ...]
  evaluado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_score_banda ON score_consulta(banda);
```

### Activar Row Level Security desde el día uno

```sql
ALTER TABLE producto_logico ENABLE ROW LEVEL SECURITY;
ALTER TABLE cliente         ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversacion    ENABLE ROW LEVEL SECURITY;
ALTER TABLE consulta        ENABLE ROW LEVEL SECURITY;
-- ... y así con todas las que tengan empresa_id

-- Política tipo (se repite por tabla con empresa_id)
CREATE POLICY tenant_isolation ON producto_logico
  USING (empresa_id = current_setting('app.empresa_id')::bigint);
```

Esto evita el accidente clásico de multi-tenant: un bug en una query y un comercio termina viendo datos de otro. Con RLS, el accidente es imposible: la base lo bloquea.

---

## 4. Agentes especializados

La pregunta era "diferentes agentes para cada tipo de respuesta". Hay dos caminos posibles:

- **Un solo LLM con muchas tools** — más simple de construir, pero un solo prompt gigante que tiene que saber de todo. Se vuelve frágil y caro.
- **Router + especialistas** — un clasificador chico decide a qué especialista pasarle, y cada especialista tiene su prompt enfocado, sus tools acotadas, su contexto liviano.

**Recomendación: router + especialistas.** Es el patrón estándar de la industria para agentes en producción, escala mejor en costo (el router barato resuelve la mayoría), y aísla problemas (si el agente de pedidos se rompe, no se rompe el de búsqueda).

### Arquitectura

```
                  ┌──────────────────────┐
   WhatsApp ─────►│ Pre-procesamiento    │   audio → texto (STT)
                  │  (audio / imagen)    │   imagen → OCR (post-Etapa 1)
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │   ROUTER (clasifica) │   modelo chico/barato
                  │   → intent + score   │
                  └──────────┬───────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       ▼              ▼              ▼              ▼              ▼
  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
  │PRODUCTO │   │  COTIZA │   │ PEDIDO  │   │   FAQ   │   │ DERIVAR │
  │ buscar  │   │  armar  │   │ estado  │   │horarios │   │a humano │
  │ piezas  │   │ pedido  │   │compras  │   │ pagos   │   │+ resumen│
  └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘
       │              │              │              │              │
       └──────────────┴──────┬───────┴──────────────┴──────────────┘
                             ▼
                  ┌──────────────────────┐
                  │   Capa de funciones  │  buscar_producto, consultar_stock,
                  │   (tools)            │  consultar_precio, armar_pedido,
                  └──────────┬───────────┘  derivar_humano, etc.
                             ▼
                  ┌──────────────────────┐
                  │  Base de datos       │
                  └──────────────────────┘

                  Asincrónicos (corren aparte, no en respuesta):
                  ┌──────────────────────┐   ┌──────────────────────┐
                  │  AUDITOR (puntúa)    │   │  RE-ENGANCHE         │
                  │  job nocturno        │   │  detecta dormidos    │
                  └──────────────────────┘   └──────────────────────┘
```

### Los siete agentes

#### 4.1 Router (clasificador)

**Qué hace:** lee el último mensaje del cliente + un resumen corto del contexto, devuelve `{intencion, especialista, confianza, datos_extraidos}`. Si la confianza es <0.6, no decide solo: pide una pregunta de desambiguación.

**Modelo recomendado:** un LLM chico y barato (Haiku, Mini, etc.) — la mayoría de los mensajes son trivialmente clasificables.

**Tools:** ninguna. Solo clasifica.

**System prompt (resumido):**
```
Sos un clasificador de intención para un bot de autopartes en Argentina.
Tu única tarea es leer el mensaje del cliente y devolver JSON con esta forma:
{
  "intencion": "buscar_producto" | "cotizacion" | "estado_pedido" |
               "faq" | "humano" | "saludo" | "cierre" | "ambiguo",
  "especialista": "producto" | "cotizacion" | "pedido" | "faq" |
                  "derivacion" | "ninguno",
  "confianza": 0.0..1.0,
  "datos_extraidos": {
    "marca_auto": ..., "modelo": ..., "anio": ..., "pieza": ..., "codigo": ...
  },
  "cuenta_como_consulta": true | false
}

Reglas:
- "hola", "buen día" → intencion: "saludo", cuenta_como_consulta: false.
- "gracias", "ok", "listo" → "cierre", cuenta_como_consulta: false.
- Mensajes ambiguos ("no sé qué necesito") → "ambiguo" con confianza baja.
- NO inventes datos. Si el cliente no dijo el año, no lo pongas.
- Si el cliente repite/aclara una intención abierta, marca "continua_consulta".
```

#### 4.2 Agente Producto

**Qué hace:** la búsqueda de piezas — el corazón del bot. Recibe del router los datos extraídos (auto, pieza, etc.), pregunta solo lo que falta, llama a las funciones del catálogo, devuelve opciones reales.

**Tools:** `buscar_producto`, `buscar_por_aplicacion`, `buscar_equivalencia`, `consultar_stock`, `consultar_precio`.

**Reglas de oro:**
- **Nunca inventa** precio, stock, o aplicación. Todo sale de tools.
- **Desambiguación quirúrgica**: si tiene auto + pieza, no pregunta marca preferida (se la ofrece al final).
- Si la confianza del match es baja → muestra opciones, no afirma.

#### 4.3 Agente Cotización / Cierre

**Qué hace:** una vez identificado el producto, aplica las reglas de precio (la lógica que ya teníamos), arma el pedido, reserva stock si corresponde, propone método de pago/entrega.

**Tools:** `aplicar_regla_precio`, `armar_pedido`, `reservar_stock`, `generar_link_pago` (a futuro Mercado Pago).

#### 4.4 Agente Pedido

**Qué hace:** "¿llegó mi pedido?", "¿cuándo está listo?". Lee estado del pedido y responde.

**Tools:** `consultar_pedido`, `consultar_estado_envio`.

#### 4.5 Agente FAQ / Info del comercio

**Qué hace:** horarios, ubicación, métodos de pago, política de devolución. Cosas que vienen de la `persona_config` y de campos de la empresa, no del catálogo.

**Tools:** `consultar_info_empresa`.

#### 4.6 Agente Derivación

**Qué hace:** decide cuándo derivar (porque el router lo pidió, porque otro agente devolvió baja confianza, porque el cliente pidió humano), **arma el resumen de contexto** para que el vendedor no le pregunte al cliente cosas que ya respondió.

**Tools:** `derivar_humano`, `generar_resumen_conversacion`.

El resumen es el activo importante acá. Tiene que tener: cliente + auto + qué busca + qué se le ofreció + dónde se trabó. Es lo que aparece en la bandeja del vendedor.

#### 4.7 Agente Auditor (asincrónico)

**Qué hace:** corre como job nocturno sobre las consultas cerradas del día. Lee la conversación entera y completa la tabla `score_consulta` (sección 5). No interactúa con el cliente.

**Tools:** ninguna. Solo lee.

### El contrato entre el router y los especialistas

Cuando el router decide "agente producto", le pasa esto:

```json
{
  "mensaje_actual": "...",
  "historial_corto": [...últimos 6 mensajes],
  "cliente": {
    "nombre": "Javier",
    "vehiculo_default": {"marca": "VW", "modelo": "Gol", "anio": 2010, "motor": "1.6"},
    "etiquetas": ["recurrente"]
  },
  "consulta_id": 1234,
  "datos_pre_extraidos": {"pieza": "pastillas", "posicion": "delanteras"},
  "config_empresa": {
    "tono": "argentino_cercano",
    "permite_alternativas": true,
    "horario_humano": "L-V 9-18"
  }
}
```

El especialista responde con texto al cliente + acciones laterales (registrar consulta, abrir pedido, etc.). No tiene loop de control — completa su turno y vuelve al orquestador, que decide si re-rutea o cierra.

---

## 5. Puntuación de conversaciones

El score sirve para tres cosas distintas: **mejorar el bot** (revisar las bajas para detectar patrones), **priorizar la bandeja del comercio** (alto valor + bajo score = atender ya), y **detectar catálogo sucio** (si todas las consultas de "amortiguadores Kangoo" puntúan bajo, falta cargar esa aplicación).

### Rúbrica (0-100)

Cinco componentes, cada uno con un máximo:

| Componente | Máx | Cómo se mide |
|---|---|---|
| **Resolución** | 40 | ¿Resolvió la necesidad? |
| **Calidad de datos** | 20 | ¿El catálogo alcanzó? |
| **Eficiencia** | 15 | ¿Preguntó solo lo necesario? |
| **Tono / experiencia** | 15 | ¿El cliente quedó conforme? |
| **Conversión** | 10 | ¿Se materializó acción? |

**Bandas finales:**
- 0–40 → **mala** (revisar)
- 41–70 → **regular**
- 71–100 → **buena**

### Cómo se puntúa cada componente

**Resolución (0-40)** — determinístico, sale de campos de la BD:
```
si consulta.resultado = 'venta'                 → 40
si consulta.resultado = 'cotizacion'            → 30
si consulta.resultado = 'derivacion' Y derivacion.resumen no es null  → 20
si consulta.resultado = 'derivacion' Y resumen pobre  → 10
si consulta.estado = 'abandonada'               → 0
```

**Calidad de datos (0-20)** — determinístico:
```
si todas las búsquedas devolvieron precio + stock + aplicación → 20
si faltó algún dato (ej: precio sí, stock no)                  → 10
si alguna búsqueda devolvió "no encontrado" cuando sí debía estar → 0
```

**Eficiencia (0-15)** — determinístico, cuenta turnos:
```
nro_turnos_desambiguacion = cuántos mensajes del bot pidieron info al cliente
si <= 3  → 15
si 4-6   → 8
si 7+    → 0
```

**Tono (0-15)** — esto sí lo evalúa el LLM auditor con esta rúbrica:
```
+15: cliente expresa satisfacción ("gracias", "buenísimo", "perfecto", emojis +)
+10: cliente neutral, sin fricción
+5:  cliente confuso o tuvo que repetir
0:   cliente expresó frustración ("no me sirve", "mejor humano",
     "no entendiste") o abandonó tras varios turnos
```

**Conversión (0-10)** — determinístico:
```
hubo pedido confirmado     → 10
solo cotización            → 5
nada                       → 0
```

### Prompt del agente auditor

```
Sos un auditor de conversaciones de un bot de autopartes.
Te paso una conversación completa cerrada y los datos estructurados
de la consulta (productos buscados, resultado, pedido si hubo).

Tu tarea es completar este JSON:

{
  "score_tono": 0..15,
  "observaciones": "...",  // 1-2 oraciones explicando qué pasó
  "oportunidades_mejora": [
    "falta_catalogo:<descripcion_pieza_no_encontrada>",
    "desambiguacion_excesiva:<sobre_que>",
    "tono_inadecuado:<que_pasó>",
    ...
  ]
}

Reglas:
- Para "oportunidades_mejora" usa SOLO los tags definidos:
  falta_catalogo, desambiguacion_excesiva, tono_inadecuado,
  derivacion_innecesaria, derivacion_sin_contexto, regla_precio_mal_aplicada.
- Sé conciso en observaciones. No moralices.
- Si la conversación fue buena, "oportunidades_mejora" puede ser [].
```

Los componentes 1, 2, 3 y 5 los calcula un script (`compute_score_components.py`), el 4 lo hace el auditor LLM, y se suman. Una sola fila en `score_consulta`.

### Qué hacemos con el score

**Dashboard del comercio** (vista que ya tienen en el demo):
- Score promedio del mes (con tendencia vs el anterior).
- Top 10 consultas con peor score → botón "revisar".
- Distribución de `oportunidades_mejora`: si "falta_catalogo" se repite mucho, sugerencia automática "cargá estos productos al catálogo".

**Dashboard de ustedes (dueños del producto):**
- Score promedio por comercio → quién está aprovechando bien el bot, quién no.
- Comercios con score bajo + muchas consultas = mala experiencia escalando = riesgo de churn.

**Bandeja del vendedor:**
- Conversaciones derivadas se ordenan por `monto_cotizado * (1 - score_bot/100)` → primero las que el bot no resolvió pero valen plata.

---

## 6. Qué hago yo / qué hacen ustedes

Soy honesto con la división del trabajo porque hay cosas que requieren acceso al entorno de ustedes que yo no tengo.

### Lo que puedo entregar yo (todo lo que está en este doc + extras)

- ✅ Este documento de diseño completo (entregado).
- ✅ El DDL de Postgres listo para pegar en Supabase (está arriba).
- ✅ Los prompts base de los 7 agentes (los esquematicé arriba — puedo escribirlos completos con few-shot y todo si me lo piden).
- ✅ El algoritmo de scoring en pseudocódigo (arriba).
- ✅ Si me dan un Excel real de un autopartista piloto, **puedo prototipar** el cargador a la base normalizada y mostrarles cómo queda.
- ✅ Puedo escribir el script Python del job de scoring (componentes 1-3-5 determinísticos + llamada al auditor) listo para deployar.
- ✅ Puedo escribir el código del router en Python con la llamada al LLM y la lógica de "cuenta como consulta o no".

### Lo que tienen que hacer ustedes (necesita su infra)

- 🔧 **Deployar Postgres** (Supabase recomendado: te da auth, RLS, storage para audios e imágenes, dashboard, y backup automatizado).
- 🔧 **Verificar el WhatsApp Business Account** con Meta y conseguir el `phone_number_id` + `access_token` del comercio piloto. Esto toma 5-10 días por la revisión de Meta — empezar ya.
- 🔧 **Servidor para el orquestador** (Cloud Run, Vercel, AWS Lambda — cualquiera sirve, sin estado interno).
- 🔧 **Elegir LLM y conseguir API keys**: Claude Sonnet 4 o GPT-4 para los especialistas, Haiku/Mini para el router, Whisper o equivalente para STT (audios). Los costos varían — recomiendo armar un sheet de "costo estimado por consulta" para confirmar el `$0,034` que pusimos en el dashboard.
- 🔧 **Conseguir el Excel real** del autopartista piloto (es lo que más nos va a destrabar — sin datos reales todo lo que probemos es teórico).
- 🔧 **Definir quién opera la bandeja del vendedor** en el comercio piloto y entrenarlo (no es un proyecto técnico — es un proyecto de cambio en su operación).

### Lo que no podemos resolver solos (depende de terceros)

- ❓ Si Tapice/Lupa van a dar API o solo Excel — preguntarles esta semana.
- ❓ Tarifas exactas de Meta para Argentina en mensajes de marketing/utilidad — confirmar al cotizar planes.
- ❓ Si el comercio piloto está dispuesto a que el bot derive en tiempo real (cambia su operación) — esto es venta consultiva, no técnica.

---

## 7. Próximos pasos sugeridos (2 semanas)

**Semana 1**
1. Aprobar este diseño en reunión con Eze, Seba, Fran.
2. Crear el proyecto Supabase + correr todo el DDL.
3. Iniciar verificación de WABA con Meta (en paralelo, porque tarda).
4. Conseguir el Excel del autopartista piloto.

**Semana 2**
5. Construir el cargador del Excel → catálogo normalizado (yo lo puedo arrancar si me pasan un Excel de muestra anonimizado).
6. Implementar el router + agente Producto (los dos primeros, los demás van detrás).
7. Endpoint webhook de WhatsApp recibiendo mensajes y guardándolos en la BD.

**Semana 3 (Etapa 2 arranca acá)**
8. Resto de agentes + scoring nocturno + dashboard básico de métricas.

---

*Documento vivo. Las decisiones de este doc son las que conviene cerrar antes de empezar a escribir código en serio — cambiarlas después cuesta refactor.*
