"""Configuración de las pruebas (HU-01 a HU-10).

Usan una base de datos SEPARADA (TEST_DATABASE_URL) que se borra y recrea.
Por seguridad, las pruebas se niegan a correr si esa base es la misma de
DATABASE_URL o si su nombre no contiene "test" o "prueba".
"""
import os
import re
import secrets
from datetime import timedelta
from urllib.parse import urlparse

import pytest
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from app import create_app
from app.cifrado import hash_contrasena
from app.config import CARPETA_PROYECTO
from app.db import aplicar_migraciones, conectar
from app.formato import hoy

load_dotenv(CARPETA_PROYECTO / ".env", override=False)
URL_PRUEBAS = os.getenv("TEST_DATABASE_URL", "")

TABLAS = "estancias, huespedes, usuarios, despliegues"
USUARIO_PRUEBA = "recepcion"
CLAVE_PRUEBA = "ClaveSegura123!"


def _base_segura(url):
    nombre = urlparse(url).path.lstrip("/").lower()
    return url and url != os.getenv("DATABASE_URL") and ("test" in nombre or "prueba" in nombre)


@pytest.fixture(scope="session")
def url_pruebas():
    if not URL_PRUEBAS or URL_PRUEBAS.upper().find("CAMBIAR") >= 0:
        pytest.skip("Define TEST_DATABASE_URL en .env para correr las pruebas.")
    if not _base_segura(URL_PRUEBAS):
        pytest.exit("TEST_DATABASE_URL debe ser una base distinta de DATABASE_URL y su nombre debe "
                    "contener 'test' o 'prueba'. No se tocó ninguna base.", returncode=2)
    with conectar(URL_PRUEBAS) as conexion:
        conexion.execute("DROP SCHEMA public CASCADE")
        conexion.execute("CREATE SCHEMA public")
        aplicar_migraciones(conexion)
    return URL_PRUEBAS


@pytest.fixture(scope="session")
def claves():
    return {
        "SECRET_KEY": secrets.token_urlsafe(48),
        "FERNET_KEY": Fernet.generate_key().decode(),
        "HMAC_KEY": secrets.token_urlsafe(48),
    }


@pytest.fixture
def app(url_pruebas, claves):
    aplicacion = create_app({"TESTING": True, "DATABASE_URL": url_pruebas, **claves})
    with conectar(url_pruebas) as conexion:
        conexion.execute(f"TRUNCATE {TABLAS} RESTART IDENTITY CASCADE")
        conexion.execute(
            """INSERT INTO usuarios (usuario, nombre_completo, rol, password_hash)
               VALUES (%s, %s, 'admin', %s)""",
            (USUARIO_PRUEBA, "Personal de Prueba", hash_contrasena(CLAVE_PRUEBA)),
        )
    yield aplicacion


@pytest.fixture
def bd(url_pruebas):
    """Conexión directa para revisar lo que quedó guardado."""
    with conectar(url_pruebas) as conexion:
        yield conexion


def token_csrf(html):
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert m, "La página no tiene token CSRF"
    return m.group(1)


class Cliente:
    """Cliente de pruebas que se comporta como el navegador: gestiona sesión y CSRF."""

    def __init__(self, app):
        self.c = app.test_client()

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def token(self, ruta="/login"):
        r = self.c.get(ruta)
        if r.status_code == 302:
            r = self.c.get("/registro")
        return token_csrf(r.get_data(as_text=True))

    def iniciar_sesion(self, usuario=USUARIO_PRUEBA, contrasena=CLAVE_PRUEBA, **kw):
        t = self.token("/login")
        return self.c.post(
            "/login",
            data={"csrf_token": t, "usuario": usuario, "contrasena": contrasena},
            **kw,
        )

    def cerrar_sesion(self, **kw):
        return self.post("/logout", **kw)

    def post(self, url, data=None, prefijo=None, csrf=True, **kw):
        datos = dict(data or {})
        if csrf:
            datos.setdefault("csrf_token", self.token())
        if prefijo:
            datos = {f"{prefijo}-{k}": v for k, v in datos.items()}
        return self.c.post(url, data=datos, **kw)

    def post_json(self, url, datos, con_token=True):
        cabeceras = {"X-CSRFToken": self.token()} if con_token else {}
        return self.c.post(url, json=datos, headers=cabeceras)


@pytest.fixture
def cliente_anonimo(app):
    """Cliente sin sesión iniciada (para probar bloqueo de acceso en HU-07)."""
    return Cliente(app)


@pytest.fixture
def cliente(app):
    """Cliente autenticado listo para probar las vistas del panel de recepción."""
    c = Cliente(app)
    r = c.iniciar_sesion()
    assert r.status_code == 302, f"No se pudo autenticar el cliente de prueba: {r.status_code}"
    return c


def datos_registro(**cambios):
    """Datos válidos de un registro en el mostrador (se pueden cambiar en cada prueba)."""
    datos = {
        "tipo_documento": "CC", "numero_documento": "1036555210",
        "nombres": "José", "apellidos": "Peña Ruiz", "nacionalidad": "Colombia",
        "telefono": "+57 300 123 4567", "correo": "jose@ejemplo.com", "acepta_datos": "y",
        "estado_llegada": "en_casa",
        "habitacion": "101", "canal": "Booking",
        "fecha_ingreso": hoy().isoformat(), "fecha_salida_prevista": (hoy() + timedelta(days=2)).isoformat(),
        "procedencia": "Bogotá", "destino": "Salento",
    }
    datos.update(cambios)
    return {k: v for k, v in datos.items() if v is not None}
