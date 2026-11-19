"""Huéspedes: registro en recepción (HU-01, HU-02, HU-06), búsqueda por nombre o documento (HU-05)
y ficha con historial de estancias (HU-04)."""
from datetime import date, timedelta

import psycopg
from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request,
                   url_for)
from wtforms import BooleanField, HiddenField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Optional, Regexp

from ..cifrado import (cifrar, descifrar, enmascarar, huella_documento, normalizar_documento,
                       texto_para_buscar, ultimos_digitos)
from ..db import consultar, consultar_uno, ejecutar, transaccion
from ..formato import CANALES, ESTADOS_ESTANCIA, TIPOS_DOCUMENTO, hoy
from ..formularios import FechaField, FlaskForm, FormularioSimple, largo, obligatorio

bp = Blueprint("huespedes", __name__)

POR_PAGINA = 25


class FormularioRegistro(FlaskForm):
    """El orden de los campos sigue el orden real del mostrador."""

    huesped_existente_id = HiddenField()

    # 1 · Documento
    tipo_documento = SelectField("Tipo de documento",
                                 choices=[("", "Selecciona…")] + list(TIPOS_DOCUMENTO.items()),
                                 validators=[obligatorio()])
    numero_documento = StringField("Número de documento", validators=[
        obligatorio(), largo(30),
        Regexp(r"^[A-Za-z0-9.\- ]+$", message="Usa solo letras, números, puntos o guiones."),
    ])
    # 2 · Datos personales
    nombres = StringField("Nombres", validators=[obligatorio(), largo(250)])
    apellidos = StringField("Apellidos", validators=[obligatorio(), largo(250)])
    nacionalidad = StringField("Nacionalidad", validators=[obligatorio(), largo(60)])
    telefono = StringField("Teléfono / WhatsApp", validators=[
        obligatorio(),
        Regexp(r"^\+?[0-9 ()\-]{7,20}$", message="Escribe un teléfono válido, por ejemplo +57 300 123 4567."),
    ])
    correo = StringField("Correo electrónico", validators=[
        Optional(), largo(120),
        Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Escribe un correo válido, por ejemplo nombre@correo.com."),
    ])
    fecha_nacimiento = FechaField("Fecha de nacimiento", validators=[Optional()])
    acepta_datos = BooleanField(
        "El huésped autoriza el tratamiento de sus datos personales",
        validators=[DataRequired(message="Sin esta autorización no se puede registrar (Ley 1581 de 2012).")],
    )
    # 3 · Estancia (incluye estado de llegada de HU-06)
    estado_llegada = SelectField(
        "Estado de llegada",
        choices=[
            ("en_casa", "Ya llegó (en casa)"),
            ("pendiente", "Pendiente de llegada"),
        ],
        default="en_casa",
        validators=[obligatorio()],
    )
    habitacion = StringField("Habitación o cama", validators=[Optional(), largo(20)])
    canal = SelectField("Canal de reserva", choices=[("", "Selecciona…")] + [(c, c) for c in CANALES],
                        validators=[obligatorio()])
    fecha_ingreso = FechaField("Fecha de ingreso", validators=[obligatorio()])
    fecha_salida_prevista = FechaField("Fecha de salida prevista", validators=[obligatorio()])
    procedencia = StringField("Procedencia (ciudad o país)", validators=[obligatorio(), largo(250)])
    destino = StringField("Destino (siguiente ciudad o país)", validators=[obligatorio(), largo(250)])
    observaciones = TextAreaField("Observaciones", validators=[Optional(), largo(500)])

    def validate(self, extra_validators=None):
        valido = super().validate(extra_validators)
        hoy_ = hoy()
        ingreso, salida = self.fecha_ingreso.data, self.fecha_salida_prevista.data
        if ingreso and salida and salida < ingreso:
            self.fecha_salida_prevista.errors.append("La salida no puede ser anterior al ingreso.")
            valido = False
        if self.estado_llegada.data == "en_casa" and ingreso and ingreso > hoy_:
            self.fecha_ingreso.errors.append(
                "La fecha de ingreso no puede ser futura si ya llegó. Selecciona «Pendiente de llegada»."
            )
            valido = False
        if self.fecha_nacimiento.data and self.fecha_nacimiento.data > hoy_:
            self.fecha_nacimiento.errors.append("La fecha de nacimiento no puede ser futura.")
            valido = False
        return valido


