[CmdletBinding()]
param(
    [string[]]$Task = @('assembleDebug', 'testDebugUnitTest', 'lintDebug'),
    [string]$SdkRoot = '',
    [string]$JavaHome = '',
    [string]$GradleHome = ''
)
$ErrorActionPreference = 'Stop'

function Repair-AndroidTransformCache([string]$CacheHome) {
    # Workaround Gradle/gradle#31438: Windows puede mantener abierto un output
    # hasta terminar el daemon. Solo promover outputs completos, sin sobrescribir.
    $cacheHomePath = [IO.Path]::GetFullPath($CacheHome).TrimEnd('\')
    $transformPath = Join-Path $cacheHomePath 'caches\8.14.3\transforms'
    if (-not (Test-Path -LiteralPath $transformPath)) { return 0 }
    $repaired = 0
    Get-ChildItem -LiteralPath $transformPath -Directory | Where-Object {
        $_.Name -match '^[0-9a-f]{32}-[0-9a-f-]{36}$' -and
        -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint)
    } | ForEach-Object {
        $cacheKey = $_.Name.Substring(0,32)
        $targetPath = [IO.Path]::GetFullPath((Join-Path $transformPath $cacheKey))
        if (-not $targetPath.StartsWith($cacheHomePath + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Destino de cache fuera del directorio de Gradle.'
        }
        if (-not (Test-Path -LiteralPath $targetPath) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName 'metadata.bin')) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName 'transformed'))) {
            Rename-Item -LiteralPath $_.FullName -NewName $cacheKey
            $repaired++
        }
    }
    return $repaired
}

$androidSourceRoot = $PSScriptRoot
$androidRepoRoot = Split-Path -Parent $androidSourceRoot
if (-not $JavaHome) {
    $JavaHome = $env:JAVA_HOME
    if (-not $JavaHome) { $JavaHome = Join-Path $env:ProgramFiles 'Android\Android Studio\jbr' }
}
if (-not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\java.exe'))) {
    throw 'No se encontro Java. Indica -JavaHome con la carpeta JDK 17 o posterior.'
}
if (-not $SdkRoot) {
    $SdkRoot = $env:ANDROID_HOME
    if (-not $SdkRoot) { $SdkRoot = Join-Path $env:USERPROFILE 'AppData\Local\Android\Sdk' }
}
if (-not (Test-Path -LiteralPath (Join-Path $SdkRoot 'platforms\android-36\android.jar'))) {
    throw 'Falta Android SDK 36. Instálalo desde Android Studio o indica -SdkRoot.'
}
if (-not $GradleHome) { $GradleHome = Join-Path $androidRepoRoot '.cache\android-gradle-home' }
$androidCacheRoot = Join-Path $androidRepoRoot '.cache'
$signingRoot = Join-Path $androidCacheRoot 'android-signing'
New-Item -ItemType Directory -Force -Path $GradleHome,$signingRoot | Out-Null
$keystore = Join-Path $signingRoot 'debug.keystore'
if (-not (Test-Path -LiteralPath $keystore)) {
    & (Join-Path $JavaHome 'bin\keytool.exe') -genkeypair -keystore $keystore `
        -storepass android -keypass android -alias androiddebugkey -keyalg RSA `
        -keysize 2048 -validity 10000 -dname 'CN=Android Debug,O=Android,C=CL'
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la firma local de prueba.' }
}
$sdkProperty = 'sdk.dir=' + (([IO.Path]::GetFullPath($SdkRoot) -replace '\\', '/') -replace ':', '\:')
Set-Content -LiteralPath (Join-Path $androidSourceRoot 'local.properties') -Value $sdkProperty -Encoding ascii
$oldEnvironment = @{}
foreach ($name in @('JAVA_HOME','ANDROID_HOME','ANDROID_SDK_ROOT','GRADLE_USER_HOME','ANDROID_USER_HOME')) {
    $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    $env:JAVA_HOME = $JavaHome
    $env:ANDROID_HOME = $SdkRoot
    $env:ANDROID_SDK_ROOT = $SdkRoot
    $env:GRADLE_USER_HOME = [IO.Path]::GetFullPath($GradleHome)
    $env:ANDROID_USER_HOME = Join-Path $androidCacheRoot 'android-user-home'
    $installedGradle = Get-ChildItem -LiteralPath (Join-Path $env:USERPROFILE '.gradle\wrapper\dists\gradle-8.14.3-bin') `
        -Filter gradle.bat -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
    if (-not $installedGradle) { $installedGradle = Join-Path $androidSourceRoot 'gradlew.bat' }
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        & $installedGradle -p $androidSourceRoot @Task --no-daemon --console plain --max-workers 2
        $buildExitCode = $LASTEXITCODE
        if ($buildExitCode -eq 0) { break }
        if ($attempt -ge 2 -or (Repair-AndroidTransformCache $env:GRADLE_USER_HOME) -eq 0) { break }
        Write-Output 'Cache de transformaciones Windows completada; se repite la compilacion.'
    }
    if ($buildExitCode -ne 0) { throw "Gradle termino con codigo $buildExitCode." }
} finally {
    foreach ($name in $oldEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], 'Process')
    }
}
