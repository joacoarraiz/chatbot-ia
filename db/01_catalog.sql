-- =====================================================
-- 01_catalog.sql
-- Esquema del catálogo: empresas, fuentes, productos lógicos,
-- ofertas concretas, aplicaciones a vehículos, equivalencias OEM
-- y reglas de precio.
-- =====================================================

-- Empresas (cada cliente de Toni es una empresa)
CREATE TABLE IF NOT EXISTS empresa (
  id BIGSERIAL PRIMARY KEY,
  nombre TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'basico',
  consultas_limite INT NOT NULL DEFAULT 1500,
  persona_config JSONB DEFAULT '{}'::jsonb,
  zona_horaria TEXT NOT NULL DEFAULT 'America/Argentina/Buenos_Aires',
  estado TEXT NOT NULL DEFAULT 'activa',
  creado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fuentes de catálogo (cada empresa puede tener N fuentes: Excel, Drive, etc.)
CREATE TABLE IF NOT EXISTS fuente_catalogo (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  nombre TEXT NOT NULL,
  tipo TEXT NOT NULL,
  sincronizado_at TIMESTAMPTZ,
  estado TEXT NOT NULL DEFAULT 'activa'
);

-- Producto lógico (la "idea" del producto: pastilla de freno X)
CREATE TABLE IF NOT EXISTS producto_logico (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  descripcion TEXT NOT NULL,
  marca_pieza TEXT,
  linea TEXT,
  atributos JSONB DEFAULT '{}'::jsonb,
  creado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_producto_empresa ON producto_logico(empresa_id);
CREATE INDEX IF NOT EXISTS idx_producto_descripcion_fts
  ON producto_logico USING GIN (to_tsvector('spanish', descripcion));

-- Oferta concreta (mismo producto puede venir de distintas fuentes a distintos precios)
CREATE TABLE IF NOT EXISTS oferta (
  id BIGSERIAL PRIMARY KEY,
  producto_id BIGINT NOT NULL REFERENCES producto_logico(id) ON DELETE CASCADE,
  fuente_id BIGINT NOT NULL REFERENCES fuente_catalogo(id) ON DELETE CASCADE,
  codigo_en_fuente TEXT NOT NULL,
  precio NUMERIC(12,2),
  costo NUMERIC(12,2),
  stock INT NOT NULL DEFAULT 0,
  deposito TEXT DEFAULT 'principal',
  actualizado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_oferta_producto ON oferta(producto_id);
CREATE INDEX IF NOT EXISTS idx_oferta_codigo ON oferta(codigo_en_fuente);

-- Aplicación a vehículos (a qué autos sirve cada producto)
CREATE TABLE IF NOT EXISTS aplicacion (
  id BIGSERIAL PRIMARY KEY,
  producto_id BIGINT NOT NULL REFERENCES producto_logico(id) ON DELETE CASCADE,
  auto_marca TEXT NOT NULL,
  modelo TEXT NOT NULL,
  anio_desde INT,
  anio_hasta INT,
  motor TEXT,
  posicion TEXT,
  notas TEXT
);

CREATE INDEX IF NOT EXISTS idx_aplicacion_producto ON aplicacion(producto_id);
CREATE INDEX IF NOT EXISTS idx_aplicacion_marca_modelo ON aplicacion(auto_marca, modelo);

-- Equivalencias OEM (códigos cruzados)
CREATE TABLE IF NOT EXISTS equivalencia (
  id BIGSERIAL PRIMARY KEY,
  producto_id BIGINT NOT NULL REFERENCES producto_logico(id) ON DELETE CASCADE,
  codigo_externo TEXT NOT NULL,
  marca_externa TEXT,
  tipo TEXT NOT NULL DEFAULT 'oem',
  confianza NUMERIC(3,2) DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS idx_equivalencia_codigo ON equivalencia(codigo_externo);

-- Reglas de precio (qué oferta priorizar)
CREATE TABLE IF NOT EXISTS regla_precio (
  id BIGSERIAL PRIMARY KEY,
  empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  ambito TEXT NOT NULL,
  ambito_valor TEXT,
  estrategia TEXT NOT NULL DEFAULT 'menor_precio',
  fuente_preferida_id BIGINT REFERENCES fuente_catalogo(id),
  requiere_stock BOOLEAN NOT NULL DEFAULT true,
  prioridad INT NOT NULL DEFAULT 0,
  activa BOOLEAN NOT NULL DEFAULT true,
  creado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
