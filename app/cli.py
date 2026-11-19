"""Comandos de consola:

    flask --app app init-db               crea o actualiza el esquema (migrations/*.sql)
    flask --app app crear-usuario         crea un usuario autorizado del panel (HU-07)
    flask --app app listar-usuarios       lista el personal registrado (HU-07)
    flask --app app desactivar-usuario    desactiva un usuario sin borrar historial (HU-07)
    flask --app app registrar-despliegue  registra la versión y resultado del despliegue (HU-09)
    flask --app app historial-despliegues muestra el historial de versiones publicadas (HU-09)
    flask --app app migrar-original       copia los datos de Usuario_hostal del Sprint 1
    flask --app app seed-demo             carga datos de prueba marcados como DEMO
"""
import click
import psycopg
from flask import current_app
from flask.cli import with_appcontext

from .cifrado import hash_contrasena
from .db import aplicar_migraciones, conectar


def _conexion():
    try:
        return conectar(current_app.config["DATABASE_URL"])
    except psycopg.OperationalError as error:
        primera_linea = str(error).strip().splitlines()[-1] if str(error).strip() else ""
        raise click.ClickException(
            "No se pudo conectar a PostgreSQL. Revisa que el servicio esté encendido y los datos de "
            f"DATABASE_URL en .env (usuario, contraseña, puerto y nombre de la base).\nDetalle: {primera_linea}"
        ) from None


@click.command("init-db")
@with_appcontext
def init_db():
    """Crea las tablas nuevas e índices. No borra ni modifica datos existentes."""
    with _conexion() as conexion:
        _revisar_base_con_alcance_extra(conexion)
        aplicadas = aplicar_migraciones(conexion)
    if aplicadas:
        click.echo("Esquema actualizado. Migraciones aplicadas: " + ", ".join(aplicadas))
    else:
        click.echo("El esquema ya estaba al día. No se cambió nada.")


