# Despliegue controlado en entorno Windows (HU-09).
# Ejecuta respaldo previo -> instalación de dependencias -> migraciones -> registro de despliegue.
#
# Uso:
#   .\scripts\desplegar.ps1 -Version "2.0.0" -Notas "Entrega 3: HU-05, HU-06, HU-07, HU-09, HU-10"
param(
    [string]$Version = "2.0.0",
    [string]$Entorno = "produccion",
    [string]$Notas = "Despliegue controlado",
    [string]$Responsable = $env:USERNAME
)

$ErrorActionPreference = "Stop"
Write-Host "=== [1/4] Creando respaldo preventivo de la base de datos ==="
& (Join-Path $PSScriptRoot "backup.ps1")

Write-Host "=== [2/4] Instalando/actualizando dependencias ==="
pip install -r requirements.txt

Write-Host "=== [3/4] Aplicando migraciones sin pérdida de datos ==="
flask --app app init-db

Write-Host "=== [4/4] Registrando versión publicada en la base de datos ==="
flask --app app registrar-despliegue --version $Version --entorno $Entorno --resultado exitoso --notas $Notas --por $Responsable

Write-Host "Despliegue v$Version completado. Ahora inicia el servidor y ejecuta scripts\smoke_test.py."
