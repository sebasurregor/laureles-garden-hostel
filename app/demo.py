"""Datos de prueba: flask --app app seed-demo

Todo lo que se crea aquí queda con es_demo = true (y se ve con la etiqueta DEMO).
Los nombres, documentos y habitaciones son INVENTADOS: no son datos reales del hostal.
    --volumen 5000   agrega 5.000 huéspedes extra para pruebas de rendimiento (HU-10)
    --borrar         elimina únicamente los datos demo
"""
import random
from datetime import timedelta

import click
from flask.cli import with_appcontext

from .cifrado import cifrar, huella_documento, texto_para_buscar, ultimos_digitos
from .db import consultar_uno, ejecutar, transaccion
from .formato import hoy

HABITACIONES_DEMO = ["101", "102", "103", "104", "201", "202", "203", "204", "205"]
NOMBRES = ["Ana", "Camila", "Valentina", "Lucía", "Sofía", "Mariana", "Laura", "Emma", "Julia", "Clara",
           "Juan", "Santiago", "Mateo", "Andrés", "Felipe", "Lukas", "Pierre", "Tom", "Diego", "Martín",
           "José", "María José", "Hannah", "Noah", "Liam", "Chloé", "Íñigo", "Nicolás", "Paula", "Tomás"]
APELLIDOS = ["Gómez", "Restrepo", "Pérez", "Muñoz", "Álvarez", "Zapata", "Ospina", "Müller", "Dubois", "Smith",
             "García", "Fernández", "Rossi", "Jansen", "Peña", "Castaño", "Londoño", "Schmidt", "Martin", "López"]
NACIONALIDADES = [("Colombia", "CC"), ("Colombia", "CC"), ("Colombia", "CC"), ("Alemania", "PA"),
                  ("Francia", "PA"), ("Estados Unidos", "PA"), ("Argentina", "PA"), ("México", "PA"),
                  ("Países Bajos", "PA"), ("España", "PA"), ("Venezuela", "PPT"), ("Chile", "PA")]
CIUDADES = ["Bogotá", "Cali", "Cartagena", "Santa Marta", "Salento", "Guatapé", "Quito", "Lima", "Panamá",
            "Madrid", "Berlín", "Ciudad de México", "Buenos Aires", "Jardín", "San Gil"]
CANALES = ["Booking", "Booking", "Hostelworld", "Hostelworld", "Airbnb", "Google", "Directo", "Sin reserva"]


def _insertar_huesped(azar, numero_unico):
    nombres = azar.choice(NOMBRES)
    apellidos = f"{azar.choice(APELLIDOS)} {azar.choice(APELLIDOS)}"
    nacionalidad, tipo = azar.choice(NACIONALIDADES)
    documento = f"{azar.randint(10, 99)}{numero_unico:07d}" if tipo == "CC" else f"DX{numero_unico:07d}"
    telefono = f"+57 3{azar.randint(0, 2)}{azar.randint(0, 9)} {azar.randint(100, 999)} {azar.randint(1000, 9999)}"
    return ejecutar(
        """INSERT INTO huespedes (nombres, apellidos, nombre_busqueda, tipo_documento, numero_documento_cifrado,
                  documento_hash, documento_ultimos, nacionalidad, telefono_cifrado, correo_cifrado,
                  acepta_tratamiento_datos, fecha_aceptacion_datos, es_demo)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, now(), true) RETURNING id""",
        (nombres, apellidos, texto_para_buscar(f"{nombres} {apellidos}"), tipo, cifrar(documento),
         huella_documento(documento), ultimos_digitos(documento), nacionalidad, cifrar(telefono),
         cifrar(f"demo{numero_unico}@ejemplo.com")),
    ).fetchone()["id"]


def _insertar_estancia(azar, huesped_id, habitacion, ingreso, noches, estado):
    salida = ingreso + timedelta(days=noches)
    ejecutar(
        """INSERT INTO estancias (huesped_id, habitacion, canal, fecha_ingreso, fecha_salida_prevista, checkin_en,
                  checkout_en, procedencia, destino, estado, es_demo)
           VALUES (%s, %s, %s, %s, %s,
                   CASE WHEN %s THEN NULL ELSE LEAST((%s::date + time '15:10')::timestamptz, now()) END,
                   CASE WHEN %s THEN (%s::date + time '11:20')::timestamptz END,
                   %s, %s, %s, true)""",
        (huesped_id, habitacion, azar.choice(CANALES), ingreso, salida,
         estado == "pendiente", ingreso,
         estado == "finalizada", salida, azar.choice(CIUDADES), azar.choice(CIUDADES), estado),
    )


def _borrar_demo():
    with transaccion():
        ejecutar("DELETE FROM estancias WHERE es_demo OR huesped_id IN (SELECT id FROM huespedes WHERE es_demo)")
        ejecutar("DELETE FROM huespedes WHERE es_demo")


@click.command("seed-demo")
@with_appcontext
@click.option("--volumen", default=0, help="Huéspedes demo extra para pruebas de rendimiento (ej. 5000).")
@click.option("--borrar", is_flag=True, help="Elimina solo los datos demo y termina.")
def seed_demo(volumen, borrar):
    """Carga datos de prueba marcados como DEMO."""
    if borrar:
        _borrar_demo()
        click.echo("Datos demo eliminados. Los datos reales no se tocaron.")
        return
    if consultar_uno("SELECT 1 FROM huespedes WHERE NOT es_demo LIMIT 1"):
        raise click.ClickException("La base ya tiene huéspedes reales. Los datos demo solo se cargan en una base "
                                   "vacía o de pruebas, para no mezclarlos.")
    _borrar_demo()
    azar = random.Random(2026)
    hoy_ = hoy()
    numero = 1
    with transaccion():
        for _ in range(45):
            h = _insertar_huesped(azar, numero)
            numero += 1
            ingreso = hoy_ - timedelta(days=azar.randint(4, 35))
            _insertar_estancia(azar, h, azar.choice(HABITACIONES_DEMO), ingreso, azar.randint(1, 3), "finalizada")
        for posicion in (2, 5, 9):
            fila = consultar_uno("SELECT id FROM huespedes WHERE es_demo ORDER BY id OFFSET %s LIMIT 1", (posicion,))
            _insertar_estancia(azar, fila["id"], azar.choice(HABITACIONES_DEMO), hoy_ - timedelta(days=2), 1,
                               "finalizada")
        for i in range(18):
            h = _insertar_huesped(azar, numero)
            numero += 1
            noches = azar.randint(2, 4)
            ingreso = hoy_ if i < 3 else hoy_ - timedelta(days=noches - (0 if i < 6 else 1))
            _insertar_estancia(azar, h, azar.choice(HABITACIONES_DEMO), ingreso, noches, "en_casa")
        for i in range(10):
            h = _insertar_huesped(azar, numero)
            numero += 1
            desfase = 0 if i < 4 else azar.randint(1, 5)
            ingreso = hoy_ + timedelta(days=desfase)
            _insertar_estancia(azar, h, azar.choice(HABITACIONES_DEMO), ingreso, azar.randint(1, 4), "pendiente")
        for i in range(volumen):
            h = _insertar_huesped(azar, numero)
            numero += 1
            if i % 3 == 0:
                ingreso = hoy_ - timedelta(days=azar.randint(1, 90))
                _insertar_estancia(azar, h, azar.choice(HABITACIONES_DEMO), ingreso, azar.randint(1, 3), "finalizada")
    click.echo(f"Datos demo cargados: {numero - 1} huéspedes (incluye pendientes de llegada). Todo está marcado como DEMO.")
