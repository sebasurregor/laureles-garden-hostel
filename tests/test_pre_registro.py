"""Pruebas del formulario público de pre-registro de huéspedes."""
import os
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from app import create_app
from app.cifrado import descifrar, hash_contrasena, huella_documento
from app.db import aplicar_migraciones, cerrar_pool, conectar, consultar, consultar_uno
from app.formato import hoy

load_dotenv()


@pytest.fixture
def app_pre_registro():
    test_url = os.getenv("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("TEST_DATABASE_URL no está configurada.")

    with conectar(test_url) as conexion:
        aplicar_migraciones(conexion)
        conexion.execute("TRUNCATE TABLE estancias, huespedes, usuarios, despliegues RESTART IDENTITY CASCADE")
        conexion.execute(
            """INSERT INTO usuarios (usuario, nombre_completo, rol, password_hash, activo)
               VALUES ('recepcion', 'Recepción Test', 'recepcion', %s, true)""",
            (hash_contrasena("ClaveSegura123"),),
        )

    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "DATABASE_URL": test_url,
            "SECRET_KEY": "s" * 40,
            "HMAC_KEY": "h" * 40,
            "FERNET_KEY": Fernet.generate_key().decode(),
            "USAR_POOL_CONEXIONES": False,
        }
    )
    yield app
    cerrar_pool(app)


def _datos_validos(documento="1020304050", nombres="Laura", apellidos="Gómez", dias_ingreso=0):
    ingreso = hoy() + timedelta(days=dias_ingreso)
    salida = ingreso + timedelta(days=2)
    return {
        "tipo_documento": "CC",
        "numero_documento": documento,
        "nombres": nombres,
        "apellidos": apellidos,
        "nacionalidad": "Colombia",
        "telefono": "+57 300 555 0199",
        "correo": "laura@ejemplo.com",
        "fecha_nacimiento": "1999-05-10",
        "acepta_datos": "y",
        "canal": "Booking",
        "fecha_ingreso": ingreso.isoformat(),
        "fecha_salida_prevista": salida.isoformat(),
        "procedencia": "Bogotá",
        "destino": "Cartagena",
        "observaciones": "Llego a las 4 pm",
        "sitio_web": "",
    }


def test_pre_registro_publico_aparece_en_llegadas_y_se_confirma(app_pre_registro):
    cliente = app_pre_registro.test_client()

    # 1. El formulario es accesible sin sesión, pero /llegadas y /en-casa siguen protegidos.
    assert cliente.get("/pre-registro").status_code == 200
    assert cliente.get("/llegadas").status_code == 302
    assert cliente.get("/en-casa").status_code == 302

    # 2. Envío válido redirige a confirmación y crea huésped cifrado + estancia pendiente.
    resp = cliente.post("/pre-registro", data=_datos_validos(), follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/pre-registro/confirmado")
    assert cliente.get("/pre-registro/confirmado").status_code == 200

    with app_pre_registro.app_context():
        huesped = consultar_uno(
            "SELECT * FROM huespedes WHERE documento_hash = %s",
            (huella_documento("1020304050"),),
        )
        assert huesped is not None
        assert descifrar(huesped["numero_documento_cifrado"]) == "1020304050"
        assert descifrar(huesped["telefono_cifrado"]) == "+57 300 555 0199"
        estancia = consultar_uno("SELECT * FROM estancias WHERE huesped_id = %s", (huesped["id"],))
        assert estancia["estado"] == "pendiente"
        assert estancia["checkin_en"] is None
        assert estancia["habitacion"] is None
        estancia_id = estancia["id"]

    # 3. Recepción inicia sesión, ve al huésped en /llegadas y confirma su ingreso a /en-casa.
    login = cliente.post("/login", data={"usuario": "recepcion", "contrasena": "ClaveSegura123"})
    assert login.status_code == 302

    llegadas = cliente.get("/llegadas")
    assert llegadas.status_code == 200
    assert "Laura Gómez" in llegadas.get_data(as_text=True)

    confirmar = cliente.post(f"/estancias/{estancia_id}/confirmar-llegada", follow_redirects=False)
    assert confirmar.status_code == 302

    en_casa = cliente.get("/en-casa")
    assert en_casa.status_code == 200
    assert "Laura Gómez" in en_casa.get_data(as_text=True)


def test_pre_registro_no_sobrescribe_huesped_existente_ni_duplica_estancia(app_pre_registro):
    cliente = app_pre_registro.test_client()

    assert cliente.post("/pre-registro", data=_datos_validos(nombres="Laura", apellidos="Gómez")).status_code == 302
    # Segundo envío con mismo documento y fechas, pero nombre alterado: no sobrescribe ni duplica.
    assert cliente.post("/pre-registro", data=_datos_validos(nombres="Otro", apellidos="Nombre")).status_code == 302

    with app_pre_registro.app_context():
        huespedes = consultar("SELECT * FROM huespedes")
        estancias = consultar("SELECT * FROM estancias")
        assert len(huespedes) == 1
        assert huespedes[0]["nombres"] == "Laura"
        assert len(estancias) == 1


def test_pre_registro_reutiliza_huesped_en_nueva_estancia_con_otras_fechas(app_pre_registro):
    cliente = app_pre_registro.test_client()

    assert cliente.post("/pre-registro", data=_datos_validos(dias_ingreso=0)).status_code == 302
    assert cliente.post("/pre-registro", data=_datos_validos(dias_ingreso=5)).status_code == 302

    with app_pre_registro.app_context():
        huespedes = consultar("SELECT * FROM huespedes")
        estancias = consultar("SELECT * FROM estancias ORDER BY fecha_ingreso ASC")
        assert len(huespedes) == 1
        assert len(estancias) == 2
        assert all(e["estado"] == "pendiente" for e in estancias)


def test_pre_registro_ignora_bots_y_valida_fechas_y_autorizacion(app_pre_registro):
    cliente = app_pre_registro.test_client()

    # Campo trampa lleno -> no inserta nada.
    datos_bot = _datos_validos()
    datos_bot["sitio_web"] = "https://spam.ejemplo"
    assert cliente.post("/pre-registro", data=datos_bot).status_code == 302

    # Fechas invertidas -> vuelve con error de validación (200) y no inserta nada.
    datos_mal = _datos_validos(dias_ingreso=3)
    datos_mal["fecha_salida_prevista"] = hoy().isoformat()
    assert cliente.post("/pre-registro", data=datos_mal).status_code == 200

    # Sin autorización de tratamiento de datos -> vuelve con error (200) y no inserta nada.
    datos_sin_consentimiento = _datos_validos()
    datos_sin_consentimiento.pop("acepta_datos")
    assert cliente.post("/pre-registro", data=datos_sin_consentimiento).status_code == 200

    with app_pre_registro.app_context():
        assert consultar("SELECT * FROM huespedes") == []
        assert consultar("SELECT * FROM estancias") == []
