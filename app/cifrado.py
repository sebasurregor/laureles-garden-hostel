"""Protección de datos personales y credenciales del personal.

- CIFRAR (Fernet): documento, teléfono y correo. Se puede revertir con la
  clave FERNET_KEY, por eso sirve para mostrar el dato cuando se necesita.
- HASH con clave (HMAC-SHA256): huella del documento para BUSCAR sin
  descifrar toda la tabla (HU-01 y HU-05). No se puede revertir.
- HASH de contraseñas (Werkzeug scrypt/pbkdf2): para el personal autorizado
  del panel de recepción (HU-07).
"""
import hashlib
import hmac
import re
import unicodedata
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash


@lru_cache(maxsize=4)
def _fernet_por_clave(clave):
    """Reutiliza la instancia Fernet para evitar decodificar la clave en cada operación (HU-10)."""
    return Fernet(clave)


def _fernet():
    return _fernet_por_clave(current_app.config["FERNET_KEY"])


def cifrar(texto):
    if not texto:
        return None
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        current_app.logger.error("No se pudo descifrar un dato: revisa FERNET_KEY.")
        return "[no disponible]"


def normalizar_documento(numero):
    """'1.036.555-21 ' -> '103655521'. Así la huella no depende del formato."""
    return re.sub(r"[\s.\-]", "", numero or "").upper()


def huella_documento(numero):
    """HMAC-SHA256 del documento normalizado, con la clave HMAC_KEY."""
    clave = current_app.config["HMAC_KEY"].encode("utf-8")
    mensaje = normalizar_documento(numero).encode("utf-8")
    return hmac.new(clave, mensaje, hashlib.sha256).hexdigest()


def ultimos_digitos(numero, cantidad=4):
    return normalizar_documento(numero)[-cantidad:]


def enmascarar(ultimos):
    return f"•••• {ultimos}" if ultimos else "••••"


def texto_para_buscar(texto):
    """Minúsculas y sin tildes: 'José Peña' -> 'jose pena'."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return " ".join(sin_tildes.lower().split())


def hash_contrasena(contrasena):
    """Genera un hash seguro con sal aleatoria para contraseñas del personal (HU-07)."""
    return generate_password_hash(contrasena)


def verificar_contrasena(hash_guardado, contrasena):
    """Compara la contraseña ingresada en tiempo constante."""
    if not hash_guardado or not contrasena:
        return False
    return check_password_hash(hash_guardado, contrasena)
