-- =====================================================
-- 03_conversations.sql
-- Conversaciones, mensajes, consultas (agrupación de intención).
-- =====================================================

CREATE TABLE IF NOT EXISTS conversacion (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
  canal_tipo TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'abierta',
  iniciada_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  cerrada_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_conv_empresa_estado ON conversacion(empresa_id, estado);

CREATE TABLE IF NOT EXISTS mensaje (
  id BIGSERIAL PRIMARY KEY,
  conversacion_id BIGINT NOT NULL REFERENCES conversacion(id) ON DELETE CASCADE,
  direccion TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'texto',
  contenido TEXT,
  media_url TEXT,
  whatsapp_msg_id TEXT,
  creado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mensaje_conv ON mensaje(conversacion_id);

CREATE TABLE IF NOT EXISTS consulta (
  id BIGSERIAL PRIMARY KEY,
  conversacion_id BIGINT NOT NULL REFERENCES conversacion(id) ON DELETE CASCADE,
  intencion TEXT,
  estado TEXT NOT NULL DEFAULT 'abierta',
  iniciada_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  cerrada_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_consulta_conv ON consulta(conversacion_id);

CREATE TABLE IF NOT EXISTS intencion_log (
  id BIGSERIAL PRIMARY KEY,
  consulta_id BIGINT NOT NULL REFERENCES consulta(id) ON DELETE CASCADE,
  intencion TEXT NOT NULL,
  confianza NUMERIC(3,2),
  datos JSONB,
  creado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Vista de consultas del mes actual (para facturación)
CREATE OR REPLACE VIEW v_consultas_mes_actual AS
SELECT c.empresa_id, COUNT(*) AS consultas
  FROM consulta cs
  JOIN conversacion c ON c.id = cs.conversacion_id
 WHERE date_trunc('month', cs.iniciada_at) = date_trunc('month', now())
 GROUP BY c.empresa_id;

-- Función para cerrar consultas inactivas (>30 min sin mensaje)
CREATE OR REPLACE FUNCTION fn_cerrar_consultas_inactivas() RETURNS INT AS $$
DECLARE
  v_count INT;
BEGIN
  UPDATE consulta SET estado = 'cerrada', cerrada_at = now()
   WHERE estado = 'abierta'
     AND id IN (
       SELECT cs.id FROM consulta cs
        JOIN conversacion c ON c.id = cs.conversacion_id
        LEFT JOIN mensaje m ON m.conversacion_id = c.id
        WHERE cs.estado = 'abierta'
        GROUP BY cs.id
       HAVING MAX(m.creado_at) < now() - INTERVAL '30 minutes'
     );
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$ LANGUAGE plpgsql;
