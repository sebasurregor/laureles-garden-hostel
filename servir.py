"""Sirve la aplicación con waitress (servidor apto para Windows).

    py servir.py            -> http://127.0.0.1:8000 (o HOST/PUERTO desde .env)

Con HU-07 todas las vistas del panel requieren inicio de sesión.
Para producción en Linux/nube con HTTPS usa Gunicorn (wsgi.py + gunicorn.conf.py).
No uses `flask run --debug` en el hostal.
"""
import os

from waitress import serve

from app import create_app

if __name__ == "__main__":
    aplicacion = create_app()
    host = os.getenv("HOST", "127.0.0.1")
    puerto = int(os.getenv("PUERTO", os.getenv("PORT", "8000")))
    hilos = int(os.getenv("HILOS", "16"))
    version = aplicacion.config["APP_VERSION"]
    print(
        f"Laureles Garden v{version} · recepción disponible en http://{host}:{puerto} "
        f"(hilos={hilos}, Ctrl+C para detener)"
    )
    serve(aplicacion, host=host, port=puerto, threads=hilos)
