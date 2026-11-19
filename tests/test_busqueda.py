"""HU-05: Búsqueda de huéspedes por nombre o número de documento."""
from conftest import datos_registro


def _registrar(cliente, **cambios):
    r = cliente.post("/registro", datos_registro(**cambios))
    assert r.status_code == 302


def test_buscar_por_nombre_sin_tildes_ni_mayusculas(cliente):
    _registrar(cliente, nombres="José", apellidos="Peña Ruiz", numero_documento="1036555210")
    _registrar(cliente, nombres="Ana María", apellidos="Gómez", numero_documento="99887766")

    html = cliente.get("/buscar?q=jose+pena").get_data(as_text=True)
    assert "José Peña Ruiz" in html
    assert "Ana María Gómez" not in html
    assert "1 huésped encontrado" in html

    html2 = cliente.get("/buscar?q=gomez").get_data(as_text=True)
    assert "Ana María Gómez" in html2


def test_buscar_por_numero_de_documento_con_o_sin_formato(cliente):
    _registrar(cliente, nombres="Lukas", apellidos="Müller", tipo_documento="PA", numero_documento="C01X00T47")
    _registrar(cliente, nombres="Camila", apellidos="Ospina", numero_documento="1020304050")

    html = cliente.get("/buscar?q=1.020.304.050").get_data(as_text=True)
    assert "Camila Ospina" in html
    assert "•••• 4050" in html
    assert "1020304050" not in html

    html_pas = cliente.get("/buscar?q=c01x00t47").get_data(as_text=True)
    assert "Lukas Müller" in html_pas


def test_busqueda_sin_coincidencias_muestra_mensaje_claro(cliente):
    _registrar(cliente)
    html = cliente.get("/buscar?q=NoExisteNadie123").get_data(as_text=True)
    assert "No existen resultados" in html


def test_resultado_permite_abrir_ficha_completa(cliente, bd):
    _registrar(cliente, nombres="Sofía", apellidos="Zapata", numero_documento="55443322")
    huesped_id = bd.execute("SELECT id FROM huespedes").fetchone()["id"]

    html = cliente.get("/buscar?q=Sofía").get_data(as_text=True)
    assert f"/huespedes/{huesped_id}" in html

    ficha = cliente.get(f"/huespedes/{huesped_id}").get_data(as_text=True)
    assert "Sofía Zapata" in ficha and "Datos personales" in ficha
