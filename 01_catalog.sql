-- =====================================================
-- 01_catalog.sql
-- Catálogo: empresas, fuentes, productos, ofertas,
-- aplicaciones, equivalencias y reglas de precio.
-- Correr PRIMERO. Idempotente (se puede correr varias veces).
-- =====================================================

-- ----- EMPRESA (multi-tenant) -----
CREATE TABLE IF NOT EXISTS empresa (
  id BIGSERIAL PRIMARY KEY,
  nombre TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'prueba',          -- 'prueba'|'basico'|'pro'
  consultas_limite INT NOT NULL DEFAULT 100,
  persona_config JSONB,                         -- tono, jerga, branding, derivación
  whatsapp_phone_id TEXT,                       -- ID del número en Meta
  whatsapp_business_id TEXT,                    -- ID del WABA
  horario_atencion JSONB,                       -- {"lun":"9-18", ...}
  zona_horaria TEXT DEFAULT 'America/Argentina/Buenos_Aires',
  activo BOOLEAN DEFAULT true,
  creado_at TIMESTAMPTZ DEFAULT now()
);
COMMENT ON TABLE empresa IS 'Cada autopartista que contrata Toni';

-- ----- FUENTE DE CATÁLOGO -----
-- Cada origen de datos: API, Excel, Drive, etc.
CREATE TABLE IF NOT EXISTS fuente_catalogo (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  nombre TEXT NOT NULL,
  tipo TEXT NOT NULL,                           -- 'api'|'excel'|'csv'|'drive'|'scraping'
  mapeo JSONB,                                  -- plantilla columna→campo
  config JSONB,                                 -- credenciales/URL/path
  sincronizado_at TIMESTAMPTZ,
  estado TEXT DEFAULT 'activa',                 -- 'activa'|'pausada'|'error'
  ultimo_error TEXT,
  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fuente_empresa ON fuente_catalogo(empresa_id);

-- ----- PRODUCTO LÓGICO -----
-- La pieza canónica. Una sola por empresa, aunque venga en varios catálogos.
CREATE TABLE IF NOT EXISTS producto_logico (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  descripcion TEXT NOT NULL,
  marca_pieza TEXT,
  linea TEXT,                                   -- frenos, motor, suspensión...
  atributos JSONB,                              -- material, especificaciones, etc.
  imagen_url TEXT,
  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_producto_empresa ON producto_logico(empresa_id);
CREATE INDEX IF NOT EXISTS idx_producto_marca ON producto_logico(empresa_id, marca_pieza);
CREATE INDEX IF NOT EXISTS idx_producto_linea ON producto_logico(empresa_id, linea);
-- Búsqueda full-text en español
CREATE INDEX IF NOT EXISTS idx_producto_descripcion
  ON producto_logico USING gin(to_tsvector('spanish', descripcion));

-- ----- OFERTA -----
-- ★ Mismo producto, distinta fuente y precio.
-- Acá vive la solución a "varios catálogos con el mismo producto a distinto precio".
CREATE TABLE IF NOT EXISTS oferta (
  id BIGSERIAL PRIMARY KEY,
  producto_id BIGINT REFERENCES producto_logico ON DELETE CASCADE,
  fuente_id BIGINT REFERENCES fuente_catalogo,
  codigo_en_fuente TEXT,
  precio NUMERIC(12,2),
  costo NUMERIC(12,2),
  stock INT DEFAULT 0,
  deposito TEXT,
  url_origen TEXT,                              -- link al producto si la fuente es web
  actualizado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_oferta_producto ON oferta(producto_id);
CREATE INDEX IF NOT EXISTS idx_oferta_codigo ON oferta(codigo_en_fuente);
CREATE INDEX IF NOT EXISTS idx_oferta_fuente_stock ON oferta(fuente_id, stock);

-- ----- APLICACIÓN -----
-- A qué vehículos calza un producto.
CREATE TABLE IF NOT EXISTS aplicacion (
  id BIGSERIAL PRIMARY KEY,
  producto_id BIGINT REFERENCES producto_logico ON DELETE CASCADE,
  auto_marca TEXT NOT NULL,
  modelo TEXT NOT NULL,
  anio_desde INT,
  anio_hasta INT,
  motor TEXT,
  posicion TEXT,                                -- delantero/trasero, izq/der, etc.
  notas TEXT
);
CREATE INDEX IF NOT EXISTS idx_aplic_producto ON aplicacion(producto_id);
CREATE INDEX IF NOT EXISTS idx_aplic_auto
  ON aplicacion(auto_marca, modelo, anio_desde, anio_hasta);

-- ----- EQUIVALENCIA -----
-- Códigos de otras marcas / OEM que apuntan al mismo producto lógico.
CREATE TABLE IF NOT EXISTS equivalencia (
  id BIGSERIAL PRIMARY KEY,
  producto_id BIGINT REFERENCES producto_logico ON DELETE CASCADE,
  tipo TEXT NOT NULL,                           -- 'oem'|'cruzada'
  codigo_externo TEXT NOT NULL,
  marca_externa TEXT,
  confianza NUMERIC(3,2) DEFAULT 1.0,           -- 0..1, evita fusiones dudosas
  fuente TEXT,                                  -- de dónde salió esta equivalencia
  notas TEXT
);
CREATE INDEX IF NOT EXISTS idx_equiv_producto ON equivalencia(producto_id);
CREATE INDEX IF NOT EXISTS idx_equiv_codigo ON equivalencia(codigo_externo);

-- ----- REGLA DE PRECIO -----
-- ★ Define qué oferta gana cuando hay varias para el mismo producto.
-- Funciona como especificidad de CSS: gana la más específica.
CREATE TABLE IF NOT EXISTS regla_precio (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT REFERENCES empresa ON DELETE CASCADE,
  ambito TEXT NOT NULL,                         -- 'producto'|'marca'|'linea'|'global'
  ambito_valor TEXT,                            -- id, marca, línea o NULL si global
  estrategia TEXT NOT NULL,                     -- 'lista_fija'|'menor_precio'|'mayor_margen'|'fallback'
  fuente_preferida_id BIGINT REFERENCES fuente_catalogo,
  orden_fallback BIGINT[],                      -- array de fuente_ids
  requiere_stock BOOLEAN DEFAULT true,
  prioridad INT NOT NULL,                       -- producto=100, marca=50, linea=30, global=0
  activa BOOLEAN DEFAULT true,
  creado_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_regla_empresa_prioridad
  ON regla_precio(empresa_id, prioridad DESC);

-- ----- Vista útil: precio recomendado por producto -----
-- Se puede consultar como tabla pero recalcula al vuelo.
-- Esta es una versión simple; la real va a estar en una función PL/pgSQL.
CREATE OR REPLACE VIEW v_producto_con_precio AS
SELECT
  p.id AS producto_id,
  p.empresa_id,
  p.descripcion,
  p.marca_pieza,
  p.linea,
  (SELECT o.precio FROM oferta o
     WHERE o.producto_id = p.id AND o.stock > 0
     ORDER BY o.precio ASC LIMIT 1) AS precio_min_con_stock,
  (SELECT COUNT(*) FROM oferta o
     WHERE o.producto_id = p.id AND o.stock > 0) AS fuentes_con_stock,
  (SELECT SUM(o.stock) FROM oferta o WHERE o.producto_id = p.id) AS stock_total
FROM producto_logico p;