def _revisar_base_con_alcance_extra(conexion):
    """Si la base proviene de una rama con alcance extra, nunca borra tablas: avisa o detiene."""
    extra = conexion.execute(
        """SELECT string_agg(table_name, ', ' ORDER BY table_name) AS tablas
             FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('habitaciones', 'pagos', 'cargos_adicionales', 'auditoria')"""
    ).fetchone()["tablas"]
    adaptada = conexion.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'estancias' AND column_name = 'habitacion'"""
    ).fetchone()
    if extra and adaptada:
        click.echo(f"Aviso: esta base conserva tablas de funcionalidades retiradas ({extra}). "
                   "No se usan ni se modifican.")
    if extra and not adaptada:
        raise click.ClickException(
            f"Esta base tiene tablas de funcionalidades retiradas ({extra}). No se modificó nada. "
            "Antes de continuar hay que decidir con la gerencia qué hacer con esos datos; "
            "ver migrations/manual/adaptar_base_con_alcance_extra.sql y el README."
        )


@click.command("crear-usuario")
@with_appcontext
@click.option("--usuario", prompt="Nombre de usuario", help="Identificador corto, ej. admin o recepcion1.")
@click.option("--nombre", prompt="Nombre completo", help="Nombre visible en el panel.")
@click.option(
    "--rol",
    type=click.Choice(["admin", "recepcion"], case_sensitive=False),
    default="recepcion",
    show_default=True,
    help="Rol del usuario.",
)
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Contraseña de al menos 8 caracteres.",
)
def crear_usuario(usuario, nombre, rol, password):
    """Crea un usuario autorizado para iniciar sesión en el panel (HU-07)."""
    usuario_limpio = usuario.strip().lower()
    nombre_limpio = " ".join(nombre.split())
    rol_limpio = rol.lower()
    if not usuario_limpio or len(usuario_limpio) > 40:
        raise click.ClickException("El nombre de usuario debe tener entre 1 y 40 caracteres.")
    if not nombre_limpio or len(nombre_limpio) > 120:
        raise click.ClickException("El nombre completo debe tener entre 1 y 120 caracteres.")
    if len(password) < 8:
        raise click.ClickException("La contraseña debe tener al menos 8 caracteres.")

    with _conexion() as conexion:
        try:
            conexion.execute(
                """INSERT INTO usuarios (usuario, nombre_completo, rol, password_hash)
                   VALUES (%s, %s, %s, %s)""",
                (usuario_limpio, nombre_limpio, rol_limpio, hash_contrasena(password)),
            )
        except psycopg.errors.UniqueViolation:
            raise click.ClickException(f"Ya existe un usuario llamado '{usuario_limpio}'.") from None
    click.echo(f"Usuario autorizado creado: {usuario_limpio} ({rol_limpio}).")


@click.command("listar-usuarios")
@with_appcontext
def listar_usuarios():
    """Muestra los usuarios registrados en el sistema (sin contraseñas)."""
    with _conexion() as conexion:
        filas = conexion.execute(
            "SELECT usuario, nombre_completo, rol, activo, ultimo_acceso FROM usuarios ORDER BY id"
        ).fetchall()
    if not filas:
        click.echo("No hay usuarios registrados. Crea uno con: flask --app app crear-usuario")
        return
    for u in filas:
        estado = "activo" if u["activo"] else "inactivo"
        click.echo(f"- {u['usuario']} | {u['nombre_completo']} | rol={u['rol']} | {estado}")


@click.command("desactivar-usuario")
@with_appcontext
@click.option("--usuario", required=True, help="Usuario a desactivar.")
def desactivar_usuario(usuario):
    """Desactiva el acceso de un usuario sin eliminar registros históricos."""
    usuario_limpio = usuario.strip().lower()
    with _conexion() as conexion:
        res = conexion.execute(
            "UPDATE usuarios SET activo = false WHERE usuario = %s AND activo = true",
            (usuario_limpio,),
        )
    if res.rowcount == 0:
        raise click.ClickException(f"No se encontró un usuario activo llamado '{usuario_limpio}'.")
    click.echo(f"Usuario '{usuario_limpio}' desactivado.")


@click.command("registrar-despliegue")
@with_appcontext
@click.option("--version", "version_app", default=None, help="Versión publicada (por defecto APP_VERSION).")
@click.option("--entorno", default=None, help="Entorno (por defecto ENTORNO).")
@click.option(
    "--resultado",
    type=click.Choice(["exitoso", "fallido", "revertido"], case_sensitive=False),
    default="exitoso",
    show_default=True,
    help="Resultado de la verificación del despliegue.",
)
@click.option("--notas", default="", help="Notas breves de la entrega o reversión.")
@click.option("--por", "desplegado_por", default="equipo-tecnico", help="Responsable del despliegue.")
def registrar_despliegue(version_app, entorno, resultado, notas, desplegado_por):
    """Registra la versión publicada y el resultado del despliegue (HU-09)."""
    version_final = (version_app or current_app.config["APP_VERSION"]).strip()
    entorno_final = (entorno or current_app.config["ENTORNO"]).strip()
    with _conexion() as conexion:
        fila = conexion.execute(
            """INSERT INTO despliegues (version, entorno, resultado, notas, desplegado_por)
               VALUES (%s, %s, %s, %s, %s) RETURNING id, desplegado_en""",
            (version_final, entorno_final, resultado.lower(), notas.strip() or None, desplegado_por.strip()),
        ).fetchone()
    click.echo(
        f"Despliegue #{fila['id']} registrado: v{version_final} en {entorno_final} -> {resultado.lower()}."
    )


@click.command("historial-despliegues")
@with_appcontext
@click.option("--limite", default=10, show_default=True, help="Cantidad máxima de registros a mostrar.")
def historial_despliegues(limite):
    """Muestra el historial de versiones publicadas y su resultado (HU-09)."""
    with _conexion() as conexion:
        filas = conexion.execute(
            """SELECT id, version, entorno, resultado, notas, desplegado_por, desplegado_en
                 FROM despliegues
                ORDER BY desplegado_en DESC, id DESC
                LIMIT %s""",
            (max(limite, 1),),
        ).fetchall()
    if not filas:
        click.echo("Aún no hay despliegues registrados.")
        return
    for d in filas:
        notas = f" · {d['notas']}" if d["notas"] else ""
        click.echo(
            f"#{d['id']} | v{d['version']} | {d['entorno']} | {d['resultado']} | "
            f"{d['desplegado_por'] or '—'} | {d['desplegado_en']:%Y-%m-%d %H:%M}{notas}"
        )


@click.command("migrar-original")
@with_appcontext
def migrar_original():
    """Copia los registros de Usuario_hostal al nuevo modelo (la tabla original no se toca)."""
    from .migracion_original import migrar

    with _conexion() as conexion:
        try:
            resumen = migrar(conexion)
        except KeyError as error:
            raise click.ClickException(
                f"La tabla original no tiene la columna esperada {error}. Revisa docs/modelo_datos.md."
            ) from None
    if not resumen["tabla"]:
        click.echo("No se encontró la tabla Usuario_hostal. No hay nada que migrar.")
        return
    click.echo(
        f"Tabla '{resumen['tabla']}': {resumen['leidos']} registros leídos, "
        f"{resumen['huespedes_nuevos']} huéspedes nuevos, {resumen['estancias_nuevas']} estancias creadas, "
        f"{resumen['omitidos']} ya migrados antes. La tabla original quedó intacta."
    )


def init_app(app):
    from .demo import seed_demo

    for comando in (
        init_db,
        crear_usuario,
        listar_usuarios,
        desactivar_usuario,
        registrar_despliegue,
        historial_despliegues,
        migrar_original,
        seed_demo,
    ):
        app.cli.add_command(comando)
