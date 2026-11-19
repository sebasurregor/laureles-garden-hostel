# Laureles Garden Hostel · Aplicación de recepción (Entrega 3 · v2.0.0)

Aplicación web para el **personal de recepción** de Laureles Garden Hostel (Laureles, Medellín). Reemplaza el libro
físico de registro y cubre el flujo completo de las entregas del curso de Sistemas de Información (**HU-01 a HU-10**).

**Stack:** Python 3.11+ · Flask 3 · PostgreSQL 14+ · `psycopg` 3 + `psycopg-pool` · Jinja2 · `Flask-WTF` · `cryptography` · Waitress (Windows) / Gunicorn (Linux/nube) · `pytest`.

## Historias de usuario implementadas

| HU | Funcionalidad | Ruta / Artefacto principal |
|---|---|---|
| HU-01 / HU-02 | Registro de huéspedes y almacenamiento cifrado atómico | `/registro`, `app/cifrado.py` |
| HU-03 / HU-04 | Huéspedes en casa, salida e historial de estancias | `/en-casa`, `/historial`, `/huespedes/<id>` |
| **HU-05** | Búsqueda de huéspedes por nombre o documento | `/buscar`, `app/blueprints/huespedes.py` |
| **HU-06** | Confirmación de llegada y modificación por error | `/llegadas`, `/estancias/<id>/confirmar-llegada`, `/marcar-pendiente` |
| **HU-07** | Acceso autorizado con usuario, contraseña y cierre de sesión | `/login`, `/logout`, `app/blueprints/auth.py`, `crear-usuario` |
| **HU-09** | Despliegue controlado con HTTPS, rollback y registro de versión | `render.yaml`, `wsgi.py`, `/health`, `smoke_test.py`, `registrar-despliegue` |
| **HU-10** | Optimización de rendimiento y pruebas comparativas | `003_indices_rendimiento.sql`, `psycopg_pool`, `benchmark_rendimiento.py` |

> Consulta la guía completa paso a paso (conexión a PostgreSQL local y nube, GitHub, despliegue HTTPS, rollback y benchmark) en **[docs/GUIA_ENTREGA3_BD_DESPLIEGUE_GITHUB.md](docs/GUIA_ENTREGA3_BD_DESPLIEGUE_GITHUB.md)**.

---

## Arranque rápido en Windows (PowerShell)

```powershell
# 1. Crear y activar el entorno virtual
py -m venv .venv
.venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar .env y generar claves criptográficas
Copy-Item .env.example .env
notepad .env                       # Ajusta DATABASE_URL y TEST_DATABASE_URL
py scripts\generar_claves.py

# 4. Aplicar migraciones (crea tablas 001, 002 e índices 003 sin borrar datos)
flask --app app init-db

# 5. Crear el primer usuario autorizado (HU-07)
flask --app app crear-usuario --usuario admin --nombre "Administrador" --rol admin

# 6. (Opcional) Cargar datos demo (incluye huéspedes en casa y pendientes de llegada)
flask --app app seed-demo

# 7. Iniciar la aplicación
py servir.py
# Abrir http://127.0.0.1:8000 e iniciar sesión
```

## Comandos principales

| Comando | Propósito |
|---|---|
| `flask --app app init-db` | Aplica migraciones pendientes (`001`, `002`, `003`) sin borrar datos |
| `flask --app app crear-usuario` | Crea un usuario autorizado (`admin` o `recepcion`) |
| `flask --app app listar-usuarios` | Lista los usuarios registrados |
| `flask --app app desactivar-usuario --usuario X` | Revoca acceso a un usuario sin perder historial |
| `flask --app app registrar-despliegue --version 2.0.0 --resultado exitoso` | Registra versión publicada y resultado (HU-09) |
| `flask --app app historial-despliegues` | Consulta el historial de entregas |
| `py -m pytest -v` | Ejecuta toda la suite automatizada (requiere `TEST_DATABASE_URL`) |
| `py scripts\benchmark_rendimiento.py` | Ejecuta comparativa de rendimiento antes/después (HU-10) |
| `py scripts\smoke_test.py --url https://... --usuario admin --password ...` | Valida el despliegue en producción (HU-09) |
| `.\scripts\backup.ps1` | Respaldo comprimido `.dump` de PostgreSQL |
| `.\scripts\desplegar.ps1` / `.\scripts\rollback.ps1` | Despliegue y reversión controlada en Windows |
