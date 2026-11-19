"""Punto de entrada WSGI para despliegue en producción (Gunicorn / Render / Railway).

    gunicorn -c gunicorn.conf.py wsgi:app
"""
from app import create_app

app = create_app()
