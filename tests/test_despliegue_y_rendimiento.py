"""HU-09 (despliegue controlado y registro de versiones) y HU-10 (rendimiento)."""
import time

from conftest import datos_registro

from app import create_app
from app.db import cerrar_pool


def test_health_endpoint_reporta_estado_y_version(cliente_anonimo):
    r = cliente_anonimo.get("/health")
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["status"] == "ok"
    assert datos["base_datos"] == "conectada"
    assert datos["version"] == "2.0.0"
    assert datos["migraciones"] >= 3


def test_registrar_y_consultar_historial_de_despliegues(app, bd):
    runner = app.test_cli_runner()
    r = runner.invoke(
        args=[
            "registrar-despliegue",
            "--version", "2.0.0",
            "--entorno", "produccion",
            "--resultado", "exitoso",
            "--notas", "Entrega 3 aprobada",
        ]
    )
    assert r.exit_code == 0 and "v2.0.0" in r.output

    r_hist = runner.invoke(args=["historial-despliegues"])
    assert r_hist.exit_code == 0 and "Entrega 3 aprobada" in r_hist.output
    assert bd.execute("SELECT COUNT(*) AS n FROM despliegues").fetchone()["n"] == 1


def test_vistas_principales_responden_en_menos_de_2_segundos_con_server_timing(cliente):
    for i in range(15):
        cliente.post("/registro", datos_registro(numero_documento=f"8000{i:04d}", nombres=f"Huésped {i}"))

    for ruta in ("/en-casa", "/llegadas", "/buscar?q=Huesped", "/historial"):
        t0 = time.perf_counter()
        r = cliente.get(ruta)
        duracion = time.perf_counter() - t0
        assert r.status_code == 200
        assert duracion < 2.0, f"{ruta} tardó {duracion:.2f}s"
        assert "Server-Timing" in r.headers


def test_pool_de_conexiones_funciona_y_cierra_limpiamente(url_pruebas, claves):
    app_pool = create_app({
        "TESTING": True,
        "DATABASE_URL": url_pruebas,
        "USAR_POOL_CONEXIONES": True,
        "DB_POOL_MIN": 1,
        "DB_POOL_MAX": 4,
        **claves,
    })
    try:
        c = app_pool.test_client()
        for _ in range(5):
            assert c.get("/health").status_code == 200
        assert "db_pool" in app_pool.extensions
    finally:
        cerrar_pool(app_pool)
