-- =====================================================
-- catalog_rpcs.sql
-- Funciones Postgres que sirven como backend de las tools
-- del bot Toni. YA ESTÁN CARGADAS EN SUPABASE.
-- Este archivo queda en el repo como referencia.
-- =====================================================

CREATE OR REPLACE FUNCTION rpc_buscar_producto(
  p_empresa_id BIGINT,
  p_query TEXT,
  p_marca_pieza TEXT DEFAULT NULL,
  p_linea TEXT DEFAULT NULL,
  p_limit INT DEFAULT 5
)
RETURNS TABLE (
  producto_id BIGINT,
  descripcion TEXT,
  marca_pieza TEXT,
  linea TEXT,
  stock_total BIGINT,
  precio_min NUMERIC,
  match_score REAL
)
LANGUAGE sql STABLE AS $$
  SELECT p.id, p.descripcion, p.marca_pieza, p.linea,
         COALESCE(SUM(o.stock), 0),
         MIN(o.precio) FILTER (WHERE o.stock > 0),
         ts_rank(to_tsvector('spanish', p.descripcion),
                 plainto_tsquery('spanish', p_query))
    FROM producto_logico p
    LEFT JOIN oferta o ON o.producto_id = p.id
   WHERE p.empresa_id = p_empresa_id
     AND to_tsvector('spanish', p.descripcion) @@ plainto_tsquery('spanish', p_query)
     AND (p_marca_pieza IS NULL OR p.marca_pieza ILIKE p_marca_pieza)
     AND (p_linea IS NULL OR p.linea ILIKE p_linea)
   GROUP BY p.id
   ORDER BY 7 DESC, 5 DESC
   LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION rpc_buscar_por_aplicacion(
  p_empresa_id BIGINT,
  p_marca TEXT,
  p_modelo TEXT,
  p_anio INT,
  p_motor TEXT DEFAULT NULL,
  p_posicion TEXT DEFAULT NULL,
  p_linea TEXT DEFAULT NULL,
  p_limit INT DEFAULT 5
)
RETURNS TABLE (
  producto_id BIGINT,
  descripcion TEXT,
  marca_pieza TEXT,
  linea TEXT,
  posicion TEXT,
  stock_total BIGINT,
  precio_min NUMERIC
)
LANGUAGE sql STABLE AS $$
  SELECT p.id, p.descripcion, p.marca_pieza, p.linea, a.posicion,
         COALESCE(SUM(o.stock), 0),
         MIN(o.precio) FILTER (WHERE o.stock > 0)
    FROM producto_logico p
    JOIN aplicacion a ON a.producto_id = p.id
    LEFT JOIN oferta o ON o.producto_id = p.id
   WHERE p.empresa_id = p_empresa_id
     AND a.auto_marca ILIKE p_marca
     AND a.modelo ILIKE p_modelo
     AND (a.anio_desde IS NULL OR a.anio_desde <= p_anio)
     AND (a.anio_hasta IS NULL OR a.anio_hasta >= p_anio)
     AND (p_motor IS NULL OR a.motor ILIKE '%' || p_motor || '%')
     AND (p_posicion IS NULL OR a.posicion ILIKE p_posicion)
     AND (p_linea IS NULL OR p.linea ILIKE p_linea)
   GROUP BY p.id, a.posicion
   ORDER BY 6 DESC, 7 ASC NULLS LAST
   LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION rpc_buscar_equivalencia(
  p_empresa_id BIGINT,
  p_codigo TEXT
)
RETURNS TABLE (
  producto_id BIGINT,
  descripcion TEXT,
  marca_pieza TEXT,
  tipo_equiv TEXT,
  marca_externa TEXT,
  confianza NUMERIC,
  stock_total BIGINT,
  precio_min NUMERIC
)
LANGUAGE sql STABLE AS $$
  SELECT p.id, p.descripcion, p.marca_pieza, e.tipo, e.marca_externa, e.confianza,
         COALESCE(SUM(o.stock), 0),
         MIN(o.precio) FILTER (WHERE o.stock > 0)
    FROM equivalencia e
    JOIN producto_logico p ON p.id = e.producto_id
    LEFT JOIN oferta o ON o.producto_id = p.id
   WHERE p.empresa_id = p_empresa_id
     AND e.codigo_externo ILIKE p_codigo
   GROUP BY p.id, e.tipo, e.marca_externa, e.confianza
   ORDER BY e.confianza DESC, 7 DESC;
