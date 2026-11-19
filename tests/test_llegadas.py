"""HU-06: Confirmación de llegada del huésped y modificación en caso de error."""
from datetime import timedelta

from conftest import datos_registro

from app.formato import hoy


def test_registrar_pendiente_de_llegada_con_fecha_futura(cliente, bd):
    r = cliente.post("/registro", datos_registro(
        estado_llegada="pendiente",
        fecha_ingreso=(hoy() + timedelta(days=2)).isoformat(),
        fecha_salida_prevista=(hoy() + timedelta(days=5)).isoformat(),
    ))
    assert r.status_code == 302
    e = bd.execute("SELECT estado, checkin_en FROM estancias").fetchone()
    assert e["estado"] == "pendiente" and e["checkin_en"] is None

    html_llegadas = cliente.get("/llegadas").get_data(as_text=True)
    assert "José Peña Ruiz" in html_llegadas and "Pendiente de llegada" in html_llegadas
    assert "Huéspedes en casa (0)" in cliente.get("/en-casa").get_data(as_text=True)


def test_confirmar_llegada_actualiza_estado_y_bd(cliente, bd):
    cliente.post("/registro", datos_registro(estado_llegada="pendiente"))
    estancia_id = bd.execute("SELECT id FROM estancias").fetchone()["id"]

    r = cliente.post(f"/estancias/{estancia_id}/confirmar-llegada", follow_redirects=True)
    assert "Llegada confirmada" in r.get_data(as_text=True)

    e = bd.execute("SELECT estado, checkin_en, actualizado_en FROM estancias WHERE id = %s", (estancia_id,)).fetchone()
    assert e["estado"] == "en_casa" and e["checkin_en"] is not None and e["actualizado_en"] is not None

    assert "Huéspedes en casa (1)" in cliente.get("/en-casa").get_data(as_text=True)
    assert "Pendientes de llegada (0)" in cliente.get("/llegadas").get_data(as_text=True)


def test_modificar_estado_de_llegada_por_error(cliente, bd):
    cliente.post("/registro", datos_registro(estado_llegada="en_casa"))
    estancia_id = bd.execute("SELECT id FROM estancias").fetchone()["id"]

    r = cliente.post(f"/estancias/{estancia_id}/marcar-pendiente", follow_redirects=True)
    assert "Estado corregido a pendiente de llegada" in r.get_data(as_text=True)

    e = bd.execute("SELECT estado, checkin_en FROM estancias WHERE id = %s", (estancia_id,)).fetchone()
    assert e["estado"] == "pendiente" and e["checkin_en"] is None
    assert "Pendientes de llegada (1)" in cliente.get("/llegadas").get_data(as_text=True)


def test_estado_actualizado_visible_en_ficha_e_historial(cliente, bd):
    cliente.post("/registro", datos_registro(estado_llegada="pendiente"))
    huesped_id = bd.execute("SELECT id FROM huespedes").fetchone()["id"]

    ficha = cliente.get(f"/huespedes/{huesped_id}").get_data(as_text=True)
    assert "Pendiente de llegada" in ficha and "Confirmar llegada" in ficha

    historial = cliente.get("/historial?estado=pendiente").get_data(as_text=True)
    assert "1 estancia" in historial and "José Peña Ruiz" in historial
