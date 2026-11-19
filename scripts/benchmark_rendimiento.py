"""Benchmark reproducible de rendimiento y concurrencia (HU-10).

Compara las vistas críticas del sistema en dos escenarios sobre los mismos datos:
  - ANTES (sin optimizaciones): sin pool de conexiones (1 conexión por petición)
    y sin los índices de la migración 003.
  - DESPUÉS (optimizado): con pool de conexiones psycopg_pool y los índices de 003.

Además ejecuta una prueba de concurrencia con varios usuarios simultáneos y genera
un reporte en Markdown en `docs/reporte_rendimiento.md` listo para la sustentación.

Uso (se ejecuta sobre TEST_DATABASE_URL para no tocar datos reales):
    py scripts\benchmark_rendimiento.py --volumen 3000 --iteraciones 25 --hilos 8
"""
import argparse
import os
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import create_app
from app.cifrado import hash_contrasena
from app.db import aplicar_migraciones, cerrar_pool, conectar

INDICES_003 = [
    "idx_huespedes_nombre_busqueda_prefix",
    "idx_huespedes_apellidos_nombres",
    "idx_huespedes_nombre_busqueda_trgm",
    "idx_estancias_en_casa_salida",
    "idx_estancias_pendientes_ingreso",
    "idx_estancias_fecha_id_desc",
    "idx_estancias_estado_fecha_id",
    "idx_estancias_huesped_fecha",
]


def _base_segura(url):
    nombre = urlparse(url).path.lstrip("/").lower()
    return bool(url) and url != os.getenv("DATABASE_URL") and ("test" in nombre or "prueba" in nombre)


def _extraer_csrf(html):
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


def _cliente_autenticado(app, usuario, clave):
    cliente = app.test_client()
    token = _extraer_csrf(cliente.get("/login").get_data(as_text=True))
    r = cliente.post("/login", data={"csrf_token": token, "usuario": usuario, "contrasena": clave})
    assert r.status_code == 302, "No fue posible iniciar sesión para el benchmark."
    return cliente


def _medir_secuencial(app, usuario, clave, rutas, iteraciones):
    cliente = _cliente_autenticado(app, usuario, clave)
    for _, ruta in rutas:
        cliente.get(ruta)

    resultados = {}
    for nombre, ruta in rutas:
        tiempos = []
        for _ in range(iteraciones):
            t0 = time.perf_counter()
            r = cliente.get(ruta)
            ms = (time.perf_counter() - t0) * 1000.0
            assert r.status_code == 200, f"Error HTTP {r.status_code} en {ruta}"
            tiempos.append(ms)
        tiempos_ord = sorted(tiempos)
        p95_idx = min(int(len(tiempos_ord) * 0.95), len(tiempos_ord) - 1)
        resultados[nombre] = {
            "ruta": ruta,
            "promedio": statistics.mean(tiempos),
            "p95": tiempos_ord[p95_idx],
            "max": max(tiempos),
        }
    return resultados


def _medir_concurrencia(app, usuario, clave, rutas, hilos, repeticiones):
    def trabajador(indice):
        cliente = _cliente_autenticado(app, usuario, clave)
        muestras = []
        for i in range(repeticiones):
            _, ruta = rutas[(indice + i) % len(rutas)]
            t0 = time.perf_counter()
            r = cliente.get(ruta)
            ms = (time.perf_counter() - t0) * 1000.0
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} en {ruta}")
            muestras.append(ms)
        return muestras

    tiempos = []
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        for parcial in pool.map(trabajador, range(hilos)):
            tiempos.extend(parcial)
    tiempos.sort()
    p95_idx = min(int(len(tiempos) * 0.95), len(tiempos) - 1)
    return {
        "peticiones": len(tiempos),
        "promedio": statistics.mean(tiempos),
        "p95": tiempos[p95_idx],
        "max": max(tiempos),
    }


