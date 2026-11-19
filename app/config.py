"""Carga y valida la configuración desde el archivo .env o variables de entorno.

Regla de oro: los secretos (claves y contraseña de la base de datos) solo
viven en .env o en las variables del servidor de despliegue. Nunca se escriben
en el código ni se imprimen en consola.
"""
import os
from datetime import timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

CARPETA_PROYECTO = Path(__file__).resolve().parent.parent

CLAVES_OBLIGATORIAS = ("SECRET_KEY", "FERNET_KEY", "HMAC_KEY", "DATABASE_URL")


class ConfiguracionInvalida(RuntimeError):
    """Falta una clave o tiene un formato inválido."""


def _es_valor_de_ejemplo(valor):
    return not valor or valor.strip().upper().startswith("CAMBIAR")


def _como_booleano(valor, por_defecto=False):
    if valor is None:
        return por_defecto
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("1", "true", "si", "sí", "yes", "on")


def _como_entero(valor, por_defecto, minimo=1):
    try:
        return max(int(valor), minimo)
    except (TypeError, ValueError):
        return por_defecto


def cargar_configuracion(sobrescribir=None):
    """Devuelve un diccionario de configuración listo para Flask."""
    load_dotenv(CARPETA_PROYECTO / ".env", override=False)
    sobrescribir = sobrescribir or {}

    def leer(nombre, por_defecto=None):
        if nombre in sobrescribir:
            return sobrescribir[nombre]
        return os.getenv(nombre, por_defecto)

    config = {nombre: leer(nombre) for nombre in CLAVES_OBLIGATORIAS}

    faltantes = [n for n in CLAVES_OBLIGATORIAS if _es_valor_de_ejemplo(config[n])]
    if faltantes:
        raise ConfiguracionInvalida(
            "Faltan claves en el archivo .env: " + ", ".join(faltantes) + ". "
            "Copia .env.example a .env, ajusta DATABASE_URL y ejecuta "
            "'py scripts\\generar_claves.py' para crear las claves."
        )
    try:
        Fernet(config["FERNET_KEY"])
    except (ValueError, TypeError):
        raise ConfiguracionInvalida(
            "FERNET_KEY no tiene un formato válido. Genérala con "
            "'py scripts\\generar_claves.py'."
        ) from None
    if len(config["HMAC_KEY"]) < 32 or len(config["SECRET_KEY"]) < 32:
        raise ConfiguracionInvalida(
            "SECRET_KEY y HMAC_KEY deben tener al menos 32 caracteres. "
            "Genéralas con 'py scripts\\generar_claves.py'."
        )

    es_prueba = _como_booleano(sobrescribir.get("TESTING"), False)
    forzar_https = _como_booleano(leer("FORZAR_HTTPS", "0"), False)
    confiar_proxy = _como_booleano(leer("CONFIAR_PROXY", "0"), False)
    solo_local = _como_booleano(leer("SOLO_LOCAL", "0"), False)

    pool_por_defecto = False if es_prueba else True
    usar_pool = _como_booleano(
        sobrescribir.get("USAR_POOL_CONEXIONES")
        if "USAR_POOL_CONEXIONES" in sobrescribir
        else (None if es_prueba else os.getenv("USAR_POOL_CONEXIONES", "1")),
        pool_por_defecto,
    )
    pool_min = _como_entero(leer("DB_POOL_MIN", 2), 2, minimo=1)
    pool_max = max(_como_entero(leer("DB_POOL_MAX", 10), 10, minimo=1), pool_min)

    config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=forzar_https and not es_prueba,
        SESSION_COOKIE_NAME="lg_sesion",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        WTF_CSRF_HEADERS=["X-CSRFToken"],
        WTF_I18N_ENABLED=False,
        NOMBRE_HOSTAL=leer("NOMBRE_HOSTAL", "Laureles Garden Hostel"),
        APP_VERSION=leer("APP_VERSION", "2.0.0"),
        ENTORNO=leer("ENTORNO", "desarrollo"),
        ZONA_HORARIA="America/Bogota",
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
        FORZAR_HTTPS=forzar_https,
        CONFIAR_PROXY=confiar_proxy,
        SOLO_LOCAL=solo_local,
        USAR_POOL_CONEXIONES=usar_pool,
        DB_POOL_MIN=pool_min,
        DB_POOL_MAX=pool_max,
    )
    for clave, valor in sobrescribir.items():
        if clave not in ("FORZAR_HTTPS", "CONFIAR_PROXY", "SOLO_LOCAL", "USAR_POOL_CONEXIONES"):
            config[clave] = valor
    return config
