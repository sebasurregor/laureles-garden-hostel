"""Prueba rápida posterior al despliegue (Smoke Test · HU-09).

Verifica contra un servidor en ejecución (local o HTTPS en producción):
  1. Que /health responda 200 OK y la base de datos esté conectada.
  2. Que las rutas con datos de huéspedes bloqueen acceso sin sesión (302 a /login).
  3. Que el inicio de sesión funcione con credenciales autorizadas.
  4. Que las vistas críticas (/en-casa, /llegadas, /buscar, /historial, /registro)
     respondan 200 OK en menos de 2 segundos.
  5. Que el cierre de sesión revoque el acceso correctamente.

Uso:
    py scripts\smoke_test.py --url https://tu-app.onrender.com --usuario admin --password TuClave
    py scripts\smoke_test.py --url http://127.0.0.1:8000 --usuario admin --password TuClave --permitir-http
"""
import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _extraer_csrf(html):
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if not m:
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else ""


def _abrir(opener, url, data=None):
    req = urllib.request.Request(url, data=data)
    inicio = time.perf_counter()
    try:
        with opener.open(req, timeout=15) as resp:
            cuerpo = resp.read().decode("utf-8", errors="replace")
            return resp.status, dict(resp.headers), cuerpo, (time.perf_counter() - inicio) * 1000
    except urllib.error.HTTPError as err:
        cuerpo = err.read().decode("utf-8", errors="replace")
        return err.code, dict(err.headers), cuerpo, (time.perf_counter() - inicio) * 1000


def main():
    parser = argparse.ArgumentParser(description="Verificación post-despliegue (HU-09)")
    parser.add_argument("--url", required=True, help="URL base, ej. https://laureles-garden.onrender.com")
    parser.add_argument("--usuario", required=True, help="Usuario autorizado")
    parser.add_argument("--password", required=True, help="Contraseña del usuario")
    parser.add_argument("--permitir-http", action="store_true", help="Permite pruebas locales sobre HTTP")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    fallos = 0

    def revisar(nombre, condicion, detalle=""):
        nonlocal fallos
        etiqueta = "PASS" if condicion else "FAIL"
        print(f"[{etiqueta}] {nombre}" + (f" · {detalle}" if detalle else ""))
        if not condicion:
            fallos += 1

    if not args.permitir_http:
        revisar("Conexión segura HTTPS", base.startswith("https://"), base)

    opener_simple = urllib.request.build_opener(SinRedireccion())
    estado, _, cuerpo, ms = _abrir(opener_simple, f"{base}/health")
    salud = {}
    try:
        salud = json.loads(cuerpo)
    except json.JSONDecodeError:
        pass
    revisar(
        "Salud del sistema (/health)",
        estado == 200 and salud.get("status") == "ok" and salud.get("base_datos") == "conectada",
        f"HTTP {estado}, v{salud.get('version', '?')}, {ms:.0f} ms",
    )

    estado, cabeceras, _, _ = _abrir(opener_simple, f"{base}/en-casa")
    ubicacion = cabeceras.get("Location") or cabeceras.get("location") or ""
    revisar(
        "Bloqueo de /en-casa sin sesión",
        estado in (301, 302) and "/login" in ubicacion,
        f"HTTP {estado} -> {ubicacion}",
    )

    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    estado, _, html_login, _ = _abrir(opener, f"{base}/login")
    token = _extraer_csrf(html_login)
    revisar("Formulario de login con CSRF", estado == 200 and bool(token), f"HTTP {estado}")

    payload = urllib.parse.urlencode(
        {"csrf_token": token, "usuario": args.usuario, "contrasena": args.password}
    ).encode("utf-8")
    estado, _, html_post, ms = _abrir(opener, f"{base}/login", data=payload)
    revisar(
        "Inicio de sesión autorizado",
        estado == 200 and "Huéspedes en casa" in html_post,
        f"HTTP {estado}, {ms:.0f} ms",
    )

    for ruta in ("/en-casa", "/llegadas", "/buscar?q=ana", "/historial", "/registro"):
        estado, _, html_vista, ms = _abrir(opener, f"{base}{ruta}")
        revisar(f"Vista {ruta}", estado == 200 and ms < 2000, f"HTTP {estado}, {ms:.0f} ms")
        token = _extraer_csrf(html_vista) or token

    payload_logout = urllib.parse.urlencode({"csrf_token": token}).encode("utf-8")
    estado, _, html_out, _ = _abrir(opener, f"{base}/logout", data=payload_logout)
    revisar(
        "Cierre de sesión",
        estado == 200 and ("Iniciar sesión" in html_out or "Acceso a recepción" in html_out),
        f"HTTP {estado}",
    )

    opener_sin_redir = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookies), SinRedireccion()
    )
    estado, _, _, _ = _abrir(opener_sin_redir, f"{base}/en-casa")
    revisar("Acceso bloqueado tras cerrar sesión", estado in (301, 302), f"HTTP {estado}")

    print("-" * 60)
    if fallos:
        print(f"RESULTADO: {fallos} verificación(es) fallaron.")
        sys.exit(1)
    print("RESULTADO: Todas las verificaciones post-despliegue pasaron correctamente.")


if __name__ == "__main__":
    main()
