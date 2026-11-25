import os
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TEMPORALES = RAIZ / ".cache/test-temp"


def _entorno_temporal():
    TEMPORALES.mkdir(parents=True, exist_ok=True)
    return dict(os.environ, TEMP=str(TEMPORALES), TMP=str(TEMPORALES))


def _literal_ps(valor):
    return "'" + str(valor).replace("'", "''") + "'"


class AndroidContractTests(unittest.TestCase):
    def test_backup_y_transferencia_excluyen_preferencias_y_bases_de_datos(self):
        reglas = ET.parse(
            RAIZ / "android/app/src/main/res/xml/data_extraction_rules.xml"
        ).getroot()
        for destino in ("cloud-backup", "device-transfer"):
            with self.subTest(destino=destino):
                excluidos = {
                    (elemento.get("domain"), elemento.get("path"))
                    for elemento in reglas.findall(f"{destino}/exclude")
                }
                for dominio in ("root", "file", "database", "sharedpref", "external",
                                "device_root", "device_file", "device_database", "device_sharedpref"):
                    self.assertIn((dominio, "."), excluidos)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Requiere PowerShell Windows")
    def test_clave_heredada_corta_se_rechaza_antes_de_preparar_archivo(self):
        entorno = _entorno_temporal()
        with tempfile.TemporaryDirectory(dir=TEMPORALES) as temporal:
            raiz = Path(temporal)
            (raiz / "tools").mkdir()
            script = raiz / "tools/iniciar_api_android.ps1"
            shutil.copyfile(RAIZ / "tools/iniciar_api_android.ps1", script)
            config = raiz / ".env"
            contenido = "NINFAS_ADMIN_API_KEY=" + "a" * 32 + "\n"
            config.write_text(contenido, encoding="utf-8")
            entorno["NINFAS_ADMIN_API_KEY"] = "short"
            resultado = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(script), "-ServerName", "pc.example.com",
                 "-PrepararClave", "-Comprobar"],
                env=entorno, capture_output=True, text=True, errors="replace", timeout=15,
            )
            self.assertNotEqual(0, resultado.returncode)
            self.assertIn("heredada", resultado.stdout + resultado.stderr)
            self.assertEqual(contenido, config.read_text(encoding="utf-8"))


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Requiere PowerShell Windows")
class AndroidLauncherPreflightTests(unittest.TestCase):
    def _ejecutar_con_listener(self, tipo="propio", direccion="127.0.0.1", host_aceptado=True):
        entorno = _entorno_temporal()
        entorno.pop("NINFAS_ADMIN_API_KEY", None)
        with tempfile.TemporaryDirectory(dir=TEMPORALES) as temporal:
            raiz = Path(temporal)
            (raiz / "tools").mkdir()
            script = raiz / "tools/iniciar_api_android.ps1"
            shutil.copyfile(RAIZ / "tools/iniciar_api_android.ps1", script)
            python = raiz / ".venv/Scripts/python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture: no ejecutar")
            marca_python = raiz / "python_ejecutado"
            marca_probe = raiz / "probe"
            config = raiz / ".env"
            contenido = "NINFAS_ADMIN_API_KEY=" + "f" * 32 + "\nNO_MODIFICAR=fixture\n"
            config.write_text(contenido, encoding="utf-8")

            ejecutable = str(python)
            modulo = "app.servidor:app"
            padre = 0
            fecha_padre = "2026-11-18T00:00:01Z"
            if tipo == "otro_modulo":
                modulo = "http.server"
            elif tipo == "otra_raiz":
                ejecutable = str(raiz / "otro-proyecto/.venv/Scripts/python.exe")
            elif tipo in ("redirector_uv", "padre_pid_reutilizado"):
                ejecutable = r"C:\uv-fixture\python\python.exe"
                padre = 5252
                if tipo == "padre_pid_reutilizado":
                    fecha_padre = "2026-11-18T00:00:03Z"

            commandline = f'"{ejecutable}" -m uvicorn {modulo} --host 127.0.0.1 --port 8123'
            if tipo == "app_dir_personalizado":
                commandline += f' --app-dir "{raiz / "otro-proyecto"}"'
            parent_commandline = f'"{python}" -m uvicorn app.servidor:app --host 127.0.0.1 --port 8123'
            dobles = r"""
$fixtureProcesses = @{
    4242 = [pscustomobject]@{
        ProcessId = 4242; ParentProcessId = @@PARENT@@;
        ExecutablePath = @@EXECUTABLE@@; CommandLine = @@COMMANDLINE@@;
        CreationDate = [datetime]'2026-11-18T00:00:02Z'
    }
    5252 = [pscustomobject]@{
        ProcessId = 5252; ParentProcessId = 1;
        ExecutablePath = @@PYTHON@@; CommandLine = @@PARENT_COMMANDLINE@@;
        CreationDate = [datetime]@@PARENT_DATE@@
    }
}
function global:Get-NetTCPConnection {
    [CmdletBinding()]
    param($LocalPort, $State, $LocalAddress)
    [pscustomobject]@{ LocalAddress = @@ADDRESS@@; LocalPort = 8123; State = 'Listen'; OwningProcess = 4242 }
}
function global:Get-CimInstance {
    [CmdletBinding()]
    param($ClassName, $Filter)
    if ($ClassName -ne 'Win32_Process') { throw 'Consulta CIM inesperada en fixture.' }
    if (-not $Filter) { return $fixtureProcesses.Values }
    $fixtureMatch = [regex]::Match([string]$Filter, '(\d+)')
    if (-not $fixtureMatch.Success) { throw 'Filtro CIM inesperado en fixture.' }
    $fixtureProcesses[[int]$fixtureMatch.Value]
}
function global:Invoke-WebRequest {
    [CmdletBinding()]
    param($Uri, $Headers, $Method, $TimeoutSec, $MaximumRedirection, [switch]$UseBasicParsing)
    [IO.File]::WriteAllText(@@PROBE_MARKER@@, ([string]$Uri + "`n" + [string]$Headers['Host'] + "`n" + [string]$Method))
    @@PROBE_RESULT@@
}
function global:Start-Process {
    [IO.File]::WriteAllText(@@PYTHON_MARKER@@, 'inicio de proceso')
    throw 'La prueba prohíbe iniciar procesos desde el launcher.'
}
function global:Stop-Process {
    [IO.File]::WriteAllText(@@PYTHON_MARKER@@, 'detencion de proceso')
    throw 'La prueba prohíbe detener procesos desde el launcher.'
}
Set-Item -LiteralPath @@PYTHON_FUNCTION@@ -Value {
    [IO.File]::WriteAllText(@@PYTHON_MARKER@@, 'llamado')
    throw 'La prueba prohíbe ejecutar Python antes de terminar el preflight.'
}
& @@SCRIPT@@ -ServerName 'pc.example.com' -Port 8123 -PrepararClave
"""
            reemplazos = {
                "@@PARENT@@": str(padre),
                "@@EXECUTABLE@@": _literal_ps(ejecutable),
                "@@COMMANDLINE@@": _literal_ps(commandline),
                "@@PYTHON@@": _literal_ps(python),
                "@@PARENT_COMMANDLINE@@": _literal_ps(parent_commandline),
                "@@PARENT_DATE@@": _literal_ps(fecha_padre),
                "@@ADDRESS@@": _literal_ps(direccion),
                "@@PROBE_MARKER@@": _literal_ps(marca_probe),
                "@@PYTHON_FUNCTION@@": _literal_ps("Function:\\global:" + str(python)),
                "@@PYTHON_MARKER@@": _literal_ps(marca_python),
                "@@SCRIPT@@": _literal_ps(script),
                "@@PROBE_RESULT@@": (
                    "[pscustomobject]@{ StatusCode = 200; Content = 'fixture' }"
                    if host_aceptado else
                    "throw [System.Net.WebException]::new('El Host solicitado no fue aceptado (HTTP 400).')"
                ),
            }
            for etiqueta, valor in reemplazos.items():
                dobles = dobles.replace(etiqueta, valor)
            resultado = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", dobles],
                cwd=raiz, env=entorno, capture_output=True, text=True, errors="replace", timeout=20,
            )
            salida = resultado.stdout + resultado.stderr
            self.assertFalse(marca_python.exists(), salida)
            self.assertEqual(contenido, config.read_text(encoding="utf-8"), salida)
            probe = marca_probe.read_text(encoding="utf-8").splitlines() if marca_probe.exists() else []
            return resultado, probe

    def _assert_reutilizado(self, tipo):
        resultado, probe = self._ejecutar_con_listener(tipo=tipo)
        salida = resultado.stdout + resultado.stderr
        self.assertEqual(0, resultado.returncode, salida)
        self.assertRegex(salida.lower(), r"ya.*ejecut")
        self.assertEqual(["http://127.0.0.1:8123/", "pc.example.com"], probe[:2], salida)
        self.assertIn(probe[2].upper() if len(probe) > 2 else "", ("", "GET"), salida)

    def test_reutiliza_listener_del_python_del_proyecto_sin_preparar_clave(self):
        self._assert_reutilizado("propio")

    def test_reutiliza_redirector_uv_con_padre_venv_del_proyecto(self):
        self._assert_reutilizado("redirector_uv")

    def test_rechaza_puerto_de_otro_modulo_sin_ejecutar_python(self):
        resultado, _ = self._ejecutar_con_listener(tipo="otro_modulo")
        self.assertNotEqual(0, resultado.returncode)
        self.assertRegex((resultado.stdout + resultado.stderr).lower(), r"puerto|8123")

    def test_rechaza_mismo_modulo_desde_otro_proyecto_sin_cambiar_env(self):
        resultado, _ = self._ejecutar_con_listener(tipo="otra_raiz")
        self.assertNotEqual(0, resultado.returncode)
        self.assertRegex((resultado.stdout + resultado.stderr).lower(), r"puerto|8123")

    def test_rechaza_app_dir_personalizado_aunque_python_y_modulo_sean_propios(self):
        resultado, _ = self._ejecutar_con_listener(tipo="app_dir_personalizado")
        self.assertNotEqual(0, resultado.returncode)
        self.assertRegex((resultado.stdout + resultado.stderr).lower(), r"puerto|8123")

    def test_rechaza_listener_que_no_esta_limitado_a_loopback(self):
        for direccion in ("0.0.0.0", "::", "192.168.1.20"):
            with self.subTest(direccion=direccion):
                resultado, _ = self._ejecutar_con_listener(direccion=direccion)
                self.assertNotEqual(0, resultado.returncode)
                self.assertRegex((resultado.stdout + resultado.stderr).lower(), r"loopback|127\.0\.0\.1|puerto|8123")

    def test_no_oculta_host_rechazado_por_api_existente(self):
        resultado, probe = self._ejecutar_con_listener(host_aceptado=False)
        salida = resultado.stdout + resultado.stderr
        self.assertNotEqual(0, resultado.returncode)
        self.assertIn("host", salida.lower())
        self.assertEqual(["http://127.0.0.1:8123/", "pc.example.com"], probe[:2], salida)

    def test_rechaza_padre_mas_nuevo_que_listener_por_posible_reuso_pid(self):
        resultado, _ = self._ejecutar_con_listener(tipo="padre_pid_reutilizado")
        self.assertNotEqual(0, resultado.returncode)
        self.assertRegex((resultado.stdout + resultado.stderr).lower(), r"puerto|8123")
