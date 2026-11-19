"""HU-01 (registro) y HU-02 (almacenamiento atómico y cifrado)."""
from datetime import timedelta

from conftest import datos_registro

from app.formato import hoy


def contar(bd, tabla):
    return bd.execute(f"SELECT COUNT(*) AS n FROM {tabla}").fetchone()["n"]


def test_registro_valido_crea_huesped_y_estancia_en_casa(cliente, bd):
    r = cliente.post("/registro", datos_registro())
    assert r.status_code == 302 and "/huespedes/" in r.headers["Location"]
    e = bd.execute("SELECT * FROM estancias").fetchone()
    assert e["estado"] == "en_casa" and e["checkin_en"] is not None and e["habitacion"] == "101"
    ficha = cliente.get(r.headers["Location"]).get_data(as_text=True)
    assert "Huésped registrado." in ficha


def test_habitacion_es_opcional(cliente, bd):
    assert cliente.post("/registro", datos_registro(habitacion="")).status_code == 302
    assert bd.execute("SELECT habitacion FROM estancias").fetchone()["habitacion"] is None


def test_registro_invalido_muestra_errores_junto_al_campo_y_no_guarda(cliente, bd):
    r = cliente.post("/registro", datos_registro(nombres="", telefono="abc"))
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Este campo es obligatorio." in html
    assert "Escribe un teléfono válido" in html
    assert contar(bd, "huespedes") == 0 and contar(bd, "estancias") == 0


def test_salida_anterior_al_ingreso_se_rechaza(cliente, bd):
    r = cliente.post("/registro", datos_registro(fecha_salida_prevista=(hoy() - timedelta(days=1)).isoformat()))
    assert "La salida no puede ser anterior al ingreso." in r.get_data(as_text=True)
    assert contar(bd, "estancias") == 0


def test_sin_autorizacion_de_datos_no_registra(cliente, bd):
    r = cliente.post("/registro", datos_registro(acepta_datos=None))
    assert "Ley 1581" in r.get_data(as_text=True)
    assert contar(bd, "huespedes") == 0


def test_autorizacion_de_datos_queda_con_fecha(cliente, bd):
    cliente.post("/registro", datos_registro())
    h = bd.execute("SELECT acepta_tratamiento_datos, fecha_aceptacion_datos FROM huespedes").fetchone()
    assert h["acepta_tratamiento_datos"] is True and h["fecha_aceptacion_datos"] is not None


def test_documento_queda_cifrado_y_con_huella(cliente, bd):
    cliente.post("/registro", datos_registro())
    fila = bd.execute("SELECT * FROM huespedes").fetchone()
    texto_fila = " ".join(str(v) for v in fila.values())
    assert "1036555210" not in texto_fila
    assert "300 123 4567" not in texto_fila
    assert "jose@ejemplo.com" not in texto_fila
    assert fila["numero_documento_cifrado"].startswith("gAAAA")
    assert len(fila["documento_hash"]) == 64 and fila["documento_ultimos"] == "5210"


def test_documento_completo_solo_en_la_ficha(cliente, bd):
    cliente.post("/registro", datos_registro())
    huesped_id = bd.execute("SELECT id FROM huespedes").fetchone()["id"]
    ficha = cliente.get(f"/huespedes/{huesped_id}").get_data(as_text=True)
    assert "•••• 5210" in ficha and "1036555210" not in ficha
    completo = cliente.post(f"/huespedes/{huesped_id}/documento").get_data(as_text=True)
    assert "1036555210" in completo


def test_huesped_que_regresa_crea_nueva_estancia_sin_409(cliente, bd):
    cliente.post("/registro", datos_registro())
    bd.execute("UPDATE estancias SET estado = 'finalizada', checkout_en = now()")
    datos = datos_registro(numero_documento="1.036.555.210", telefono="+57 311 000 0000")
    r = cliente.post("/registro", datos)
    assert r.status_code == 200
    assert "ya está registrado a nombre de" in r.get_data(as_text=True)
    assert contar(bd, "estancias") == 1
    huesped_id = bd.execute("SELECT id FROM huespedes").fetchone()["id"]
    r = cliente.post("/registro", {**datos, "huesped_existente_id": str(huesped_id)})
    assert r.status_code == 302
    assert contar(bd, "huespedes") == 1 and contar(bd, "estancias") == 2


def test_huesped_en_casa_no_se_registra_dos_veces(cliente, bd):
    cliente.post("/registro", datos_registro())
    huesped_id = bd.execute("SELECT id FROM huespedes").fetchone()["id"]
    r = cliente.post("/registro", {**datos_registro(), "huesped_existente_id": str(huesped_id)})
    assert "ya está en casa" in r.get_data(as_text=True)
    assert contar(bd, "estancias") == 1


def test_verificar_documento_por_fetch(cliente):
    cliente.post("/registro", datos_registro())
    r = cliente.post_json("/huespedes/verificar-documento", {"tipo": "CC", "numero": "1036555210"})
    assert r.get_json()["existe"] is True and r.get_json()["en_casa"] is True
    r = cliente.post_json("/huespedes/verificar-documento", {"tipo": "CC", "numero": "999"})
    assert r.get_json()["existe"] is False


def test_transaccion_atomica_si_falla_la_estancia_no_queda_el_huesped(cliente, bd):
    bd.execute("ALTER TABLE estancias ADD CONSTRAINT prueba_rechazo CHECK (procedencia <> 'Bogotá')")
    try:
        try:
            cliente.post("/registro", datos_registro())
        except Exception:
            pass
        assert contar(bd, "huespedes") == 0 and contar(bd, "estancias") == 0
    finally:
        bd.execute("ALTER TABLE estancias DROP CONSTRAINT prueba_rechazo")


def test_fecha_de_ingreso_futura_se_rechaza_si_ya_llego(cliente, bd):
    r = cliente.post("/registro", datos_registro(
        estado_llegada="en_casa",
        fecha_ingreso=(hoy() + timedelta(days=3)).isoformat(),
        fecha_salida_prevista=(hoy() + timedelta(days=5)).isoformat(),
    ))
    assert "no puede ser futura" in r.get_data(as_text=True)
    assert contar(bd, "estancias") == 0


def test_zona_horaria_de_colombia(cliente, bd):
    cliente.post("/registro", datos_registro())
    fila = bd.execute("SELECT checkin_en, current_setting('TimeZone') AS zona, "
                      "pg_typeof(checkin_en)::text AS tipo FROM estancias").fetchone()
    assert fila["zona"] == "America/Bogota" and fila["tipo"] == "timestamp with time zone"
    assert fila["checkin_en"].utcoffset() == timedelta(hours=-5)


def test_existen_las_tablas_esperadas_de_la_entrega_3(bd):
    tablas = {f["table_name"] for f in bd.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'").fetchall()}
    assert tablas == {"huespedes", "estancias", "usuarios", "despliegues", "migraciones_aplicadas"}