def _datos_personales(form):
    return {
        "nombres": " ".join(form.nombres.data.split()),
        "apellidos": " ".join(form.apellidos.data.split()),
        "nacionalidad": form.nacionalidad.data.strip(),
        "telefono": cifrar(form.telefono.data.strip()),
        "correo": cifrar((form.correo.data or "").strip().lower()),
        "fecha_nacimiento": form.fecha_nacimiento.data,
    }


def _guardar_registro(form, existente):
    """Huésped + estancia en UNA transacción: se guarda todo o nada (HU-02, HU-06)."""
    datos = _datos_personales(form)
    busqueda = texto_para_buscar(f"{datos['nombres']} {datos['apellidos']}")
    estado = form.estado_llegada.data

    with transaccion():
        if existente:
            huesped_id = existente["id"]
            ejecutar(
                """UPDATE huespedes SET nombres=%s, apellidos=%s, nombre_busqueda=%s, nacionalidad=%s,
                          telefono_cifrado=%s, correo_cifrado=%s,
                          fecha_nacimiento=COALESCE(%s, fecha_nacimiento),
                          acepta_tratamiento_datos=true, fecha_aceptacion_datos=now(), actualizado_en=now()
                    WHERE id=%s""",
                (datos["nombres"], datos["apellidos"], busqueda, datos["nacionalidad"], datos["telefono"],
                 datos["correo"], datos["fecha_nacimiento"], huesped_id),
            )
        else:
            numero = form.numero_documento.data.strip()
            huesped_id = ejecutar(
                """INSERT INTO huespedes (nombres, apellidos, nombre_busqueda, tipo_documento,
                          numero_documento_cifrado, documento_hash, documento_ultimos, nacionalidad,
                          telefono_cifrado, correo_cifrado, fecha_nacimiento,
                          acepta_tratamiento_datos, fecha_aceptacion_datos)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, now()) RETURNING id""",
                (datos["nombres"], datos["apellidos"], busqueda, form.tipo_documento.data, cifrar(numero),
                 huella_documento(numero), ultimos_digitos(numero), datos["nacionalidad"],
                 datos["telefono"], datos["correo"], datos["fecha_nacimiento"]),
            ).fetchone()["id"]

        ejecutar(
            """INSERT INTO estancias (huesped_id, habitacion, canal, fecha_ingreso, fecha_salida_prevista,
                      checkin_en, procedencia, destino, estado, observaciones)
               VALUES (%s, %s, %s, %s, %s,
                       CASE WHEN %s = 'en_casa' THEN now() ELSE NULL END,
                       %s, %s, %s, %s)""",
            (huesped_id, (form.habitacion.data or "").strip() or None, form.canal.data, form.fecha_ingreso.data,
             form.fecha_salida_prevista.data, estado, form.procedencia.data.strip(), form.destino.data.strip(),
             estado, (form.observaciones.data or "").strip() or None),
        )
    return huesped_id


def _buscar_por_documento(tipo, numero):
    return consultar_uno(
        """SELECT h.id, h.nombres, h.apellidos,
                  (SELECT COUNT(*) FROM estancias e WHERE e.huesped_id = h.id) AS estancias,
                  EXISTS (SELECT 1 FROM estancias e WHERE e.huesped_id = h.id AND e.estado = 'en_casa') AS en_casa
             FROM huespedes h WHERE h.tipo_documento = %s AND h.documento_hash = %s""",
        (tipo, huella_documento(numero)),
    )


def _precargar_huesped(form, huesped_id):
    h = consultar_uno("SELECT * FROM huespedes WHERE id = %s", (huesped_id,))
    if not h:
        abort(404)
    form.huesped_existente_id.data = str(h["id"])
    form.tipo_documento.data = h["tipo_documento"]
    form.numero_documento.data = descifrar(h["numero_documento_cifrado"])
    form.nombres.data, form.apellidos.data = h["nombres"], h["apellidos"]
    form.nacionalidad.data = "" if h["nacionalidad"] == "Sin dato" else h["nacionalidad"]
    form.telefono.data = descifrar(h["telefono_cifrado"])
    form.correo.data = descifrar(h["correo_cifrado"])
    form.fecha_nacimiento.data = h["fecha_nacimiento"]
    return h


