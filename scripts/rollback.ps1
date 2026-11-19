# Plan de reversión (rollback) controlado sin pérdida de datos (HU-09).
# Vuelve a una etiqueta Git estable anterior y opcionalmente restaura un respaldo .dump.
#
# Uso:
#   .\scripts\rollback.ps1 -TagAnterior "v1.0.0" -Notas "Fallo crítico detectado tras despliegue"
#   .\scripts\rollback.ps1 -TagAnterior "v1.0.0" -Respaldo "backups\laureles_garden_2026-11-19_1800.dump"
param(
    [Parameter(Mandatory = $true)]
    [string]$TagAnterior,
    [string]$Respaldo = "",
    [string]$Notas = "Reversión a versión estable anterior",
    [string]$Responsable = $env:USERNAME
)

$ErrorActionPreference = "Stop"
Write-Host "=== [1/3] Cambiando código a la versión estable: $TagAnterior ==="
git fetch --tags
git checkout $TagAnterior
pip install -r requirements.txt

if ($Respaldo -ne "") {
    if (-not (Test-Path $Respaldo)) { throw "No se encontró el archivo de respaldo: $Respaldo" }
    Write-Host "=== [2/3] Restaurando respaldo de base de datos desde $Respaldo ==="
    $archivoEnv = Join-Path $PSScriptRoot "..\.env"
    $linea = Get-Content $archivoEnv | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
    $url = ($linea -split '=', 2)[1].Trim()
    pg_restore --clean --if-exists --no-owner --dbname "$url" "$Respaldo"
} else {
    Write-Host "=== [2/3] Conservando base de datos actual (migraciones retrocompatibles) ==="
}

Write-Host "=== [3/3] Registrando reversión en auditoría de despliegues ==="
try {
    flask --app app registrar-despliegue --version $TagAnterior --entorno produccion --resultado revertido --notas $Notas --por $Responsable
} catch {
    Write-Host "Aviso: la versión anterior no incluye el comando registrar-despliegue; registra el evento en CHANGELOG.md."
}

Write-Host "Reversión completada a $TagAnterior. Reinicia el servicio y verifica el funcionamiento."
