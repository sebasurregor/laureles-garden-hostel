# Registro de versiones (Changelog) · Laureles Garden Hostel

## [2.0.0] - Entrega 3 (HU-05, HU-06, HU-07, HU-09, HU-10)
### Agregado
- **HU-05 (Búsqueda de huéspedes):** Nueva vista `/buscar` para encontrar registros por nombre/apellidos (sin importar tildes o mayúsculas) o número de documento exacto mediante huella HMAC-SHA256, con mensaje claro cuando no hay coincidencias y acceso directo a la ficha completa.
- **HU-06 (Confirmación de llegada):** Nuevo estado `pendiente` ("Pendiente de llegada") en `estancias`, nueva vista `/llegadas`, selector de estado en `/registro`, confirmación de llegada (`POST /estancias/<id>/confirmar-llegada`) y reversión en caso de error (`POST /estancias/<id>/marcar-pendiente`).
- **HU-07 (Acceso autorizado):** Tabla `usuarios` con hashes seguros (`werkzeug.security`), inicio y cierre de sesión (`/login`, `/logout`), bloqueo global de rutas protegidas sin sesión válida y comandos CLI `crear-usuario`, `listar-usuarios` y `desactivar-usuario`.
- **HU-09 (Despliegue controlado):** Soporte WSGI con Gunicorn (`wsgi.py`, `gunicorn.conf.py`, `Procfile`, `render.yaml`), `ProxyFix` y `FORZAR_HTTPS=1` (HSTS + cookies `Secure`), endpoint `/health`, tabla `despliegues` + comandos CLI `registrar-despliegue` e `historial-despliegues`, script de verificación `scripts/smoke_test.py` y scripts de despliegue/reversión (`desplegar.ps1`, `rollback.ps1`, `backup.sh`).
- **HU-10 (Optimización de rendimiento):** Pool de conexiones PostgreSQL (`psycopg_pool`), caché en memoria de instancia Fernet (`lru_cache`), migración `003_indices_rendimiento.sql` (índices compuestos, parciales y `pg_trgm` para búsqueda por nombre), consultas optimizadas con proyección de columnas, caché HTTP para archivos estáticos, cabecera `Server-Timing` y script reproducible `scripts/benchmark_rendimiento.py`.

## [1.0.0] - Sprint 1 (HU-01 a HU-04)
- Registro de huéspedes y estancias con transacciones atómicas y cifrado Fernet/HMAC.
- Consulta de huéspedes en casa (`/en-casa`), registro de salida e historial (`/historial` y `/huespedes/<id>`).
- Migración de la tabla original `Usuario_hostal`, respaldo `backup.ps1` y 32 pruebas automatizadas.