@bp.route("/registro", methods=["GET", "POST"])
def registro():
    form = FormularioRegistro()
    coincidencia = None
    if request.method == "GET":
        form.fecha_ingreso.data = hoy()
        form.fecha_salida_prevista.data = hoy() + timedelta(days=1)
        if request.args.get("estado") in ("en_casa", "pendiente"):
            form.estado_llegada.data = request.args.get("estado")
        if request.args.get("huesped", type=int):
            coincidencia = _precargar_huesped(form, request.args.get("huesped", type=int))
            coincidencia = {**coincidencia, "confirmado": True}
    elif form.validate_on_submit():
        existente = _buscar_por_documento(form.tipo_documento.data, form.numero_documento.data)
        if existente and existente["en_casa"] and form.estado_llegada.data == "en_casa":
            flash("Este huésped ya está en casa. Revisa su estancia actual antes de registrar otra.", "error")
            return render_template("huespedes/registro.html", form=form, coincidencia=existente)
        if existente and form.huesped_existente_id.data != str(existente["id"]):
            form.huesped_existente_id.data = str(existente["id"])
            return render_template("huespedes/registro.html", form=form, coincidencia=existente)
        try:
            huesped_id = _guardar_registro(form, existente)
        except psycopg.errors.UniqueViolation:
            flash("Este huésped acaba de ser registrado desde otro equipo. Búscalo antes de continuar.", "error")
        else:
            mensaje = (
                "Huésped registrado como pendiente de llegada."
                if form.estado_llegada.data == "pendiente"
                else "Huésped registrado."
            )
            flash(mensaje, "ok")
            return redirect(url_for("huespedes.ficha", huesped_id=huesped_id))
    return render_template("huespedes/registro.html", form=form, coincidencia=coincidencia)


@bp.post("/huespedes/verificar-documento")
def verificar_documento():
    """Llamado por JavaScript (fetch con token CSRF en la cabecera) al escribir el documento."""
    datos = request.get_json(silent=True) or {}
    tipo, numero = str(datos.get("tipo", "")), str(datos.get("numero", ""))
    if tipo not in TIPOS_DOCUMENTO or not normalizar_documento(numero):
        return jsonify(existe=False)
    h = _buscar_por_documento(tipo, numero)
    if not h:
        return jsonify(existe=False)
    return jsonify(existe=True, id=h["id"], nombre=f"{h['nombres']} {h['apellidos']}",
                   estancias=h["estancias"], en_casa=h["en_casa"],
                   url_ficha=url_for("huespedes.ficha", huesped_id=h["id"]))


@bp.get("/politica-de-datos")
def politica_datos():
    """Política corta de tratamiento de datos (Ley 1581 de 2012) para leerle al huésped."""
    return render_template("politica_datos.html")


# ---------------------------------------------------------------- Búsqueda de huéspedes (HU-05)

