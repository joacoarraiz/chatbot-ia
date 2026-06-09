-- =====================================================
-- 05_rls.sql
-- Row Level Security: cada empresa solo ve sus datos.
-- =====================================================

ALTER TABLE empresa ENABLE ROW LEVEL SECURITY;
ALTER TABLE fuente_catalogo ENABLE ROW LEVEL SECURITY;
ALTER TABLE producto_logico ENABLE ROW LEVEL SECURITY;
ALTER TABLE oferta ENABLE ROW LEVEL SECURITY;
ALTER TABLE aplicacion ENABLE ROW LEVEL SECURITY;
ALTER TABLE equivalencia ENABLE ROW LEVEL SECURITY;
ALTER TABLE regla_precio ENABLE ROW LEVEL SECURITY;
ALTER TABLE cliente ENABLE ROW LEVEL SECURITY;
ALTER TABLE contact_channel ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehiculo_cliente ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversacion ENABLE ROW LEVEL SECURITY;
ALTER TABLE mensaje ENABLE ROW LEVEL SECURITY;
ALTER TABLE consulta ENABLE ROW LEVEL SECURITY;
ALTER TABLE intencion_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE pedido ENABLE ROW LEVEL SECURITY;
ALTER TABLE pedido_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE derivacion ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_consulta ENABLE ROW LEVEL SECURITY;

-- El service_role bypassa RLS automáticamente, así que el bot funciona.
-- Las policies específicas para usuarios del dashboard se definen después.
