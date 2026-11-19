"""Autenticación del personal de recepción (HU-07)."""
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from wtforms import PasswordField, StringField

from ..cifrado import verificar_contrasena
from ..db import consultar_uno, ejecutar
from ..formularios import FlaskForm, largo, obligatorio

bp = Blueprint("auth", __name__)


class FormularioLogin(FlaskForm):
    usuario = StringField("Usuario", validators=[obligatorio(), largo(40)])
    contrasena = PasswordField("Contraseña", validators=[obligatorio(), largo(128)])


def _destino_seguro(valor):
    """Evita redirecciones abiertas: solo permite rutas internas que inicien con '/'."""
    if valor and valor.startswith("/") and not valor.startswith("//") and "\\" not in valor:
        return valor
    return url_for("estancias.en_casa")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if getattr(g, "usuario", None) is not None:
        return redirect(url_for("estancias.en_casa"))

    form = FormularioLogin()
    siguiente = request.args.get("siguiente") or request.form.get("siguiente") or ""

    if form.validate_on_submit():
        nombre_usuario = form.usuario.data.strip().lower()
        cuenta = consultar_uno(
            "SELECT id, usuario, nombre_completo, rol, password_hash, activo FROM usuarios WHERE usuario = %s",
            (nombre_usuario,),
        )
        if cuenta and cuenta["activo"] and verificar_contrasena(cuenta["password_hash"], form.contrasena.data):
            session.clear()
            session["usuario_id"] = cuenta["id"]
            session.permanent = True
            ejecutar("UPDATE usuarios SET ultimo_acceso = now() WHERE id = %s", (cuenta["id"],))
            current_app.logger.info("Inicio de sesión autorizado: usuario=%s", cuenta["usuario"])
            flash(f"Bienvenido, {cuenta['nombre_completo']}.", "ok")
            return redirect(_destino_seguro(siguiente))

        current_app.logger.warning("Intento fallido de inicio de sesión: usuario=%s", nombre_usuario)
        flash("Usuario o contraseña incorrectos.", "error")
        return render_template("auth/login.html", form=form, siguiente=siguiente), 401

    return render_template("auth/login.html", form=form, siguiente=siguiente)


@bp.post("/logout")
def logout():
    usuario = getattr(g, "usuario", None)
    session.clear()
    if usuario:
        current_app.logger.info("Cierre de sesión: usuario=%s", usuario["usuario"])
    flash("Sesión cerrada correctamente.", "ok")
    return redirect(url_for("auth.login"))
