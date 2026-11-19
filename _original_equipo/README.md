# Registro de huéspedes - PostgreSQL

## Ejecutar en Windows (PowerShell)
1. Tener Python y PostgreSQL disponibles, con la tabla `Usuario_hostal` ya creada.
2. Abrir una terminal en esta carpeta.
3. Ejecutar `py -m pip install -r requirements.txt`.
4. Copiar `.env.example` a `.env` y reemplazar usuario, contraseña, puerto y nombre de la base de datos. Si la contraseña tiene caracteres especiales como `@`, codificarlos para URL.
5. Ejecutar `py app.py`.
6. Abrir `http://127.0.0.1:5000` (no abrir el HTML como archivo local).

El servidor recibe POST `/api/huespedes` y guarda los datos con SQL parametrizado. No crea ni altera tablas. El campo `fecha_Checkout` es opcional. El índice UNIQUE de tipo/número de documento impedirá duplicados. Si se ejecuta desde otra máquina, habrá que configurar el despliegue y seguridad; el servidor de desarrollo no debe exponerse a Internet.
