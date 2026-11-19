"""Piezas comunes de los formularios (Flask-WTF + WTForms).

FlaskForm agrega automáticamente el token CSRF a cada formulario.
Los mensajes de error se escriben en español para que recepción los entienda.
"""
from flask_wtf import FlaskForm as _FlaskForm
from wtforms import DateField
from wtforms.validators import DataRequired, Length

OBLIGATORIO = "Este campo es obligatorio."


class FlaskForm(_FlaskForm):
    """Base de todos los formularios: mensajes integrados de WTForms en español."""

    class Meta:
        locales = ["es_ES", "es"]


def obligatorio():
    return DataRequired(message=OBLIGATORIO)


def largo(maximo, minimo=-1):
    if minimo > 0:
        return Length(min=minimo, max=maximo, message=f"Debe tener entre {minimo} y {maximo} caracteres.")
    return Length(max=maximo, message=f"Máximo {maximo} caracteres.")


class FechaField(DateField):
    def process_formdata(self, valuelist):
        try:
            super().process_formdata(valuelist)
        except ValueError:
            self.data = None
            raise ValueError("Escribe una fecha válida.") from None


class FormularioSimple(FlaskForm):
    """Formulario vacío: solo lleva el token CSRF (botones de una acción)."""
