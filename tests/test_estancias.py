"""HU-03 (consulta de huéspedes en casa) y HU-04 (historial de huéspedes)."""
from datetime import timedelta

from conftest import datos_registro

from app.formato import hoy


def registrar_en_casa(cliente, documento="1036555210", **cambios):
    r = cliente.post("/registro", datos_registro(numero_documento=documento, **cambios))
    assert r.status_code == 302, r.get_data(as_text=True)[:500]


def test_inicio_lleva_a_huespedes_en_casa(cliente):
    r = cliente.get("/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/en-casa")


def test_listado_en_casa_con_documento_enmascarado_y_habitacion(cliente):
    registrar_en_casa(cliente)
    registrar_en_casa(cliente, documento="44332211", habitacion="Dorm 2")
    html = cliente.get("/en-casa").get_data(as_text=True)
    assert "•••• 5210" in html and "•••• 2211" in html
    assert "1036555210" not in html and "44332211" not in html
    assert "Dorm 2" in html and "Huéspedes en casa (2)" in html


def test_en_casa_se_pagina(cliente):
    for i in range(23):
        registrar_en_casa(cliente, documento=f"9000{i:04d}")
    assert "Página 1 de 2" in cliente.get("/en-casa").get_data(as_text=True)
    assert "Página 2 de 2" in cliente.get("/en-casa?pagina=2").get_data(as_text=True)


def test_registrar_salida(cliente, bd):
    registrar_en_casa(cliente)
    estancia = bd.execute("SELECT id FROM estancias").fetchone()["id"]
    r = cliente.post(f"/estancias/{estancia}/salida", follow_redirects=True)
    assert "Salida registrada" in r.get_data(as_text=True)
    e = bd.execute("SELECT * FROM estancias WHERE id = %s", (estancia,)).fetchone()
    assert e["estado"] == "finalizada" and e["checkout_en"] is not None
    assert "Huéspedes en casa (0)" in cliente.get("/en-casa").get_data(as_text=True)
    r = cliente.post(f"/estancias/{estancia}/salida", follow_redirects=True)
    assert "no está en casa" in r.get_data(as_text=True)


def test_historial_por_rango_de_fechas_y_estado(cliente, bd):
    registrar_en_casa(cliente)
    estancia = bd.execute("SELECT id FROM estancias").fetchone()["id"]
    bd.execute("UPDATE estancias SET estado = 'finalizada', checkout_en = now(), fecha_ingreso = current_date - 40, "
               "fecha_salida_prevista = current_date - 38 WHERE id = %s", (estancia,))
    huesped = bd.execute("SELECT id FROM huespedes").fetchone()["id"]
    r = cliente.post("/registro", {**datos_registro(), "huesped_existente_id": str(huesped)})
    assert r.status_code == 302
    ficha = cliente.get(f"/huespedes/{huesped}").get_data(as_text=True)
    assert "2 estancias" in ficha
    desde = (hoy() - timedelta(days=5)).isoformat()
    assert "1 estancia " in cliente.get(f"/huespedes/{huesped}?desde={desde}").get_data(as_text=True)
    hace_60 = (hoy() - timedelta(days=60)).isoformat()
    assert "2 estancias" in cliente.get(f"/historial?desde={hace_60}").get_data(as_text=True)
    solo_finalizadas = cliente.get(f"/historial?desde={hace_60}&estado=finalizada").get_data(as_text=True)
    assert "1 estancia" in solo_finalizadas


def test_seed_demo_marca_todo_y_se_puede_borrar(app, bd):
    r = app.test_cli_runner().invoke(args=["seed-demo"])
    assert "Todo está marcado como DEMO" in r.output, r.output
    assert bd.execute("SELECT bool_and(es_demo) AS d FROM huespedes").fetchone()["d"] is True
    assert bd.execute("SELECT COUNT(*) AS n FROM estancias WHERE estado = 'en_casa'").fetchone()["n"] == 18
    app.test_cli_runner().invoke(args=["seed-demo", "--borrar"])
    assert bd.execute("SELECT COUNT(*) AS n FROM huespedes").fetchone()["n"] == 0
