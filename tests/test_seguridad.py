"""HU-07 (acceso autorizado al panel de recepción) y controles de seguridad:
CSRF, cabeceras, errores sin trazas y claves obligatorias."""
import pytest

from conftest import CLAVE_PRUEBA, USUARIO_PRUEBA, datos_registro


def test_login_solicita_usuario_y_contrasena(cliente_anonimo):
    r = cliente_anonimo.get("/login")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'name="usuario"' in html and 'name="contrasena"' in html


def test_rutas_con_datos_bloquean_acceso_sin_sesion(cliente_anonimo):
    rutas_protegidas = ["/", "/en-casa", "/llegadas", "/buscar", "/historial", "/registro", "/huespedes/1"]
    for ruta in rutas_protegidas:
        r = cliente_anonimo.get(ruta)
        assert r.status_code == 302 and "/login" in r.headers["Location"], f"Fallo en {ruta}"
    r_json = cliente_anonimo.post_json("/huespedes/verificar-documento", {"tipo": "CC", "numero": "123"})
    assert r_json.status_code == 401


def test_credenciales_incorrectas_impiden_acceso(cliente_anonimo):
    r = cliente_anonimo.iniciar_sesion(usuario=USUARIO_PRUEBA, contrasena="ClaveIncorrecta999")
    assert r.status_code == 401
    assert "Usuario o contraseña incorrectos" in r.get_data(as_text=True)
    assert cliente_anonimo.get("/en-casa").status_code == 302


def test_usuario_inexistente_o_inactivo_no_ingresa(cliente_anonimo, bd):
    r1 = cliente_anonimo.iniciar_sesion(usuario="desconocido", contrasena=CLAVE_PRUEBA)
    assert r1.status_code == 401
    bd.execute("UPDATE usuarios SET activo = false WHERE usuario = %s", (USUARIO_PRUEBA,))
    r2 = cliente_anonimo.iniciar_sesion(usuario=USUARIO_PRUEBA, contrasena=CLAVE_PRUEBA)
    assert r2.status_code == 401


def test_credenciales_validas_permiten_acceso_y_cierre_de_sesion(cliente_anonimo):
    r = cliente_anonimo.iniciar_sesion(usuario=USUARIO_PRUEBA, contrasena=CLAVE_PRUEBA)
    assert r.status_code == 302 and r.headers["Location"].endswith("/en-casa")
    assert cliente_anonimo.get("/en-casa").status_code == 200

    r_out = cliente_anonimo.cerrar_sesion(follow_redirects=True)
    assert "Sesión cerrada correctamente" in r_out.get_data(as_text=True)
    assert cliente_anonimo.get("/en-casa").status_code == 302


def test_cli_crear_y_desactivar_usuario(app, bd):
    runner = app.test_cli_runner()
    r = runner.invoke(
        args=[
            "crear-usuario",
            "--usuario", "ana_recep",
            "--nombre", "Ana Recepción",
            "--rol", "recepcion",
            "--password", "Segura2026!",
        ]
    )
    assert r.exit_code == 0 and "Usuario autorizado creado" in r.output
    fila = bd.execute("SELECT usuario, rol, activo, password_hash FROM usuarios WHERE usuario = 'ana_recep'").fetchone()
    assert fila and fila["activo"] is True and "Segura2026!" not in fila["password_hash"]

    r2 = runner.invoke(args=["desactivar-usuario", "--usuario", "ana_recep"])
    assert r2.exit_code == 0
    assert bd.execute("SELECT activo FROM usuarios WHERE usuario = 'ana_recep'").fetchone()["activo"] is False


def test_csrf_rechaza_formulario_sin_token(cliente, bd):
    r = cliente.post("/registro", datos_registro(), csrf=False)
    assert r.status_code == 400
    assert "El formulario expiró" in r.get_data(as_text=True)
    assert bd.execute("SELECT COUNT(*) AS n FROM huespedes").fetchone()["n"] == 0


def test_csrf_rechaza_fetch_sin_cabecera(cliente):
    datos = {"tipo": "CC", "numero": "123"}
    assert cliente.post_json("/huespedes/verificar-documento", datos, con_token=False).status_code == 400
    assert cliente.post_json("/huespedes/verificar-documento", datos, con_token=True).status_code == 200


def test_cabeceras_de_seguridad(cliente):
    r = cliente.get("/en-casa")
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "frame-ancestors 'none'" in csp
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "same-origin"
    assert r.headers["Cache-Control"] == "no-store"
    assert "<script>" not in r.get_data(as_text=True)


def test_paginas_de_error_amigables(cliente):
    r = cliente.get("/pagina-que-no-existe")
    assert r.status_code == 404 and "Página no encontrada" in r.get_data(as_text=True)
    assert "Traceback" not in r.get_data(as_text=True)


def test_la_app_no_arranca_sin_claves(url_pruebas):
    from app import create_app
    from app.config import ConfiguracionInvalida

    with pytest.raises(ConfiguracionInvalida, match="FERNET_KEY"):
        create_app({"TESTING": True, "DATABASE_URL": url_pruebas, "SECRET_KEY": "x" * 40,
                    "FERNET_KEY": "CAMBIAR", "HMAC_KEY": "y" * 40})
