"""Aplicación web de recepción · Laureles Garden Hostel (Entrega 3: HU-01 a HU-10).

Se crea con el patrón "application factory": create_app() arma la app,
registra los módulos (blueprints) y aplica la configuración de seguridad y rendimiento.
Uso: flask --app app <comando>   |   py servir.py   |   gunicorn -c gunicorn.conf.py wsgi:app
"""
import logging
import sys
import time
import traceback

import psycopg
from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db
from .config import ConfiguracionInvalida, cargar_configuracion

csrf = CSRFProtect()

DIRECCIONES_LOCALES = {"127.0.0.1", "::1"}

ENDPOINTS_PUBLICOS = {
    "auth.login",
    "estancias.health",
    "huespedes.politica_datos",
    "static",
}

CABECERAS_SEGURIDAD = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def create_app(configuracion=None):
    app = Flask(__name__)
    try:
        app.config.update(cargar_configuracion(configuracion))
    except ConfiguracionInvalida as error:
        if configuracion and configuracion.get("TESTING"):
            raise
        print(f"\n[Laureles Garden] La aplicación no puede iniciar:\n  {error}\n", file=sys.stderr)
        raise SystemExit(1)

    if app.config.get("CONFIAR_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    _configurar_logs(app)
    db.init_app(app)
    csrf.init_app(app)

    from .blueprints import auth, estancias, huespedes

    for modulo in (auth, huespedes, estancias):
        app.register_blueprint(modulo.bp)

    from . import cli, formato

    cli.init_app(app)
    formato.init_app(app)
    _registrar_controles(app)
    _registrar_errores(app)

    if app.debug and not app.testing:
        app.logger.warning("ATENCIÓN: FLASK_DEBUG está activo. No lo uses en el hostal.")
    return app


def _configurar_logs(app):
    manejador = logging.StreamHandler()
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    app.logger.handlers = [manejador]
    app.logger.setLevel(logging.INFO)


def _registrar_controles(app):
    @app.before_request
    def iniciar_cronometro():
        g.inicio_peticion = time.perf_counter()

    @app.before_request
    def verificar_entorno_y_sesion():
        g.usuario = None

        if app.config.get("SOLO_LOCAL") and request.remote_addr not in DIRECCIONES_LOCALES:
            app.logger.warning("Petición rechazada desde otra dirección: %s", request.remote_addr)
            abort(403)

        if (
            app.config.get("FORZAR_HTTPS")
            and not app.testing
            and not request.is_secure
            and request.endpoint != "estancias.health"
        ):
            url_segura = request.url.replace("http://", "https://", 1)
            return redirect(url_segura, code=301)

        usuario_id = session.get("usuario_id")
        if usuario_id is not None:
            usuario = db.consultar_uno(
                "SELECT id, usuario, nombre_completo, rol, activo FROM usuarios WHERE id = %s",
                (usuario_id,),
            )
            if usuario and usuario["activo"]:
                g.usuario = usuario
            else:
                session.clear()

        if request.endpoint in ENDPOINTS_PUBLICOS or request.endpoint is None:
            return None

        if g.usuario is None:
            es_json = request.is_json or request.path.startswith("/huespedes/verificar-documento")
            if es_json:
                return jsonify(error="Debes iniciar sesión para realizar esta acción."), 401
            destino = request.full_path.rstrip("?")
            return redirect(url_for("auth.login", siguiente=destino))

        return None

    @app.after_request
    def agregar_cabeceras(respuesta):
        for nombre, valor in CABECERAS_SEGURIDAD.items():
            respuesta.headers.setdefault(nombre, valor)

        if app.config.get("FORZAR_HTTPS") and not app.testing:
            respuesta.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        if request.endpoint == "static":
            respuesta.headers["Cache-Control"] = "public, max-age=86400"
        else:
            respuesta.headers["Cache-Control"] = "no-store"

        inicio = getattr(g, "inicio_peticion", None)
        if inicio is not None:
            duracion_ms = (time.perf_counter() - inicio) * 1000.0
            respuesta.headers["Server-Timing"] = f"app;dur={duracion_ms:.2f}"
        return respuesta


def _registrar_errores(app):
    def pagina(codigo, titulo, mensaje):
        return render_template("error.html", codigo=codigo, titulo=titulo, mensaje=mensaje), codigo

    @app.errorhandler(400)
    def solicitud_invalida(_e):
        return pagina(400, "Solicitud no válida", "Revisa los datos e inténtalo de nuevo.")

    @app.errorhandler(CSRFError)
    def error_csrf(_e):
        app.logger.warning("Formulario rechazado por CSRF en %s", request.path)
        return pagina(400, "El formulario expiró",
                      "Por seguridad, recarga la página y vuelve a enviar el formulario.")

    @app.errorhandler(403)
    def prohibido(_e):
        return pagina(403, "Acceso no permitido",
                      "No tienes autorización para acceder a este recurso.")

    @app.errorhandler(404)
    def no_encontrado(_e):
        return pagina(404, "Página no encontrada", "La dirección no existe o el registro fue retirado.")

    @app.errorhandler(psycopg.OperationalError)
    def sin_base_de_datos(error):
        app.logger.error("Sin conexión con PostgreSQL (%s)", type(error).__name__)
        return pagina(503, "Sin conexión con la base de datos",
                      "No fue posible conectar con PostgreSQL. Avisa a quien administra el sistema "
                      "(ver la sección 'Errores comunes' del README).")

    @app.errorhandler(Exception)
    def error_inesperado(error):
        if isinstance(error, HTTPException):
            return error
        pila = "".join(traceback.format_tb(error.__traceback__))
        app.logger.error("Error inesperado en %s: %s\n%s", request.path, type(error).__name__, pila)
        return pagina(500, "Algo salió mal", "No se pudo completar la acción. Inténtalo de nuevo; "
                      "si se repite, avisa a la gerencia.")