$$;

CREATE OR REPLACE FUNCTION rpc_consultar_precio(
  p_empresa_id BIGINT,
  p_producto_id BIGINT
)
RETURNS TABLE (
  producto_id BIGINT,
  precio_final NUMERIC,
  oferta_id BIGINT,
  fuente_id BIGINT,
  regla_aplicada_id BIGINT,
  estrategia TEXT
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  v_marca TEXT; v_linea TEXT; v_regla RECORD; v_oferta RECORD;
BEGIN
  SELECT marca_pieza, linea INTO v_marca, v_linea
    FROM producto_logico WHERE id = p_producto_id;

  SELECT * INTO v_regla FROM regla_precio r
   WHERE r.empresa_id = p_empresa_id AND r.activa = true
     AND ((r.ambito='producto' AND r.ambito_valor=p_producto_id::TEXT)
       OR (r.ambito='marca' AND r.ambito_valor=v_marca)
       OR (r.ambito='linea' AND r.ambito_valor=v_linea)
       OR (r.ambito='global'))
   ORDER BY r.prioridad DESC LIMIT 1;

  IF v_regla IS NULL THEN
    SELECT o.id, o.precio, o.fuente_id INTO v_oferta
      FROM oferta o WHERE o.producto_id=p_producto_id AND o.stock>0
      ORDER BY o.precio ASC LIMIT 1;
    IF v_oferta IS NULL THEN RETURN; END IF;
    RETURN QUERY SELECT p_producto_id, v_oferta.precio, v_oferta.id,
                        v_oferta.fuente_id, NULL::BIGINT, 'sin_regla';
    RETURN;
  END IF;

  IF v_regla.estrategia='menor_precio' THEN
    SELECT o.id, o.precio, o.fuente_id INTO v_oferta FROM oferta o
     WHERE o.producto_id=p_producto_id AND (NOT v_regla.requiere_stock OR o.stock>0)
     ORDER BY o.precio ASC LIMIT 1;
  ELSIF v_regla.estrategia='mayor_margen' THEN
    SELECT o.id, o.precio, o.fuente_id INTO v_oferta FROM oferta o
     WHERE o.producto_id=p_producto_id AND (NOT v_regla.requiere_stock OR o.stock>0)
     ORDER BY (o.precio-COALESCE(o.costo,0)) DESC LIMIT 1;
  ELSIF v_regla.estrategia='lista_fija' AND v_regla.fuente_preferida_id IS NOT NULL THEN
    SELECT o.id, o.precio, o.fuente_id INTO v_oferta FROM oferta o
     WHERE o.producto_id=p_producto_id AND o.fuente_id=v_regla.fuente_preferida_id
       AND (NOT v_regla.requiere_stock OR o.stock>0) LIMIT 1;
  END IF;

  IF v_oferta IS NULL THEN
    SELECT o.id, o.precio, o.fuente_id INTO v_oferta FROM oferta o
     WHERE o.producto_id=p_producto_id AND o.stock>0
     ORDER BY o.precio ASC LIMIT 1;
  END IF;

  IF v_oferta IS NULL THEN RETURN; END IF;
  RETURN QUERY SELECT p_producto_id, v_oferta.precio, v_oferta.id,
                      v_oferta.fuente_id, v_regla.id, v_regla.estrategia;
END;
$$;
