"""Conexión a PostgreSQL con psycopg 3 y pool de conexiones (HU-10).

- En operación normal reutiliza conexiones mediante `psycopg_pool.ConnectionPool`
  para reducir la latencia por petición y soportar usuarios simultáneos.
- Si `USAR_POOL_CONEXIONES=0`, vuelve al modo de una conexión por petición
  (útil para pruebas unitarias y comparativas de rendimiento antes/después).
- autocommit=True: cada consulta suelta se confirma sola. Cuando varias
  escrituras deben guardarse juntas o no guardarse, se envuelven en
  `with transaccion():` (todo o nada).
- Todas las consultas usan parámetros (%s): nunca se concatenan textos en el SQL.
"""
import atexit
from contextlib import contextmanager
from pathlib import Path

import psycopg
from flask import current_app, g
from psycopg.rows import dict_row

try:
    from psycopg_pool import ConnectionPool
except ImportError:  # pragma: no cover
    ConnectionPool = None

CARPETA_MIGRACIONES = Path(__file__).resolve().parent.parent / "migrations"


def _kwargs_conexion():
    return {
        "autocommit": True,
        "row_factory": dict_row,
        "connect_timeout": 5,
        "options": "-c timezone=America/Bogota",
    }


def conectar(url):
    """Abre una conexión directa con la zona horaria de Colombia fijada en la sesión."""
    return psycopg.connect(url, **_kwargs_conexion())


def _obtener_pool():
    """Crea el pool de forma perezosa la primera vez que se necesita (no bloquea el arranque)."""
    if not current_app.config.get("USAR_POOL_CONEXIONES", True) or ConnectionPool is None:
        return None
    pool = current_app.extensions.get("db_pool")
    if pool is None:
        pool = ConnectionPool(
            conninfo=current_app.config["DATABASE_URL"],
            min_size=current_app.config.get("DB_POOL_MIN", 2),
            max_size=current_app.config.get("DB_POOL_MAX", 10),
            timeout=10,
            kwargs=_kwargs_conexion(),
            open=True,
            check=ConnectionPool.check_connection,
        )
        current_app.extensions["db_pool"] = pool
        atexit.register(_cerrar_pool_silencioso, pool)
    return pool


def _cerrar_pool_silencioso(pool):
    try:
        pool.close()
    except Exception:
        pass


def cerrar_pool(app):
    """Cierra el pool asociado a una instancia de la aplicación (útil en pruebas y benchmarks)."""
    pool = app.extensions.pop("db_pool", None)
    if pool is not None:
        _cerrar_pool_silencioso(pool)


def obtener_conexion():
    if "db" not in g:
        pool = _obtener_pool()
        if pool is not None:
            g.db = pool.getconn()
            g.db_pool = pool
        else:
            g.db = conectar(current_app.config["DATABASE_URL"])
            g.db_pool = None
    return g.db


def cerrar_conexion(_error=None):
    conexion = g.pop("db", None)
    pool = g.pop("db_pool", None)
    if conexion is None:
        return
    if pool is not None:
        try:
            pool.putconn(conexion)
        except Exception:
            try:
                conexion.close()
            except Exception:
                pass
    else:
        conexion.close()


def consultar(sql, parametros=()):
    """Devuelve todas las filas como diccionarios."""
    return obtener_conexion().execute(sql, parametros).fetchall()


def consultar_uno(sql, parametros=()):
    """Devuelve una fila (diccionario) o None."""
    return obtener_conexion().execute(sql, parametros).fetchone()


def ejecutar(sql, parametros=()):
    return obtener_conexion().execute(sql, parametros)


@contextmanager
def transaccion():
    """Bloque atómico: si algo falla dentro, PostgreSQL deshace todo."""
    with obtener_conexion().transaction():
        yield


def aplicar_migraciones(conexion):
    """Ejecuta, en orden, los archivos migrations/NNN_*.sql que falten.

    Devuelve la lista de archivos aplicados en esta ejecución.
    """
    conexion.execute(
        """CREATE TABLE IF NOT EXISTS migraciones_aplicadas (
               nombre      varchar(120) PRIMARY KEY,
               aplicada_en timestamptz NOT NULL DEFAULT now())"""
    )
    ya_aplicadas = {
        fila["nombre"]
        for fila in conexion.execute("SELECT nombre FROM migraciones_aplicadas").fetchall()
    }
    aplicadas = []
    for archivo in sorted(CARPETA_MIGRACIONES.glob("[0-9][0-9][0-9]_*.sql")):
        if archivo.name in ya_aplicadas:
            continue
        with conexion.transaction():
            conexion.execute(archivo.read_text(encoding="utf-8"))
            conexion.execute(
                "INSERT INTO migraciones_aplicadas (nombre) VALUES (%s)", (archivo.name,)
            )
        aplicadas.append(archivo.name)
    return aplicadas


def init_app(app):
    app.teardown_appcontext(cerrar_conexion)
