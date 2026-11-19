"""Estancias: huéspedes en casa (HU-03), confirmación de llegada (HU-06),
registro de salida y verificación de salud para despliegue (HU-09)."""
import psycopg
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from ..cifrado import enmascarar
from ..db import consultar, consultar_uno, ejecutar
from ..formularios import FormularioSimple

bp = Blueprint("estancias", __name__)

POR_PAGINA = 20


def _volver(por_defecto="estancias.en_casa"):
    """A dónde regresar tras una acción (solo rutas internas)."""
    destino = request.form.get("volver", "")
    if not destino.startswith("/") or destino.startswith("//") or "\\" in destino:
        destino = url_for(por_defecto)
    return destino


@bp.get("/health")
def health():
    """Endpoint de verificación tras despliegue (HU-09): no expone datos personales."""
    try:
        consultar_uno("SELECT 1 AS ok")
        mig = consultar_uno("SELECT COUNT(*) AS total FROM migraciones_aplicadas")
        ultimo_despliegue = consultar_uno(
            "SELECT version, resultado, desplegado_en FROM despliegues ORDER BY desplegado_en DESC, id DESC LIMIT 1"
        )
    except psycopg.Error:
        return jsonify(
            status="error",
            version=current_app.config["APP_VERSION"],
            entorno=current_app.config["ENTORNO"],
            base_datos="sin_conexion",
        ), 503

    return jsonify(
        status="ok",
        version=current_app.config["APP_VERSION"],
        entorno=current_app.config["ENTORNO"],
        base_datos="conectada",
        migraciones=mig["total"] if mig else 0,
        ultimo_despliegue=(
            {
                "version": ultimo_despliegue["version"],
                "resultado": ultimo_despliegue["resultado"],
                "desplegado_en": ultimo_despliegue["desplegado_en"].isoformat(),
            }
            if ultimo_despliegue
            else None
        ),
    )


@bp.get("/")
def inicio():
    return redirect(url_for("estancias.en_casa"))


@bp.get("/en-casa")
def en_casa():
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    filas = consultar(
        """SELECT e.id, e.huesped_id, e.habitacion, e.fecha_ingreso, e.fecha_salida_prevista, e.estado,
                  hu.nombres, hu.apellidos, hu.tipo_documento, hu.documento_ultimos, hu.es_demo AS huesped_demo,
                  COUNT(*) OVER () AS total_filas
             FROM estancias e
             JOIN huespedes hu ON hu.id = e.huesped_id
            WHERE e.estado = 'en_casa'
            ORDER BY e.fecha_salida_prevista, hu.apellidos
            LIMIT %s OFFSET %s""",
        (POR_PAGINA, (pagina - 1) * POR_PAGINA),
    )
    total = filas[0]["total_filas"] if filas else 0
    return render_template(
        "estancias/en_casa.html", en_casa=filas, pagina=pagina, total=total,
        paginas=max((total + POR_PAGINA - 1) // POR_PAGINA, 1), enmascarar=enmascarar,
        form_simple=FormularioSimple(),
    )


@bp.get("/llegadas")
def llegadas():
    """HU-06: huéspedes pendientes de llegada listos para confirmar su ingreso."""
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    filas = consultar(
        """SELECT e.id, e.huesped_id, e.habitacion, e.canal, e.fecha_ingreso, e.fecha_salida_prevista, e.estado,
                  hu.nombres, hu.apellidos, hu.tipo_documento, hu.documento_ultimos, hu.es_demo AS huesped_demo,
                  COUNT(*) OVER () AS total_filas
             FROM estancias e
             JOIN huespedes hu ON hu.id = e.huesped_id
            WHERE e.estado = 'pendiente'
            ORDER BY e.fecha_ingreso ASC, hu.apellidos ASC
            LIMIT %s OFFSET %s""",
        (POR_PAGINA, (pagina - 1) * POR_PAGINA),
    )
    total = filas[0]["total_filas"] if filas else 0
    return render_template(
        "estancias/llegadas.html", pendientes=filas, pagina=pagina, total=total,
        paginas=max((total + POR_PAGINA - 1) // POR_PAGINA, 1), enmascarar=enmascarar,
        form_simple=FormularioSimple(),
    )


@bp.post("/estancias/<int:estancia_id>/confirmar-llegada")
def confirmar_llegada(estancia_id):
    """HU-06: pasa una estancia de 'pendiente' a 'en_casa' y guarda la hora de llegada."""
    try:
        cambiada = ejecutar(
            """UPDATE estancias
                  SET estado = 'en_casa', checkin_en = now(), actualizado_en = now()
                WHERE id = %s AND estado = 'pendiente'""",
            (estancia_id,),
        )
    except psycopg.errors.UniqueViolation:
        flash("Este huésped ya figura en casa en otra estancia activa.", "error")
        return redirect(_volver("estancias.llegadas"))

    if cambiada.rowcount == 1:
        fila = consultar_uno(
            """SELECT hu.nombres || ' ' || hu.apellidos AS nombre FROM estancias e
                 JOIN huespedes hu ON hu.id = e.huesped_id WHERE e.id = %s""",
            (estancia_id,),
        )
        flash(f"Llegada confirmada: {fila['nombre']} ahora está en casa.", "ok")
    else:
        flash("Esta estancia no se encuentra pendiente de llegada.", "error")
    return redirect(_volver("estancias.llegadas"))


@bp.post("/estancias/<int:estancia_id>/marcar-pendiente")
def marcar_pendiente(estancia_id):
    """HU-06 (criterio 2): permite revertir a 'pendiente' si se confirmó una llegada por error."""
    cambiada = ejecutar(
        """UPDATE estancias
              SET estado = 'pendiente', checkin_en = NULL, actualizado_en = now()
            WHERE id = %s AND estado = 'en_casa'""",
        (estancia_id,),
    )
    if cambiada.rowcount == 1:
        fila = consultar_uno(
            """SELECT hu.nombres || ' ' || hu.apellidos AS nombre FROM estancias e
                 JOIN huespedes hu ON hu.id = e.huesped_id WHERE e.id = %s""",
            (estancia_id,),
        )
        flash(f"Estado corregido a pendiente de llegada: {fila['nombre']}.", "ok")
    else:
        flash("Solo se puede pasar a pendiente una estancia que esté en casa.", "error")
    return redirect(_volver("estancias.en_casa"))


@bp.post("/estancias/<int:estancia_id>/salida")
def salida(estancia_id):
    """Registra la fecha y hora de salida (el campo fecha_Checkout del formulario original)."""
    cambiada = ejecutar(
        """UPDATE estancias
              SET estado = 'finalizada', checkout_en = now(), actualizado_en = now()
            WHERE id = %s AND estado = 'en_casa'""",
        (estancia_id,),
    )
    if cambiada.rowcount == 1:
        fila = consultar_uno(
            """SELECT hu.nombres || ' ' || hu.apellidos AS nombre FROM estancias e
                 JOIN huespedes hu ON hu.id = e.huesped_id WHERE e.id = %s""",
            (estancia_id,),
        )
        flash(f"Salida registrada: {fila['nombre']}.", "ok")
    else:
        flash("Esta estancia no está en casa.", "error")
    return redirect(_volver())
