"""Genera SECRET_KEY, FERNET_KEY y HMAC_KEY y las escribe en el archivo .env.

    py scripts\\generar_claves.py

- Las claves NO se muestran en pantalla: se escriben directamente en .env.
- Solo completa las claves que falten o que tengan el valor de ejemplo "CAMBIAR...".
- Nunca reemplaza una clave existente: si se cambia FERNET_KEY o HMAC_KEY,
  los datos ya cifrados dejarían de poder leerse y buscarse.
"""
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ENV = Path(__file__).resolve().parent.parent / ".env"
EJEMPLO = ENV.with_name(".env.example")

GENERADORES = {
    "SECRET_KEY": lambda: secrets.token_urlsafe(48),
    "FERNET_KEY": lambda: Fernet.generate_key().decode("ascii"),
    "HMAC_KEY": lambda: secrets.token_urlsafe(48),
}


def main():
    if not ENV.exists():
        if not EJEMPLO.exists():
            sys.exit("No existe .env ni .env.example en la carpeta del proyecto.")
        ENV.write_text(EJEMPLO.read_text(encoding="utf-8"), encoding="utf-8")
        print("Se creó .env a partir de .env.example. Recuerda ajustar DATABASE_URL.")

    lineas = ENV.read_text(encoding="utf-8").splitlines()
    presentes = {}
    for i, linea in enumerate(lineas):
        nombre, _, valor = linea.partition("=")
        if nombre.strip() in GENERADORES:
            presentes[nombre.strip()] = (i, valor.strip())

    generadas, conservadas = [], []
    for nombre, generar in GENERADORES.items():
        indice, valor = presentes.get(nombre, (None, ""))
        if valor and not valor.upper().startswith("CAMBIAR"):
            conservadas.append(nombre)
            continue
        nueva = f"{nombre}={generar()}"
        if indice is None:
            lineas.append(nueva)
        else:
            lineas[indice] = nueva
        generadas.append(nombre)

    ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    if generadas:
        print("Claves generadas y guardadas en .env: " + ", ".join(generadas))
    if conservadas:
        print("Claves que ya existían y NO se cambiaron: " + ", ".join(conservadas))
    print("Guarda una copia de .env en un lugar seguro: sin FERNET_KEY no se pueden leer los datos cifrados.")


if __name__ == "__main__":
    main()
