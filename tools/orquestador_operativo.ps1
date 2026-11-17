# tools/orquestador_operativo.ps1
# Orquestador de Pre-vuelo, Migracion y Supervision para Monitor de Ninfas (Mini-PC Dedicado)
param(
    [switch]$Headless
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

if ($Headless) {
    $env:NINFAS_HEADLESS = "1"
}

Write-Host "=== [1/5] Verificando entorno Python y Contratos ===" -ForegroundColor Cyan
$PythonExe = Join-Path $Raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "No se encontro el entorno virtual en .venv. Ejecuta: py -3.11 -m venv .venv"
}
& $PythonExe tools/verificar_proyecto.py
if ($LASTEXITCODE -ne 0) {
    throw "Fallo la verificacion contractual del proyecto."
}

Write-Host "=== [2/5] Auditando archivo .env y Microsoft ODBC Driver 18 ===" -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Se creo .env a partir de .env.example." -ForegroundColor Yellow
}

$Odbc = Get-OdbcDriver | Where-Object { $_.Name -like "*ODBC Driver 18 for SQL Server*" }
$AzureConfigurado = (& $PythonExe -c "from dotenv import load_dotenv; from pathlib import Path; load_dotenv(Path('.env')); from modulos.base_datos import _cargar_config_azure; print('1' if _cargar_config_azure() else '0')").Trim()

if (-not $Odbc) {
    Write-Warning "Microsoft ODBC Driver 18 for SQL Server NO detectado. El monitor operara en modo local."
} else {
    Write-Host "[OK] Driver ODBC detectado: $($Odbc[0].Name)" -ForegroundColor Green
    if ($AzureConfigurado -eq "1") {
        Write-Host "=== [3/5] Aplicando migraciones idempotentes en Azure SQL ===" -ForegroundColor Cyan
        & $PythonExe tools/migrar_bd.py
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "No se pudieron aplicar migraciones en este momento. Se usara el respaldo local."
        }
    } else {
        Write-Host "=== [3/5] Azure SQL sin credenciales en .env (modo local activo) ===" -ForegroundColor Yellow
    }
}

Write-Host "=== [4/5] Iniciando API y Panel Web (FastAPI :8123) ===" -ForegroundColor Cyan
$ApiProc = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m uvicorn app.servidor:app --host 127.0.0.1 --port 8123" `
    -WorkingDirectory $Raiz `
    -PassThru -WindowStyle Hidden

try {
    $ApiLista = $false
    for ($i = 0; $i -lt 8; $i++) {
        Start-Sleep -Milliseconds 1000
        try {
            $Respuesta = Invoke-WebRequest -Uri "http://127.0.0.1:8123/api/health" -UseBasicParsing -TimeoutSec 3
            if ($Respuesta.StatusCode -eq 200) {
                $ApiLista = $true
                break
            }
        } catch {
            # Esperando a que Uvicorn termine de enlazar el puerto 8123
        }
    }

    if ($ApiLista) {
        Write-Host "[OK] Panel Web y API operativos en http://127.0.0.1:8123 (PID: $($ApiProc.Id))" -ForegroundColor Green
    } else {
        Write-Warning "La API tardo mas de lo esperado en responder en el puerto 8123."
    }

    Write-Host "=== [5/5] Iniciando Orquestador de Vision (main.py) ===" -ForegroundColor Cyan
    & $PythonExe main.py
}
finally {
    Write-Host "Deteniendo servidor FastAPI (PID: $($ApiProc.Id))..." -ForegroundColor Yellow
    if ($ApiProc -and -not $ApiProc.HasExited) {
        Stop-Process -Id $ApiProc.Id -Force
    }
}
