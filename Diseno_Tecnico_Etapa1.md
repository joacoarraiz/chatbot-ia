-- =====================================================
-- 05_rls.sql
-- Row Level Security: cada empresa solo ve sus propios datos.
-- Evita el bug clásico de multi-tenant donde un comercio
-- termina viendo datos de otro por un error en una query.
-- Correr ÚLTIMO, una vez que las tablas existen.
-- =====================================================

-- ----- Activar RLS en todas las tablas con empresa_id -----
ALTER TABLE empresa            ENABLE ROW LEVEL SECURITY;
ALTER TABLE fuente_catalogo    ENABLE ROW LEVEL SECURITY;
ALTER TABLE producto_logico    ENABLE ROW LEVEL SECURITY;
ALTER TABLE oferta             ENABLE ROW LEVEL SECURITY;
ALTER TABLE aplicacion         ENABLE ROW LEVEL SECURITY;
ALTER TABLE equivalencia       ENABLE ROW LEVEL SECURITY;
ALTER TABLE regla_precio       ENABLE ROW LEVEL SECURITY;
ALTER TABLE cliente            ENABLE ROW LEVEL SECURITY;
ALTER TABLE contact_channel    ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehiculo_cliente   ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversacion       ENABLE ROW LEVEL SECURITY;
ALTER TABLE mensaje            ENABLE ROW LEVEL SECURITY;
ALTER TABLE consulta           ENABLE ROW LEVEL SECURITY;
ALTER TABLE intencion_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE pedido             ENABLE ROW LEVEL SECURITY;
ALTER TABLE pedido_item        ENABLE ROW LEVEL SECURITY;
ALTER TABLE derivacion         ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_consulta     ENABLE ROW LEVEL SECURITY;

-- ----- Política: el rol "anon" (frontend público) NO ve nada -----
-- Solo el service_role del backend puede leer/escribir.
-- Cuando agreguemos auth y un panel para los comercios, ahí
-- crearemos políticas que filtran por empresa_id usando JWT.

-- ----- Patrón de política por empresa (para usar después con auth) -----
-- Cuando un usuario logueado consulte, el JWT incluirá su empresa_id
-- y la política filtrará automáticamente. Ejemplo para producto_logico:

-- CREATE POLICY tenant_isolation_productos ON producto_logico
--   FOR ALL
--   TO authenticated
--   USING (empresa_id = (auth.jwt() ->> 'empresa_id')::bigint);

-- Por ahora, mientras todo el acceso pasa por el backend con service_role,
-- las políticas pueden quedar como "deny all" desde anon:

CREATE POLICY deny_all_anon ON empresa FOR ALL TO anon USING (false);
CREATE POLICY deny_all_anon ON producto_logico FOR ALL TO anon USING (false);
CREATE POLICY deny_all_anon ON cliente FOR ALL TO anon USING (false);
CREATE POLICY deny_all_anon ON conversacion FOR ALL TO anon USING (false);
CREATE POLICY deny_all_anon ON mensaje FOR ALL TO anon USING (false);
CREATE POLICY deny_all_anon ON consulta FOR ALL TO anon USING (false);
CREATE POLICY deny_all_anon ON pedido FOR ALL TO anon USING (false);
-- (las demás tablas heredan: con RLS activado y sin política, no se ve nada)

-- =====================================================
-- NOTA IMPORTANTE
-- =====================================================
-- El service_role de Supabase (el que va a usar el backend del bot)
-- BYPASSEA RLS por diseño. Eso está bien — el backend es quien
-- valida que el comercio X solo toque datos del comercio X.
--
-- Cuando hagamos el panel web para que cada comercio vea SU CRM,
-- vamos a usar JWT con empresa_id incluido, y las políticas
-- van a filtrar automáticamente. En ese momento descomentamos
-- y ajustamos las políticas de arriba.
-- =====================================================