def _escapar_like(texto):
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@bp.get("/buscar")
def buscar():
    """HU-05: búsqueda rápida por nombre/apellidos o número de documento (HMAC)."""
    q = request.args.get("q", "").strip()
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    filas = []
    total = 0

    if q:
        texto = texto_para_buscar(q)
        tokens = [t for t in texto.split() if t][:6]
        doc_normalizado = normalizar_documento(q)
        huella = huella_documento(q) if doc_normalizado else None

        condiciones = []
        parametros = []
        if huella:
            condiciones.append("h.documento_hash = %s")
            parametros.append(huella)
        if tokens:
            condiciones_nombre = []
            for token in tokens:
                condiciones_nombre.append("h.nombre_busqueda LIKE %s ESCAPE '\\'")
                parametros.append(f"%{_escapar_like(token)}%")
            condiciones.append("(" + " AND ".join(condiciones_nombre) + ")")

        if condiciones:
            where_sql = " OR ".join(condiciones)
            parametros.extend([POR_PAGINA, (pagina - 1) * POR_PAGINA])
            filas = consultar(
                f"""SELECT h.id, h.nombres, h.apellidos, h.tipo_documento, h.documento_ultimos,
                          h.nacionalidad, h.es_demo,
                          ult.estado AS estado_actual, ult.habitacion AS habitacion_actual,
                          ult.fecha_ingreso AS ultimo_ingreso,
                          (SELECT COUNT(*) FROM estancias e WHERE e.huesped_id = h.id) AS total_estancias,
                          COUNT(*) OVER () AS total_filas
                     FROM huespedes h
                     LEFT JOIN LATERAL (
                         SELECT e.estado, e.habitacion, e.fecha_ingreso
                           FROM estancias e
                          WHERE e.huesped_id = h.id
                          ORDER BY CASE e.estado WHEN 'en_casa' THEN 1 WHEN 'pendiente' THEN 2 ELSE 3 END,
                                   e.fecha_ingreso DESC, e.id DESC
                          LIMIT 1
                     ) ult ON true
                    WHERE {where_sql}
                    ORDER BY h.apellidos, h.nombres
                    LIMIT %s OFFSET %s""",
                tuple(parametros),
            )
            total = filas[0]["total_filas"] if filas else 0

    return render_template(
        "huespedes/buscar.html",
        q=q,
        resultados=filas,
        total=total,
        pagina=pagina,
        paginas=max((total + POR_PAGINA - 1) // POR_PAGINA, 1),
        enmascarar=enmascarar,
    )


# ---------------------------------------------------------------- Ficha e historial (HU-04)

def _fecha_param(nombre):
    valor = request.args.get(nombre, "")
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _ficha(huesped_id, documento_completo=None):
    h = consultar_uno("SELECT * FROM huespedes WHERE id = %s", (huesped_id,))
    if not h:
        abort(404)
    desde, hasta = _fecha_param("desde"), _fecha_param("hasta")
    estancias = consultar(
        """SELECT e.id, e.huesped_id, e.habitacion, e.canal, e.fecha_ingreso, e.fecha_salida_prevista,
                  e.checkin_en, e.checkout_en, e.procedencia, e.destino, e.estado, e.observaciones
             FROM estancias e
            WHERE e.huesped_id = %s
              AND (%s::date IS NULL OR e.fecha_ingreso >= %s::date)
              AND (%s::date IS NULL OR e.fecha_ingreso <= %s::date)
            ORDER BY e.fecha_ingreso DESC, e.id DESC""",
        (huesped_id, desde, desde, hasta, hasta),
    )
    if desde is None and hasta is None:
        en_casa = any(e["estado"] == "en_casa" for e in estancias)
    else:
        en_casa = bool(
            consultar_uno("SELECT 1 FROM estancias WHERE huesped_id = %s AND estado = 'en_casa'", (huesped_id,))
        )
    contacto = {"telefono": descifrar(h["telefono_cifrado"]), "correo": descifrar(h["correo_cifrado"])}
    return render_template(
        "huespedes/ficha.html", h=h, estancias=estancias, contacto=contacto, desde=desde, hasta=hasta,
        documento_mascara=enmascarar(h["documento_ultimos"]), documento_completo=documento_completo,
        form_simple=FormularioSimple(), en_casa=en_casa,
    )


@bp.get("/huespedes/<int:huesped_id>")
def ficha(huesped_id):
    return _ficha(huesped_id)


@bp.post("/huespedes/<int:huesped_id>/documento")
def ver_documento(huesped_id):
    """Muestra el documento completo y deja constancia en el log (solo identificadores)."""
    h = consultar_uno("SELECT numero_documento_cifrado FROM huespedes WHERE id = %s", (huesped_id,))
    if not h:
        abort(404)
    current_app.logger.info("Documento completo consultado: huesped_id=%s", huesped_id)
    return _ficha(huesped_id, documento_completo=descifrar(h["numero_documento_cifrado"]))


@bp.get("/historial")
def historial():
    desde = _fecha_param("desde") or hoy() - timedelta(days=30)
    hasta = _fecha_param("hasta") or hoy()
    estado = request.args.get("estado", "")
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    filtro_estado = estado if estado in ESTADOS_ESTANCIA else None
    filas = consultar(
        """SELECT e.id, e.huesped_id, e.habitacion, e.canal, e.fecha_ingreso, e.procedencia, e.destino, e.estado,
                  hu.nombres, hu.apellidos, hu.documento_ultimos, hu.tipo_documento, hu.es_demo AS huesped_demo,
                  COUNT(*) OVER () AS total_filas
             FROM estancias e
             JOIN huespedes hu ON hu.id = e.huesped_id
            WHERE e.fecha_ingreso BETWEEN %s AND %s
              AND (%s::text IS NULL OR e.estado = %s::text)
            ORDER BY e.fecha_ingreso DESC, e.id DESC
            LIMIT %s OFFSET %s""",
        (desde, hasta, filtro_estado, filtro_estado, POR_PAGINA, (pagina - 1) * POR_PAGINA),
    )
    total = filas[0]["total_filas"] if filas else 0
    return render_template("huespedes/historial.html", filas=filas, desde=desde, hasta=hasta, estado=estado,
                           pagina=pagina, paginas=max((total + POR_PAGINA - 1) // POR_PAGINA, 1), total=total,
                           enmascarar=enmascarar)
