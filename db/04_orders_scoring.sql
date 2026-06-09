-- =====================================================
-- 04_orders_scoring.sql
-- Pedidos, derivaciones a humano, scoring de conversaciones.
-- =====================================================

CREATE TABLE IF NOT EXISTS pedido (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
  consulta_id BIGINT REFERENCES consulta(id),
  total NUMERIC(12,2) NOT NULL DEFAULT 0,
  estado TEXT NOT NULL DEFAULT 'borrador',
  creado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pedido_item (
  id BIGSERIAL PRIMARY KEY,
  pedido_id BIGINT NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
  producto_id BIGINT NOT NULL REFERENCES producto_logico(id),
  cantidad INT NOT NULL DEFAULT 1,
  precio_unitario NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS derivacion (
  id BIGSERIAL PRIMARY KEY,
  consulta_id BIGINT NOT NULL REFERENCES consulta(id) ON DELETE CASCADE,
  motivo TEXT,
  resumen_contexto TEXT,
  valor_cotizado NUMERIC(12,2),
  estado TEXT NOT NULL DEFAULT 'pendiente',
  asignado_a TEXT,
  creado_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resuelto_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS score_consulta (
  id BIGSERIAL PRIMARY KEY,
  consulta_id BIGINT NOT NULL REFERENCES consulta(id) ON DELETE CASCADE,
  score INT NOT NULL,
  componente_1 INT,
  componente_2 INT,
  componente_3 INT,
  componente_4 INT,
  componente_5_tono INT,
  oportunidades_mejora JSONB,
  evaluado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Vista de salud del bot por empresa
CREATE OR REPLACE VIEW v_salud_bot AS
SELECT c.empresa_id,
       COUNT(DISTINCT cs.id) AS consultas_total,
       AVG(sc.score)::INT AS score_promedio,
       COUNT(DISTINCT d.id) FILTER (WHERE d.estado = 'pendiente') AS derivaciones_pendientes
  FROM consulta cs
  JOIN conversacion c ON c.id = cs.conversacion_id
  LEFT JOIN score_consulta sc ON sc.consulta_id = cs.id
  LEFT JOIN derivacion d ON d.consulta_id = cs.id
 WHERE date_trunc('day', cs.iniciada_at) >= now() - INTERVAL '7 days'
 GROUP BY c.empresa_id;
