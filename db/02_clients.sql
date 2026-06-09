-- =====================================================
-- 02_clients.sql
-- Esquema de clientes finales, sus canales y vehículos.
-- =====================================================

CREATE TABLE IF NOT EXISTS cliente (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  nombre TEXT,
  apellido TEXT,
  email TEXT,
  notas TEXT,
  etiquetas JSONB DEFAULT '[]'::jsonb,
  creado_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ultimo_contacto_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_cliente_empresa ON cliente(empresa_id);

CREATE TABLE IF NOT EXISTS contact_channel (
  id BIGSERIAL PRIMARY KEY,
  cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,
  identificador TEXT NOT NULL,
  verificado BOOLEAN NOT NULL DEFAULT false,
  UNIQUE(tipo, identificador)
);

CREATE INDEX IF NOT EXISTS idx_canal_cliente ON contact_channel(cliente_id);

CREATE TABLE IF NOT EXISTS vehiculo_cliente (
  id BIGSERIAL PRIMARY KEY,
  cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
  marca TEXT NOT NULL,
  modelo TEXT NOT NULL,
  anio INT,
  motor TEXT,
  patente TEXT,
  notas TEXT
);

CREATE INDEX IF NOT EXISTS idx_vehiculo_cliente ON vehiculo_cliente(cliente_id);

-- Función para obtener o crear cliente por canal (idempotente)
CREATE OR REPLACE FUNCTION fn_get_or_create_cliente(
  p_empresa_id BIGINT,
  p_canal_tipo TEXT,
  p_canal_identificador TEXT
) RETURNS BIGINT AS $$
DECLARE
  v_cliente_id BIGINT;
BEGIN
  SELECT c.id INTO v_cliente_id
    FROM cliente c
    JOIN contact_channel cc ON cc.cliente_id = c.id
   WHERE c.empresa_id = p_empresa_id
     AND cc.tipo = p_canal_tipo
     AND cc.identificador = p_canal_identificador
   LIMIT 1;

  IF v_cliente_id IS NULL THEN
    INSERT INTO cliente (empresa_id) VALUES (p_empresa_id) RETURNING id INTO v_cliente_id;
    INSERT INTO contact_channel (cliente_id, tipo, identificador)
      VALUES (v_cliente_id, p_canal_tipo, p_canal_identificador);
  END IF;

  UPDATE cliente SET ultimo_contacto_at = now() WHERE id = v_cliente_id;
  RETURN v_cliente_id;
END;
$$ LANGUAGE plpgsql;
