"""HU-02: migración de la tabla original del Sprint 1 (Usuario_hostal) sin perder registros."""
import pytest


@pytest.fixture
def tabla_original(bd):
    """Recrea la tabla tal como la crea pgAdmin: con comillas y mayúsculas."""
    bd.execute('DROP TABLE IF EXISTS "Usuario_hostal"')
    bd.execute(
        'CREATE TABLE "Usuario_hostal" ('
        '"Id_Usuario_hostal" serial PRIMARY KEY, "Nombres" varchar(250) NOT NULL, "Apellidos" varchar(250) NOT NULL, '
        '"Tipo_Documento" varchar(50) NOT NULL, "Numero_Documento" varchar(50) NOT NULL, '
        '"Fecha_Arrendamiento" date NOT NULL, "Lugar_Provenida" varchar(250) NOT NULL, '
        '"Lugar_Partida" varchar(250) NOT NULL, "fecha_Checkout" timestamp NULL)'
    )
    filas = [
        ("Ana", "Gómez", "Cédula de ciudadanía", "1020304050", "2026-09-01", "Bogotá", "Cali", "2026-09-03 11:00"),
        ("Tom", "Müller", "Pasaporte", "C01X00T47", "2026-09-10", "Berlín", "Salento", None),
        ("Ana", "Gómez", "Cédula de ciudadanía", "1020304050", "2026-10-01", "Cali", "Bogotá", "2026-10-02 10:00"),
    ]
    for f in filas:
        bd.execute(
            'INSERT INTO "Usuario_hostal" ("Nombres", "Apellidos", "Tipo_Documento", "Numero_Documento", '
            '"Fecha_Arrendamiento", "Lugar_Provenida", "Lugar_Partida", "fecha_Checkout") '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            f,
        )
    yield
    bd.execute('DROP TABLE IF EXISTS "Usuario_hostal"')


def test_migracion_traslada_sin_perder_y_sin_tocar_la_original(app, bd, tabla_original):
    runner = app.test_cli_runner()
    r = runner.invoke(args=["migrar-original"])
    assert "3 registros leídos" in r.output and "2 huéspedes nuevos" in r.output and "3 estancias" in r.output
    assert bd.execute("SELECT COUNT(*) AS n FROM huespedes").fetchone()["n"] == 2
    assert bd.execute("SELECT COUNT(*) AS n FROM estancias").fetchone()["n"] == 3
    ana = bd.execute("SELECT * FROM huespedes WHERE nombres = 'Ana'").fetchone()
    assert ana["tipo_documento"] == "CC" and "1020304050" not in ana["numero_documento_cifrado"]
    tom = bd.execute("SELECT tipo_documento FROM huespedes WHERE nombres = 'Tom'").fetchone()
    assert tom["tipo_documento"] == "PA"
    assert bd.execute('SELECT COUNT(*) AS n FROM "Usuario_hostal"').fetchone()["n"] == 3
    r = runner.invoke(args=["migrar-original"])
    assert "3 ya migrados antes" in r.output
    assert bd.execute("SELECT COUNT(*) AS n FROM estancias").fetchone()["n"] == 3


def test_sin_tabla_original_no_hace_nada(app):
    r = app.test_cli_runner().invoke(args=["migrar-original"])
    assert "No se encontró la tabla Usuario_hostal" in r.output


def test_init_db_no_toca_una_base_con_tablas_del_alcance_retirado(app, bd):
    bd.execute("CREATE TABLE pagos (id serial PRIMARY KEY, monto numeric)")
    bd.execute("INSERT INTO pagos (monto) VALUES (50000)")
    bd.execute("ALTER TABLE estancias RENAME COLUMN habitacion TO habitacion_vieja")
    try:
        r = app.test_cli_runner().invoke(args=["init-db"])
        assert r.exit_code != 0 and "funcionalidades retiradas (pagos)" in r.output
        assert bd.execute("SELECT COUNT(*) AS n FROM pagos").fetchone()["n"] == 1
        bd.execute("ALTER TABLE estancias RENAME COLUMN habitacion_vieja TO habitacion")
        r = app.test_cli_runner().invoke(args=["init-db"])
        assert r.exit_code == 0 and "No se usan ni se modifican" in r.output
        assert bd.execute("SELECT COUNT(*) AS n FROM pagos").fetchone()["n"] == 1
    finally:
        sin_restaurar = bd.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'estancias' "
            "AND column_name = 'habitacion_vieja'"
        ).fetchone()
        if sin_restaurar:
            bd.execute("ALTER TABLE estancias RENAME COLUMN habitacion_vieja TO habitacion")
        bd.execute("DROP TABLE pagos")
