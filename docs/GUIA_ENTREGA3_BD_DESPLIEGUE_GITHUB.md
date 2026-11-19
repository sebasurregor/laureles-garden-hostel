# Guía paso a paso · Base de datos, GitHub, Despliegue HTTPS y Benchmark (Entrega 3)

Esta guía resume todo el proceso operativo para dejar funcionando **Laureles Garden Hostel v2.0.0** desde cero en local, versionarlo correctamente en GitHub, desplegarlo en producción con HTTPS y generar las evidencias de rendimiento para la sustentación.

---

## Parte 1 · Conectar el proyecto a PostgreSQL (local)

### 1.1 Crear las bases de datos en pgAdmin
1. Abre **pgAdmin 4** y conéctate a tu servidor local de PostgreSQL (puerto por defecto `5432`).
2. Crea la base de datos principal: clic derecho en **Databases → Create → Database…**, nombre: `laureles_garden`.
3. Crea la base de datos exclusiva para pruebas automáticas y benchmark: nombre: `laureles_garden_test`.

### 1.2 Configurar `.env`
En PowerShell, dentro de la carpeta del proyecto:
```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```
Abre `.env` y ajusta las dos URLs con tu usuario y contraseña de PostgreSQL:
```ini
DATABASE_URL=postgresql://postgres:TU_CONTRASENA@localhost:5432/laureles_garden
TEST_DATABASE_URL=postgresql://postgres:TU_CONTRASENA@localhost:5432/laureles_garden_test
```
> **Nota:** si tu contraseña tiene caracteres especiales, codifícalos (`@` → `%40`, `#` → `%23`, `/` → `%2F`, `:` → `%3A`, `%` → `%25`).

Genera las claves criptográficas automáticamente sin mostrarlas en pantalla:
```powershell
py scripts\generar_claves.py
```

### 1.3 Aplicar migraciones, crear usuario y probar
```powershell
flask --app app init-db
flask --app app crear-usuario --usuario admin --nombre "Administrador" --rol admin
flask --app app seed-demo
py -m pytest -v
py servir.py
```
Abre `http://127.0.0.1:8000` e inicia sesión con `admin` y la contraseña que elegiste.

---

## Parte 2 · Subir el proyecto a GitHub de forma segura

> **Regla crítica:** nunca subas `.env`, `backups/` ni `.venv/` al repositorio. El archivo `.gitignore` ya los excluye.

### 2.1 Inicializar o verificar el repositorio local
```powershell
git status
# Si aún no está inicializado:
git init
git branch -M main
```

### 2.2 Verificar que ningún secreto se vaya a subir
```powershell
git status --ignored
```
Confirma que `.env` aparece bajo **Ignored files** (y nunca bajo *Changes to be committed*).

### 2.3 Crear commit, etiqueta de versión y subir a GitHub
1. Crea un repositorio vacío en GitHub (por ejemplo `laureles-garden-hostel`).
2. Conecta el remoto y sube la rama y la etiqueta `v2.0.0` (útil para rollback en HU-09):
```powershell
git add .
git commit -m "Entrega 3: HU-05 busqueda, HU-06 llegadas, HU-07 login, HU-09 despliegue, HU-10 optimizacion"
git remote add origin https://github.com/TU_USUARIO/laureles-garden-hostel.git
git push -u origin main

# Etiqueta de versión estable para trazabilidad y rollback (HU-09)
git tag -a v2.0.0 -m "Entrega 3 estable: HU-05, HU-06, HU-07, HU-09 y HU-10"
git push origin v2.0.0
```

Si ya tenías un repositorio con `origin` configurado y estás trabajando en una rama de entrega:
```powershell
git checkout -b entrega-3
git add .
git commit -m "Entrega 3: HU-05, HU-06, HU-07, HU-09 y HU-10"
git push -u origin entrega-3
```
Luego abre un **Pull Request** en GitHub hacia `main` y haz *Merge* una vez pasen las pruebas.

---

## Parte 3 · Despliegue controlado en producción con HTTPS (HU-09)

La opción más directa, gratuita y con **HTTPS automático + PostgreSQL gestionado + Rollback en un clic** es **Render** usando el archivo `render.yaml` incluido en la raíz del proyecto.

### 3.1 Desplegar con Render Blueprint
1. Inicia sesión en [dashboard.render.com](https://dashboard.render.com) con tu cuenta de GitHub.
2. Haz clic en **New → Blueprint** y selecciona tu repositorio `laureles-garden-hostel`.
3. Render leerá automáticamente `render.yaml`, que configura:
   - Base de datos PostgreSQL `laureles-garden-db`.
   - Servicio web Python con `gunicorn -c gunicorn.conf.py wsgi:app`.
   - `preDeployCommand: flask --app app init-db` (aplica migraciones sin borrar datos existentes).
   - `healthCheckPath: /health`.
   - Variables de seguridad (`FORZAR_HTTPS=1`, `CONFIAR_PROXY=1`, `FLASK_DEBUG=0`, `USAR_POOL_CONEXIONES=1`).
4. Cuando Render te pida el valor de **`FERNET_KEY`**, genera una clave válida en tu PC y pégala:
   ```powershell
   py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Guarda una copia segura de esa clave (sin ella no se descifran documentos/teléfonos).
5. Haz clic en **Apply** y espera a que termine el despliegue.

### 3.2 Crear usuario en producción y registrar el despliegue
Abre la pestaña **Shell** de tu servicio web en Render y ejecuta:
```bash
flask --app app crear-usuario --usuario admin --nombre "Administrador" --rol admin
flask --app app registrar-despliegue --version 2.0.0 --entorno produccion --resultado exitoso --notas "Entrega 3 publicada con HTTPS"
```

### 3.3 Ejecutar la verificación post-despliegue (Smoke Test)
Desde tu computador:
```powershell
py scripts\smoke_test.py --url https://TU-SERVICIO.onrender.com --usuario admin --password TU_CLAVE
```
Esto verifica automáticamente HTTPS, `/health`, bloqueo sin sesión, inicio de sesión, vistas críticas `< 2 s` y cierre de sesión.

### 3.4 Cómo hacer Rollback sin pérdida de datos
- **En Render:** entra al servicio → pestaña **Events / Deploys** → busca el despliegue estable anterior → clic en **Rollback to this deploy**. Como las migraciones (`002`, `003`) son aditivas y no destructivas, todos los huéspedes y estancias quedan intactos.
- **En local / servidor Windows:** usa `.\scripts\rollback.ps1 -TagAnterior v1.0.0` (y opcionalmente `-Respaldo backups\archivo.dump`).
- Registra siempre el evento con:
  ```bash
  flask --app app registrar-despliegue --version 1.0.0 --entorno produccion --resultado revertido --notas "Motivo del rollback"
  ```

---

## Parte 4 · Generar evidencia medible antes/después de rendimiento (HU-10)

Para demostrar el criterio 5 de HU-10 con datos reales sobre 3.000+ huéspedes y concurrencia simultánea:
```powershell
py scripts\benchmark_rendimiento.py --volumen 3000 --iteraciones 20 --hilos 8
```
El script:
1. Carga datos demo en `TEST_DATABASE_URL` (no toca tu base principal).
2. Mide tiempos de carga (promedio, p95, máximo) y concurrencia **SIN pool ni índices 003**.
3. Aplica `003_indices_rendimiento.sql` y activa `psycopg_pool`, y vuelve a medir las mismas consultas.
4. Guarda automáticamente la tabla comparativa en **`docs/reporte_rendimiento.md`**, lista para anexar a tu entrega o sustentar en clase.
