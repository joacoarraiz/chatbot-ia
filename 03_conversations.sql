-- =====================================================
-- 03_conversations.sql
-- Conversaciones, mensajes individuales, consultas
-- (la unidad de facturación) y log del router.
-- Correr DESPUÉS de 02_clients.sql.
-- =====================================================

-- ----- CONVERSACIÓN -----
-- Una "sesión" de chat con un cliente. Una conversación puede
-- contener múltiples consultas (cambios de intención).
CREATE TABLE IF NOT EXISTS conversacion (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  cliente_id BIGINT REFERENCES cliente,
  canal TEXT NOT NULL,                          -- 'whatsapp'|'ml'|'web'
  abierta_at TIMESTAMPTZ DEFAULT now(),
  cerrada_at TIMESTAMPTZ,
  cerrada_por TEXT,                             -- 'inactividad'|'cliente'|'derivacion'|'venta'
  estado TEXT DEFAULT 'activa'                  -- 'activa'|'derivada'|'cerrada'
);
CREATE INDEX IF NOT EXISTS idx_conv_empresa_estado
  ON conversacion(empresa_id, estado);
CREATE INDEX IF NOT EXISTS idx_conv_cliente ON conversacion(cliente_id);
CREATE INDEX IF NOT EXISTS idx_conv_abierta ON conversacion(abierta_at DESC);

-- ----- CONSULTA (★ unidad de facturación) -----
-- Lee bien la sección 1 del diseño técnico antes de tocar esto.
CREATE TABLE IF NOT EXISTS consulta (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  conversacion_id BIGINT REFERENCES conversacion,
  cliente_id BIGINT REFERENCES cliente,

  intencion TEXT NOT NULL,                      -- 'buscar_producto'|'cotizacion'|'estado_pedido'|'faq'|'humano'
  estado TEXT DEFAULT 'abierta',                -- 'abierta'|'resuelta'|'derivada'|'abandonada'
  resultado TEXT,                               -- 'venta'|'cotizacion'|'derivacion'|'sin_resultado'

  productos_consultados BIGINT[],               -- IDs de producto_logico
  vehiculo_id BIGINT REFERENCES vehiculo_cliente,
  monto_cotizado NUMERIC(12,2),

  iniciada_at TIMESTAMPTZ DEFAULT now(),
  cerrada_at TIMESTAMPTZ,

  -- Costos
  tokens_input INT DEFAULT 0,
  tokens_output INT DEFAULT 0,
  costo_ia_usd NUMERIC(10,5) DEFAULT 0,

  -- Metadata
  motivo_cierre TEXT,                           -- por qué se cerró
  notas TEXT
);
CREATE INDEX IF NOT EXISTS idx_consulta_empresa_iniciada
  ON consulta(empresa_id, iniciada_at);
CREATE INDEX IF NOT EXISTS idx_consulta_cliente ON consulta(cliente_id);
CREATE INDEX IF NOT EXISTS idx_consulta_estado ON consulta(estado);
CREATE INDEX IF NOT EXISTS idx_consulta_conv ON consulta(conversacion_id);

-- ----- MENSAJE -----
-- Cada mensaje individual. Algunos NO atan a consulta (saludos, gracias).
CREATE TABLE IF NOT EXISTS mensaje (
  id BIGSERIAL PRIMARY KEY,
  conversacion_id BIGINT REFERENCES conversacion ON DELETE CASCADE,
  consulta_id BIGINT REFERENCES consulta,       -- nullable

  emisor TEXT NOT NULL,                         -- 'cliente'|'bot'|'humano'
  agente TEXT,                                  -- 'router'|'producto'|'cotizacion'|etc, si emisor='bot'

  contenido TEXT,                               -- texto del mensaje (post-STT si era audio)
  tipo_media TEXT DEFAULT 'texto',              -- 'texto'|'audio'|'imagen'|'documento'
  media_url TEXT,                               -- link al archivo en storage

  -- Metadata interna
  metadata JSONB,                               -- tokens, latencia, intent detectado, etc.
  whatsapp_msg_id TEXT,                         -- el wamid de Meta, para referencias

  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON mensaje(conversacion_id, creado_at);
CREATE INDEX IF NOT EXISTS idx_msg_consulta ON mensaje(consulta_id);
CREATE INDEX IF NOT EXISTS idx_msg_wamid ON mensaje(whatsapp_msg_id);

-- ----- LOG DEL ROUTER -----
-- Cada vez que el router clasifica, deja registro. Sirve para mejorar el bot.
CREATE TABLE IF NOT EXISTS intencion_log (
  id BIGSERIAL PRIMARY KEY,
  mensaje_id BIGINT REFERENCES mensaje ON DELETE CASCADE,
  intencion_detectada TEXT,
  confianza NUMERIC(3,2),
  agente_asignado TEXT,
  cuenta_como_consulta BOOLEAN,
  datos_extraidos JSONB,                        -- {marca_auto, modelo, anio, pieza, codigo}
  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_intent_mensaje ON intencion_log(mensaje_id);

-- ----- Función helper: cerrar consultas por inactividad -----
-- Corre cada N minutos (cron job). Cierra consultas con +30 min sin actividad.
CREATE OR REPLACE FUNCTION fn_cerrar_consultas_inactivas()
RETURNS INT AS $$
DECLARE
  v_cerradas INT;
BEGIN
  WITH inactivas AS (
    SELECT c.id
      FROM consulta c
     WHERE c.estado = 'abierta'
       AND NOT EXISTS (
         SELECT 1 FROM mensaje m
          WHERE m.consulta_id = c.id
            AND m.creado_at > now() - INTERVAL '30 minutes'
       )
  )
  UPDATE consulta
     SET estado = 'abandonada',
         cerrada_at = now(),
         motivo_cierre = 'inactividad'
   WHERE id IN (SELECT id FROM inactivas);

  GET DIAGNOSTICS v_cerradas = ROW_COUNT;
  RETURN v_cerradas;
END;
$$ LANGUAGE plpgsql;

-- ----- Vista útil: consultas del mes por empresa -----
CREATE OR REPLACE VIEW v_consultas_mes_actual AS
SELECT
  e.id AS empresa_id,
  e.nombre AS empresa,
  e.plan,
  e.consultas_limite,
  COUNT(c.id) AS consultas_usadas,
  e.consultas_limite - COUNT(c.id) AS consultas_restantes,
  ROUND(100.0 * COUNT(c.id) / NULLIF(e.consultas_limite, 0), 1) AS porcentaje_usado
FROM empresa e
LEFT JOIN consulta c
  ON c.empresa_id = e.id
 AND c.iniciada_at >= date_trunc('month', now())
GROUP BY e.id;
