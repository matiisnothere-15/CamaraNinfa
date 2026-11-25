[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$')]
    [string]$ServerName,
    [ValidateRange(1024,65535)]
    [int]$Port = 8123,
    [switch]$PrepararClave,
    [switch]$Comprobar
)
$ErrorActionPreference = 'Stop'
if ($env:NINFAS_ADMIN_API_KEY -and $env:NINFAS_ADMIN_API_KEY.Length -lt 32) {
    throw 'La clave administrativa heredada de esta terminal es demasiado corta. Quita esa variable o configura al menos 32 caracteres antes de preparar .env.'
}
if ($env:NINFAS_ADMIN_API_KEY) {
    Write-Output 'Se usa la clave administrativa heredada de esta terminal, sin imprimirla.'
}
$apiRepoRoot = Split-Path -Parent $PSScriptRoot
$apiPython = Join-Path $apiRepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $apiPython)) { throw 'Falta .venv. Instala primero las dependencias del proyecto.' }
$envPath = Join-Path $apiRepoRoot '.env'
if (-not $Comprobar) {
    function Test-ApiDelProyecto {
        param($ApiProcess)
        $modulePattern = '\s+-m\s+uvicorn\s+app\.servidor:app(?:\s|$)'
        $pythonPattern = '^"?' + [regex]::Escape($apiPython) + '"?\s+-m\s+uvicorn\s+app\.servidor:app(?:\s|$)'
        $customAppDirPattern = '(?:^|\s)"?--app-dir(?=["=\s]|$)'
        if (-not $ApiProcess -or $ApiProcess.CommandLine -notmatch $modulePattern -or
            $ApiProcess.CommandLine -match $customAppDirPattern) { return $false }
        if ($ApiProcess.CommandLine -match $pythonPattern) { return $true }
        # El redirector de .venv en Windows mantiene un padre del proyecto y
        # ejecuta el servidor con el Python base. No confundirlo con otra copia.
        if (-not $ApiProcess.ParentProcessId -or -not $ApiProcess.CreationDate) { return $false }
        $apiParent = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $($ApiProcess.ParentProcessId)"
        return ($apiParent -and $apiParent.CreationDate -and
            [datetime]$apiParent.CreationDate -le [datetime]$ApiProcess.CreationDate -and
            $apiParent.CommandLine -match $pythonPattern -and
            $apiParent.CommandLine -notmatch $customAppDirPattern)
    }

    $apiListeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($apiListeners.Count -gt 0) {
        $apiOwnerIds = @($apiListeners.OwningProcess | Sort-Object -Unique)
        $apiExternalListeners = @($apiListeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') })
        $apiExisting = $null
        if ($apiOwnerIds.Count -eq 1 -and $apiExternalListeners.Count -eq 0) {
            $apiExisting = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $($apiOwnerIds[0])"
        }
        if (-not (Test-ApiDelProyecto $apiExisting)) {
            throw "El puerto $Port ya esta ocupado (PID: $($apiOwnerIds -join ', ')). No corresponde a la API loopback de este proyecto; revisa ese proceso."
        }
        try {
            $apiProbe = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" `
                -Headers @{ Host = $ServerName } -Method Get -UseBasicParsing `
                -TimeoutSec 5 -MaximumRedirection 0
            if ($apiProbe.StatusCode -ne 200) { throw 'Respuesta HTTP inesperada.' }
        } catch {
            throw "La API del proyecto ya ocupa el puerto $Port, pero no se pudo comprobar el acceso con Host '$ServerName'. Revisa la configuracion del servidor existente."
        }
        Write-Output "La API de este proyecto ya esta ejecutandose en 127.0.0.1:$Port (PID: $($apiOwnerIds[0]))."
        Write-Output "URL para Android: https://$ServerName"
        $global:LASTEXITCODE = 0
        return
    }
}
$prepareKey = if ($PrepararClave) { 'yes' } else { 'no' }
@'
import os
import secrets
import sys
from dotenv import load_dotenv, set_key

path, prepare = sys.argv[1:]
load_dotenv(path)
key = os.getenv("NINFAS_ADMIN_API_KEY", "")
if len(key) < 32:
    if prepare != "yes":
        print("Falta una clave administrativa de al menos 32 caracteres. Usa -PrepararClave.", file=sys.stderr)
        raise SystemExit(3)
    set_key(path, "NINFAS_ADMIN_API_KEY", secrets.token_urlsafe(32))
    print("Clave administrativa preparada en .env; su valor no se imprime.")
else:
    print("Clave administrativa configurada; no se modifica ni se imprime.")
'@ | & $apiPython - $envPath $prepareKey
if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar la configuracion de acceso Android.' }
Write-Output "URL esperada en Android: https://$ServerName"
Write-Output "API interna: http://127.0.0.1:$Port (requiere proxy HTTPS privado)."
if ($Comprobar) { return }
$previousHosts = $env:NINFAS_ALLOWED_HOSTS
Push-Location $apiRepoRoot
try {
    $env:NINFAS_ALLOWED_HOSTS = "127.0.0.1,localhost,[::1],$ServerName"
    & $apiPython -m uvicorn app.servidor:app --host 127.0.0.1 --port $Port `
        --proxy-headers --forwarded-allow-ips '127.0.0.1,::1'
    if ($LASTEXITCODE -ne 0) { throw "La API termino con codigo $LASTEXITCODE." }
} finally {
    $env:NINFAS_ALLOWED_HOSTS = $previousHosts
    Pop-Location
}
