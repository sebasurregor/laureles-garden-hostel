"""Textos y formatos que se muestran en pantalla (fechas, roles y estados)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import g

ZONA = ZoneInfo("America/Bogota")

TIPOS_DOCUMENTO = {
    "CC": "Cédula de ciudadanía",
    "CE": "Cédula de extranjería",
    "PA": "Pasaporte",
    "TI": "Tarjeta de identidad",
    "PPT": "Permiso por Protección Temporal",
    "OTRO": "Otro",
}
CANALES = ["Booking", "Airbnb", "Hostelworld", "Google", "Directo", "Sin reserva"]
ESTADOS_ESTANCIA = {
    "pendiente": "Pendiente de llegada",
    "en_casa": "En casa",
    "finalizada": "Finalizada",
}
ROLES_USUARIO = {
    "admin": "Administrador",
    "recepcion": "Recepción",
}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def hoy():
    """Fecha de hoy en Colombia (no en la hora del servidor ni en UTC)."""
    return datetime.now(ZONA).date()


def fecha(valor):
    if not valor:
        return "—"
    if isinstance(valor, datetime):
        valor = valor.astimezone(ZONA).date()
    return f"{valor.day:02d} {MESES[valor.month - 1]} {valor.year}"


def fecha_hora(valor):
    if not valor:
        return "—"
    local = valor.astimezone(ZONA)
    return f"{fecha(local.date())} · {local:%I:%M %p}".replace("AM", "a. m.").replace("PM", "p. m.")


def init_app(app):
    app.jinja_env.filters.update(fecha=fecha, fecha_hora=fecha_hora)

    @app.context_processor
    def variables_comunes():
        return {
            "NOMBRE_HOSTAL": app.config["NOMBRE_HOSTAL"],
            "APP_VERSION": app.config["APP_VERSION"],
            "TIPOS_DOCUMENTO": TIPOS_DOCUMENTO,
            "ESTADOS_ESTANCIA": ESTADOS_ESTANCIA,
            "ROLES_USUARIO": ROLES_USUARIO,
            "usuario_actual": getattr(g, "usuario", None),
            "hoy": hoy(),
        }
