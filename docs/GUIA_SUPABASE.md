# Guía rápida — Supabase

## Acceso al panel

Andá a https://supabase.com y entrá a tu proyecto "Toni chatbot".

## Cosas útiles desde el panel

- **Table Editor**: ver y editar filas a mano.
- **SQL Editor**: correr queries SQL.
- **Database → Functions**: ver las RPC creadas.
- **Storage**: el bucket `media` (audios e imágenes).
- **Project Settings → API**: las credenciales (URL, anon key, service_role key).

## RPC ya cargadas (ver functions/_rpcs/catalog_rpcs.sql)

- `rpc_buscar_producto(empresa_id, query, marca_pieza, linea, limit)`
- `rpc_buscar_por_aplicacion(empresa_id, marca, modelo, anio, motor, posicion, linea, limit)`
- `rpc_buscar_equivalencia(empresa_id, codigo)`
- `rpc_consultar_precio(empresa_id, producto_id)`

## Cómo verificar que la base está sana

```sql
-- Contar lo que hay en cada tabla
SELECT 'producto_logico' AS tabla, COUNT(*) FROM producto_logico
UNION ALL SELECT 'oferta', COUNT(*) FROM oferta
UNION ALL SELECT 'aplicacion', COUNT(*) FROM aplicacion
UNION ALL SELECT 'empresa', COUNT(*) FROM empresa;

-- Test de búsqueda
SELECT * FROM rpc_buscar_por_aplicacion(1, 'VW', 'Gol', 2010, NULL, NULL, NULL, 5);
```
