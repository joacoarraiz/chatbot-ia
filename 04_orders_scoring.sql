-- =====================================================
-- 04_orders_scoring.sql
-- Pedidos, items de pedido, derivaciones a humano y
-- scoring (puntuación) de cada consulta.
-- Correr DESPUÉS de 03_conversations.sql.
-- =====================================================

-- ----- PEDIDO -----
CREATE TABLE IF NOT EXISTS pedido (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  cliente_id BIGINT REFERENCES cliente,
  consulta_id BIGINT REFERENCES consulta,

  numero TEXT,                                  -- "PED-2025-0001", legible para el comercio
  estado TEXT DEFAULT 'borrador',               -- 'borrador'|'confirmado'|'pagado'|'entregado'|'cancelado'
  monto_total NUMERIC(12,2),

  metodo_pago TEXT,                             -- 'efectivo'|'transferencia'|'mp'|'tarjeta'
  metodo_entrega TEXT,                          -- 'retira'|'envio'|'moto'
  direccion_envio TEXT,

  notas TEXT,
  creado_at TIMESTAMPTZ DEFAULT now(),
  confirmado_at TIMESTAMPTZ,
  entregado_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pedido_empresa_estado
  ON pedido(empresa_id, estado);
CREATE INDEX IF NOT EXISTS idx_pedido_cliente ON pedido(cliente_id);

-- ----- ITEMS DEL PEDIDO -----
CREATE TABLE IF NOT EXISTS pedido_item (
  id BIGSERIAL PRIMARY KEY,
  pedido_id BIGINT REFERENCES pedido ON DELETE CASCADE,
  producto_id BIGINT REFERENCES producto_logico,
  oferta_id BIGINT REFERENCES oferta,           -- de qué fuente se está vendiendo
  cantidad INT NOT NULL DEFAULT 1,
  precio_unitario NUMERIC(12,2) NOT NULL,
  subtotal NUMERIC(12,2) NOT NULL,
  descuento NUMERIC(12,2) DEFAULT 0,
  notas TEXT
);
CREATE INDEX IF NOT EXISTS idx_item_pedido ON pedido_item(pedido_id);

-- ----- DERIVACIÓN A HUMANO -----
CREATE TABLE IF NOT EXISTS derivacion (
  id BIGSERIAL PRIMARY KEY,
  conversacion_id BIGINT REFERENCES conversacion,
  consulta_id BIGINT REFERENCES consulta,

  motivo TEXT NOT NULL,                         -- 'cliente_pidio'|'baja_confianza'|'fuera_alcance'|'fuera_horario'
  resumen TEXT NOT NULL,                        -- el contexto armado por el agente derivador
  prioridad TEXT DEFAULT 'normal',              -- 'baja'|'normal'|'alta'

  asignado_a BIGINT,                            -- user_id del vendedor (cuando exista auth)
  asignado_at TIMESTAMPTZ,

  creado_at TIMESTAMPTZ DEFAULT now(),
  resuelta_at TIMESTAMPTZ,
  resolucion TEXT                               -- texto libre de cómo se cerró
);
CREATE INDEX IF NOT EXISTS idx_deriv_conv ON derivacion(conversacion_id);
CREATE INDEX IF NOT EXISTS idx_deriv_asignado ON derivacion(asignado_a, resuelta_at);

-- ----- SCORE DE CONSULTA (★ puntuación) -----
-- Lee la sección 5 del diseño técnico antes de tocar esto.
CREATE TABLE IF NOT EXISTS score_consulta (
  id BIGSERIAL PRIMARY KEY,
  consulta_id BIGINT REFERENCES consulta ON DELETE CASCADE UNIQUE,

  -- Componentes (suman 100)
  score_resolucion INT,                         -- 0-40 (determinístico)
  score_datos INT,                              -- 0-20 (determinístico)
  score_eficiencia INT,                         -- 0-15 (determinístico)
  score_tono INT,                               -- 0-15 (LLM auditor)
  score_conversion INT,                         -- 0-10 (determinístico)
  score_total INT,                              -- 0-100

  banda TEXT,                                   -- 'mala'|'regular'|'buena'
  observaciones TEXT,                           -- redactadas por el agente auditor
  oportunidades_mejora JSONB,                   -- ['falta_catalogo:pastilla_kangoo_diesel', ...]

  evaluado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_score_banda ON score_consulta(banda);
CREATE INDEX IF NOT EXISTS idx_score_total ON score_consulta(score_total);

-- ----- Vista útil: salud del bot por empresa -----
CREATE OR REPLACE VIEW v_salud_bot_empresa AS
SELECT
  e.id AS empresa_id,
  e.nombre AS empresa,
  COUNT(s.id) AS consultas_puntuadas,
  ROUND(AVG(s.score_total), 1) AS score_promedio,
  COUNT(*) FILTER (WHERE s.banda = 'buena') AS buenas,
  COUNT(*) FILTER (WHERE s.banda = 'regular') AS regulares,
  COUNT(*) FILTER (WHERE s.banda = 'mala') AS malas,
  ROUND(100.0 * COUNT(*) FILTER (WHERE s.banda = 'buena') / NULLIF(COUNT(s.id), 0), 1)
    AS pct_buenas
FROM empresa e
LEFT JOIN consulta c ON c.empresa_id = e.id
LEFT JOIN score_consulta s ON s.consulta_id = c.id
WHERE c.iniciada_at >= now() - INTERVAL '30 days'
GROUP BY e.id;

-- ----- Vista útil: oportunidades de mejora más frecuentes -----
-- Sirve para que el comercio vea "qué le falta al bot" priorizado.
CREATE OR REPLACE VIEW v_oportunidades_top AS
SELECT
  c.empresa_id,
  jsonb_array_elements_text(s.oportunidades_mejora) AS oportunidad,
  COUNT(*) AS frecuencia
FROM score_consulta s
JOIN consulta c ON c.id = s.consulta_id
WHERE s.evaluado_at >= now() - INTERVAL '30 days'
GROUP BY c.empresa_id, oportunidad
ORDER BY frecuencia DESC;
