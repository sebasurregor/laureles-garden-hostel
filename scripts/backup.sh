#!/usr/bin/env bash
# Respaldo de PostgreSQL para Linux/macOS (HU-09).
# Uso: ./scripts/backup.sh [carpeta_destino]
set -euo pipefail

DESTINO="${1:-backups}"
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "Error: DATABASE_URL no está definida en el entorno ni en .env" >&2
    exit 1
fi

mkdir -p "$DESTINO"
FECHA="$(date +%Y-%m-%d_%H%M)"
SALIDA="${DESTINO}/laureles_garden_${FECHA}.dump"

pg_dump --format=custom --no-owner --file "$SALIDA" --dbname "$DATABASE_URL"
echo "Respaldo creado: $SALIDA"
