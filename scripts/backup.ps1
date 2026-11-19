# Respaldo de la base de datos de Laureles Garden con pg_dump.
#
# Uso (PowerShell, desde la carpeta del proyecto):
#     .\scripts\backup.ps1
#     .\scripts\backup.ps1 -Destino "D:\Respaldos"
#
# Lee DATABASE_URL del archivo .env (sin mostrarla) y crea un archivo
# backups\laureles_garden_AAAA-MM-DD_HHmm.dump (formato comprimido de pg_dump).
# Para restaurar:  pg_restore --clean --dbname "<DATABASE_URL>" archivo.dump
#
# IMPORTANTE: el respaldo contiene datos personales (cifrados, pero también nombres).
# Guárdalo en un lugar protegido y, por aparte, guarda una copia de .env:
# sin FERNET_KEY los datos cifrados del respaldo no se pueden leer.

param(
    [string]$Destino = (Join-Path $PSScriptRoot "..\backups")
)

$ErrorActionPreference = "Stop"
$archivoEnv = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $archivoEnv)) { throw "No se encontró el archivo .env" }

$linea = Get-Content $archivoEnv | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
if (-not $linea) { throw "El archivo .env no tiene DATABASE_URL" }
$url = ($linea -split '=', 2)[1].Trim()

# Busca pg_dump en el PATH o en la instalación estándar de PostgreSQL para Windows.
$pgDump = (Get-Command pg_dump -ErrorAction SilentlyContinue).Source
if (-not $pgDump) {
    $pgDump = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $pgDump) { throw "No se encontró pg_dump. Agrega 'C:\Program Files\PostgreSQL\<versión>\bin' al PATH." }

New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$fecha = Get-Date -Format "yyyy-MM-dd_HHmm"
$salida = Join-Path (Resolve-Path $Destino) "laureles_garden_$fecha.dump"

& $pgDump --format=custom --no-owner --file "$salida" --dbname "$url"
if ($LASTEXITCODE -ne 0) { throw "pg_dump terminó con error (código $LASTEXITCODE). Revisa DATABASE_URL." }

$tamano = [math]::Round((Get-Item $salida).Length / 1KB, 1)
Write-Host "Respaldo creado: $salida ($tamano KB)"