def main():
    load_dotenv(RAIZ / ".env", override=False)
    parser = argparse.ArgumentParser(description="Benchmark antes/después (HU-10)")
    parser.add_argument("--volumen", type=int, default=3000, help="Huéspedes demo extra a cargar (default 3000)")
    parser.add_argument("--iteraciones", type=int, default=20, help="Iteraciones por ruta (default 20)")
    parser.add_argument("--hilos", type=int, default=8, help="Usuarios concurrentes simulados (default 8)")
    args = parser.parse_args()

    url_db = os.getenv("TEST_DATABASE_URL", "")
    if not url_db or "CAMBIAR" in url_db.upper() or not _base_segura(url_db):
        sys.exit(
            "Define TEST_DATABASE_URL en .env apuntando a una base distinta de DATABASE_URL "
            "cuyo nombre contenga 'test' o 'prueba'."
        )

    print(f"[1/5] Preparando base de pruebas con {args.volumen} huéspedes extra...")
    with conectar(url_db) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        aplicar_migraciones(conn)

    app_base = create_app({"DATABASE_URL": url_db, "USAR_POOL_CONEXIONES": False})
    runner = app_base.test_cli_runner()
    res_seed = runner.invoke(args=["seed-demo", "--volumen", str(args.volumen)])
    assert res_seed.exit_code == 0, res_seed.output

    usuario_bench, clave_bench = "bench_user", "ClaveBench123!"
    with conectar(url_db) as conn:
        conn.execute(
            "INSERT INTO usuarios (usuario, nombre_completo, rol, password_hash) VALUES (%s, %s, 'admin', %s)",
            (usuario_bench, "Usuario Benchmark", hash_contrasena(clave_bench)),
        )
        huesped_id = conn.execute("SELECT id FROM huespedes ORDER BY id LIMIT 1").fetchone()["id"]
        conn.execute("ANALYZE")

    rutas = [
        ("En casa", "/en-casa"),
        ("Llegadas pendientes", "/llegadas"),
        ("Búsqueda por nombre", "/buscar?q=ana"),
        ("Búsqueda por documento", "/buscar?q=DX0000010"),
        ("Historial", "/historial"),
        ("Ficha de huésped", f"/huespedes/{huesped_id}"),
    ]

    print("[2/5] Midiendo escenario ANTES (sin pool de conexiones ni índices de migración 003)...")
    with conectar(url_db) as conn:
        for idx in INDICES_003:
            conn.execute(f"DROP INDEX IF EXISTS {idx}")
        conn.execute("ANALYZE")

    app_antes = create_app({"DATABASE_URL": url_db, "USAR_POOL_CONEXIONES": False})
    sec_antes = _medir_secuencial(app_antes, usuario_bench, clave_bench, rutas, args.iteraciones)
    conc_antes = _medir_concurrencia(app_antes, usuario_bench, clave_bench, rutas, args.hilos, 6)

    print("[3/5] Aplicando índices de migración 003 y activando pool de conexiones...")
    sql_003 = (RAIZ / "migrations" / "003_indices_rendimiento.sql").read_text(encoding="utf-8")
    with conectar(url_db) as conn:
        conn.execute(sql_003)
        conn.execute("ANALYZE")

    print("[4/5] Midiendo escenario DESPUÉS (con pool de conexiones + índices 003)...")
    app_despues = create_app({
        "DATABASE_URL": url_db,
        "USAR_POOL_CONEXIONES": True,
        "DB_POOL_MIN": 2,
        "DB_POOL_MAX": max(args.hilos, 8),
    })
    try:
        sec_despues = _medir_secuencial(app_despues, usuario_bench, clave_bench, rutas, args.iteraciones)
        conc_despues = _medir_concurrencia(app_despues, usuario_bench, clave_bench, rutas, args.hilos, 6)
    finally:
        cerrar_pool(app_despues)

    print("[5/5] Generando reporte en docs/reporte_rendimiento.md...")
    lineas = [
        "# Reporte de optimización de rendimiento (HU-10)",
        "",
        f"- **Fecha:** {datetime.now():%Y-%m-%d %H:%M}",
        f"- **Volumen probado:** {args.volumen + 73} huéspedes demo",
        f"- **Iteraciones por vista:** {args.iteraciones}",
        f"- **Usuarios simultáneos (concurrencia):** {args.hilos}",
        "",
        "## 1. Comparativa por vista (tiempos en milisegundos)",
        "",
        "| Vista | Antes (prom) | Después (prom) | Mejora | Después (p95) | Cumple < 2000 ms |",
        "|---|---:|---:|---:|---:|:---:|",
    ]
    for nombre, _ in rutas:
        a = sec_antes[nombre]["promedio"]
        d = sec_despues[nombre]["promedio"]
        p95 = sec_despues[nombre]["p95"]
        mejora = ((a - d) / a * 100.0) if a > 0 else 0.0
        cumple = "Sí" if p95 < 2000 else "No"
        lineas.append(f"| {nombre} | {a:.1f} ms | {d:.1f} ms | {mejora:+.1f}% | {p95:.1f} ms | {cumple} |")

    mejora_conc = (
        (conc_antes["promedio"] - conc_despues["promedio"]) / conc_antes["promedio"] * 100.0
        if conc_antes["promedio"] > 0
        else 0.0
    )
    lineas.extend([
        "",
        "## 2. Prueba bajo concurrencia simultánea",
        "",
        "| Escenario | Peticiones | Promedio | p95 | Máximo |",
        "|---|---:|---:|---:|---:|",
        f"| Antes (sin pool ni índices 003) | {conc_antes['peticiones']} | {conc_antes['promedio']:.1f} ms | {conc_antes['p95']:.1f} ms | {conc_antes['max']:.1f} ms |",
        f"| Después (pool + índices 003) | {conc_despues['peticiones']} | {conc_despues['promedio']:.1f} ms | {conc_despues['p95']:.1f} ms | {conc_despues['max']:.1f} ms |",
        "",
        f"**Reducción promedio bajo concurrencia:** {mejora_conc:+.1f}%",
        "",
    ])
    reporte = "\n".join(lineas)
    destino = RAIZ / "docs" / "reporte_rendimiento.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(reporte, encoding="utf-8")
    print("\n" + reporte)


if __name__ == "__main__":
    main()
