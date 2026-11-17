# tools/instalar_inicio_automatico.ps1
# Registra o elimina la Tarea Programada de Windows para iniciar el Monitor de Ninfas
# automáticamente en modo Headless al encender o iniciar sesión en el Mini-PC.
param(
    [switch]$Desinstalar
)

$ErrorActionPreference = "Stop"
$NombreTarea = "MonitorDeNinfas_AutoStart"
$Raiz = Split-Path -Parent $PSScriptRoot
$ScriptOrquestador = Join-Path $PSScriptRoot "orquestador_operativo.ps1"

if ($Desinstalar) {
    if (Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false
        Write-Host "Tarea programada '$NombreTarea' eliminada correctamente." -ForegroundColor Yellow
    } else {
        Write-Host "La tarea '$NombreTarea' no estaba registrada." -ForegroundColor Cyan
    }
    exit 0
}

if (-not (Test-Path $ScriptOrquestador)) {
    throw "No se encontró el orquestador en: $ScriptOrquestador"
}

$Argumentos = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptOrquestador`" -Headless"
$Accion = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Argumentos -WorkingDirectory $Raiz
$Disparador = New-ScheduledTaskTrigger -AtLogOn
$Configuracion = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $NombreTarea `
    -Action $Accion `
    -Trigger $Disparador `
    -Settings $Configuracion `
    -Description "Inicia automáticamente el Monitor de Ninfas (FastAPI + YOLOv8 Headless) en el Mini-PC dedicado." `
    -Force | Out-Null

Write-Host "Tarea programada '$NombreTarea' instalada con éxito (Modo Headless con auto-reinicio)." -ForegroundColor Green
Write-Host "Para eliminarla en el futuro: powershell -File tools\instalar_inicio_automatico.ps1 -Desinstalar" -ForegroundColor Cyan
