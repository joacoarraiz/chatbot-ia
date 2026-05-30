# Guía: setup de Supabase desde cero

15 minutos. Si te pasan los 30, algo está raro — avisame.

## 1. Crear cuenta

1. Ir a https://supabase.com → "Start your project" → "Sign in with GitHub" (lo más simple).
2. Confirmar el email si te lo pide.

## 2. Crear el proyecto

1. Dashboard → "New project".
2. Llenar:
   - **Name**: `toni-prod` (o `toni-dev` si querés tener dos: uno para desarrollo y otro para producción).
   - **Database Password**: generá una larga y guardala en un password manager. Si la perdés tenés que resetearla.
   - **Region**: **South America (São Paulo)**. Es la más cerca de Argentina y baja la latencia.
   - **Pricing Plan**: Free.
3. "Create new project". Tarda 1-2 minutos en aprovisionar.

## 3. Anotar las credenciales

Una vez creado, en el panel del proyecto:

1. Sidebar izquierdo → **Settings** (engranaje) → **API**.
2. Copiar y pegar en tu archivo `.env`:
   - **Project URL** → `SUPABASE_URL`
   - **anon public** → `SUPABASE_ANON_KEY`
   - **service_role secret** → `SUPABASE_SERVICE_ROLE_KEY` ⚠️ Es la clave de admin. **NUNCA** la pongas en el frontend, solo en el backend.

## 4. Correr los SQL en orden

1. Sidebar → ícono `</>` (SQL Editor).
2. Click "+ New query".
3. Pegar el contenido completo de `db/01_catalog.sql` → click "Run" (o Ctrl+Enter).
4. Repetir con cada archivo en orden:
   - `db/01_catalog.sql`
   - `db/02_clients.sql`
   - `db/03_conversations.sql`
   - `db/04_orders_scoring.sql`
   - `db/05_rls.sql`
   - `functions/_rpcs/catalog_rpcs.sql`

Cada uno debería decir "Success. No rows returned." Si alguno tira error, parar y mostrármelo.

## 5. Verificar que se crearon las tablas

1. Sidebar → **Table Editor**.
2. Deberías ver al menos estas 17 tablas:
   - `empresa`, `fuente_catalogo`, `producto_logico`, `oferta`, `aplicacion`, `equivalencia`, `regla_precio`
   - `cliente`, `contact_channel`, `vehiculo_cliente`
   - `conversacion`, `mensaje`, `consulta`, `intencion_log`
   - `pedido`, `pedido_item`, `derivacion`, `score_consulta`

## 6. Crear la primera empresa (piloto)

Volvé a SQL Editor:

```sql
INSERT INTO empresa (
  nombre,
  plan,
  consultas_limite,
  persona_config,
  zona_horaria
) VALUES (
  'Repuestos Piloto',  -- ← reemplazá por el nombre real cuando lo tengas
  'basico',
  1500,
  '{
    "tono": "argentino_cercano",
    "permite_alternativas": true,
    "horario_atencion": {"lun":"9-18","mar":"9-18","mie":"9-18","jue":"9-18","vie":"9-18","sab":"9-13"},
    "metodos_pago": ["efectivo","transferencia","mercadopago"],
    "metodos_entrega": ["retira","envio"]
  }',
  'America/Argentina/Buenos_Aires'
) RETURNING id;
```

Anotá el `id` que devuelve (probablemente `1`). Ese va a ser el `empresa_id` que usás en todas las pruebas.

## 7. Configurar el bucket de archivos

Para guardar audios e imágenes que mande el cliente:

1. Sidebar → **Storage** → "New bucket".
2. Nombre: `media`.
3. Public: **NO** (que quede privado).
4. "Create bucket".

Listo. El backend va a usar el `service_role_key` para subir y leer archivos de acá.

## 8. Backups

En el plan Free Supabase hace backup automático **diario** y los retiene **7 días**. Para verificar:

1. Sidebar → Settings → Database → Backups.

Cuando pasemos a un plan pago vamos a tener backups más frecuentes (PITR — Point In Time Recovery). Por ahora alcanza.

## 9. Verificar que funciona

Volvé a SQL Editor y probá:

```sql
SELECT count(*) FROM empresa;
-- Debería devolver 1
```

```sql
SELECT * FROM rpc_consultar_precio(1, 1);
-- Va a devolver vacío porque no hay productos cargados, pero NO debe tirar error.
-- Si tira "function does not exist" → te faltó correr functions/_rpcs/catalog_rpcs.sql.
```

## 10. Habilitar conexión desde tu máquina (opcional, recomendado)

Si querés conectarte desde un cliente SQL (TablePlus, DBeaver, psql):

1. Settings → Database → Connection string. Copiá la URI.
2. Pegar en tu cliente. La password es la que pusiste al crear el proyecto.

---

## Costos esperados

Con el plan **Free** de Supabase tenés:
- 500 MB de base.
- 1 GB de Storage.
- 5 GB de transferencia/mes.
- 50 MAU de auth.

Es más que suficiente para 5-10 comercios piloto durante 2-3 meses. Cuando se queda corto, el plan **Pro** son USD 25/mes y multiplica todo por 16. No es el cuello de botella del proyecto.

---

## Si rompiste algo

Para empezar de cero **sin** borrar el proyecto:

```sql
-- ⚠️ ESTO BORRA TODO. Solo si estás seguro.
DROP TABLE IF EXISTS score_consulta, derivacion, pedido_item, pedido,
  intencion_log, mensaje, consulta, conversacion,
  vehiculo_cliente, contact_channel, cliente,
  regla_precio, equivalencia, aplicacion, oferta,
  producto_logico, fuente_catalogo, empresa CASCADE;

DROP FUNCTION IF EXISTS fn_get_or_create_cliente, fn_un_default_por_cliente,
  fn_cerrar_consultas_inactivas, rpc_buscar_producto,
  rpc_buscar_por_aplicacion, rpc_buscar_equivalencia,
  rpc_consultar_precio CASCADE;
```

Y volvés a correr los SQL desde el 01.
