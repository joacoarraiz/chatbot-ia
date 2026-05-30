-- =====================================================
-- 02_clients.sql
-- Clientes finales (los que chatean con el bot),
-- sus identidades por canal y sus vehículos.
-- Correr DESPUÉS de 01_catalog.sql.
-- =====================================================

-- ----- CLIENTE -----
-- Un cliente final, con stats agregadas.
-- Identidad por (empresa, persona): el mismo número puede ser cliente
-- de 2 comercios distintos y se trata como dos clientes diferentes.
CREATE TABLE IF NOT EXISTS cliente (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  nombre TEXT,                                  -- si lo dio en algún momento
  tipo TEXT DEFAULT 'b2c',                      -- 'b2c'|'b2b'
  notas TEXT,                                   -- texto libre del CRM
  preferencias JSONB,                           -- {"original": true, "retira_local": true}

  -- Stats agregadas (recalculadas por job nocturno)
  total_consultas INT DEFAULT 0,
  total_compras INT DEFAULT 0,
  monto_acumulado NUMERIC(14,2) DEFAULT 0,
  primera_actividad_at TIMESTAMPTZ,
  ultima_actividad_at TIMESTAMPTZ,

  -- Etiquetas calculadas: 'recurrente', 'candidato_b2b', 'dormido', 'frio'
  etiquetas TEXT[],

  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cliente_empresa ON cliente(empresa_id);
CREATE INDEX IF NOT EXISTS idx_cliente_ultima
  ON cliente(empresa_id, ultima_actividad_at DESC);
CREATE INDEX IF NOT EXISTS idx_cliente_etiquetas
  ON cliente USING gin(etiquetas);

-- ----- CONTACT CHANNEL -----
-- Identificadores del cliente en cada canal (WhatsApp, ML, web, etc).
-- Permite unir al mismo cliente que aparece en varios canales.
CREATE TABLE IF NOT EXISTS contact_channel (
  id BIGSERIAL PRIMARY KEY,
  cliente_id BIGINT REFERENCES cliente ON DELETE CASCADE,
  canal TEXT NOT NULL,                          -- 'whatsapp'|'ml'|'web'|'instagram'
  identificador TEXT NOT NULL,                  -- E.164 / user_id / session_id
  display_name TEXT,                            -- nombre que muestra el canal
  verificado BOOLEAN DEFAULT true,
  creado_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(canal, identificador)
);
CREATE INDEX IF NOT EXISTS idx_cc_cliente ON contact_channel(cliente_id);
CREATE INDEX IF NOT EXISTS idx_cc_canal_id ON contact_channel(canal, identificador);

-- ----- VEHÍCULO DEL CLIENTE -----
-- Los autos asociados a un cliente. Memoria del bot.
CREATE TABLE IF NOT EXISTS vehiculo_cliente (
  id BIGSERIAL PRIMARY KEY,
  cliente_id BIGINT REFERENCES cliente ON DELETE CASCADE,
  marca TEXT NOT NULL,
  modelo TEXT NOT NULL,
  anio INT,
  motor TEXT,                                   -- "1.6", "1.4 TDI", etc.
  version TEXT,
  patente TEXT,
  es_default BOOLEAN DEFAULT false,             -- el que el bot asume por defecto
  notas TEXT,                                   -- "este lo usa la esposa", etc.
  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_veh_cliente ON vehiculo_cliente(cliente_id);

-- ----- Trigger para asegurar que solo haya UN default por cliente -----
CREATE OR REPLACE FUNCTION fn_un_default_por_cliente()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.es_default = true THEN
    UPDATE vehiculo_cliente
       SET es_default = false
     WHERE cliente_id = NEW.cliente_id
       AND id <> NEW.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_un_default_vehiculo ON vehiculo_cliente;
CREATE TRIGGER trg_un_default_vehiculo
  BEFORE INSERT OR UPDATE ON vehiculo_cliente
  FOR EACH ROW EXECUTE FUNCTION fn_un_default_por_cliente();

-- ----- Función helper: buscar o crear cliente desde un canal -----
-- Es la que llama el webhook cuando entra un mensaje nuevo.
CREATE OR REPLACE FUNCTION fn_get_or_create_cliente(
  p_empresa_id BIGINT,
  p_canal TEXT,
  p_identificador TEXT,
  p_display_name TEXT DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
  v_cliente_id BIGINT;
BEGIN
  -- ¿Ya existe el contact_channel?
  SELECT cliente_id INTO v_cliente_id
    FROM contact_channel
   WHERE canal = p_canal AND identificador = p_identificador;

  IF v_cliente_id IS NOT NULL THEN
    -- Validar que sea de esta empresa; si no, hay que crearle uno nuevo
    PERFORM 1 FROM cliente
     WHERE id = v_cliente_id AND empresa_id = p_empresa_id;
    IF FOUND THEN
      RETURN v_cliente_id;
    END IF;
  END IF;

  -- Crear cliente nuevo + contact_channel
  INSERT INTO cliente (empresa_id, nombre, primera_actividad_at, ultima_actividad_at)
       VALUES (p_empresa_id, p_display_name, now(), now())
    RETURNING id INTO v_cliente_id;

  INSERT INTO contact_channel (cliente_id, canal, identificador, display_name)
       VALUES (v_cliente_id, p_canal, p_identificador, p_display_name)
  ON CONFLICT (canal, identificador) DO NOTHING;

  RETURN v_cliente_id;
END;
$$ LANGUAGE plpgsql;
