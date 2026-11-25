"""Regresiones del orquestador sin importar main ni abrir dispositivos o .env."""

import ast
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modulos.comportamiento import (
    EstadoComportamiento,
    GestorComportamiento,
    ObservacionComportamiento,
    TipoEvento,
)

RAIZ = Path(__file__).resolve().parent.parent


def cargar_funcion(nombre, contexto):
    """Ejecuta las funciones reales omitiendo imports y configuración con IO."""
    arbol = ast.parse((RAIZ / "main.py").read_text(encoding="utf-8"))
    funciones = [
        nodo
        for nodo in arbol.body
        if isinstance(nodo, ast.FunctionDef) and nodo.name == nombre
    ]
    modulo = ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *funciones],
        type_ignores=[],
    )
    exec(compile(ast.fix_missing_locations(modulo), str(RAIZ / "main.py"), "exec"), contexto)
    return contexto[nombre]


class DetenerSimulacion(Exception):
    pass


def ejecutar_monitor(
    tiempos, alertas=None, paquetes=None, repetir_frame=False,
    estados_camara=None, condiciones=None,
):
    """Corre el bucle real con cámara/inferencia/notificación locales simuladas."""
    pasos = SimpleNamespace(indice=-1, ahora=0.0)
    frame = SimpleNamespace(shape=(480, 640, 3))
    eventos = []
    guardados = []
    notificados = []
    observaciones_creadas = []
    gestor = GestorComportamiento()
    paquetes = paquetes or {}
    if condiciones is None:
        condiciones = []

    class Camara:
        def estado(self):
            return (estados_camara or {}).get(pasos.indice + 1, {"conectada": True})

        def leer(self):
            pasos.indice += 1
            if pasos.indice >= len(tiempos):
                raise DetenerSimulacion()
            return (1 if repetir_frame and pasos.indice > 0 else pasos.indice), frame

        def start(self):
            pass

        def stop(self):
            pass

    def monotonic():
        pasos.ahora = tiempos[min(pasos.indice + 1, len(tiempos) - 1)]
        return pasos.ahora

    def crear_observaciones(resultado, *_args):
        observaciones_creadas.append(pasos.indice)
        if not resultado.detecciones:
            return []
        return [ObservacionComportamiento(7, EstadoComportamiento.COMIENDO, 0.9)]

    def nulo(*_args, **_kwargs):
        return None
    procesador = SimpleNamespace(
        enviar_frame_async=nulo,
        recoger_resultado_async=lambda: paquetes.get(pasos.indice),
        procesar=lambda resultados, *_args: SimpleNamespace(detecciones=[1] if resultados else [], comederos=[], bebederos=[]),
        detener_worker_async=nulo,
    )
    audio = SimpleNamespace(start=nulo, stop=nulo, get_status=lambda: {"status": "silencio"})
    contexto = dict(
        COLA_BD=None,
        cargar_modelo=lambda: SimpleNamespace(names={0: "ninfa"}),
        seleccionar_fuente_video=lambda: (0, None),
        configurar_identificacion=lambda: (object(), ["Mushu"]),
        ProcesadorDetecciones=lambda **_kwargs: procesador,
        VisualizadorDetecciones=lambda: None,
        GestorZonas=lambda: SimpleNamespace(actualizar=nulo),
        CamaraStream=lambda _fuente: Camara(),
        AudioMonitorNulo=lambda: audio,
        MovementMonitor=lambda: SimpleNamespace(get_global_activity=lambda: ("Normal", 0.0)),
        DB_ACTIVA=False,
        HealthMonitor=lambda *_args, **_kwargs: SimpleNamespace(
            actualizar_condiciones=lambda **kwargs: condiciones.append(kwargs),
            check_health=lambda: (alertas or {}).get(pasos.indice, []),
            get_stats=lambda: {"eating_sec": 0, "drinking_sec": 0},
        ),
        EstabilizadorAnimo=lambda **_kwargs: SimpleNamespace(actualizar=lambda _animo: ("Normal", False)),
        SnapshotPeriodico=lambda: SimpleNamespace(toca_guardar=lambda: False),
        GestorComportamiento=lambda: gestor,
        NotificadorAlertas=lambda: SimpleNamespace(
            notificar_async=lambda clave, texto, **kwargs: notificados.append((clave, texto, kwargs["nivel"])),
            stop=nulo,
        ),
        RecolectorActivoDataset=lambda: SimpleNamespace(registrar_frame=nulo, evaluar_y_guardar=nulo, stop=nulo),
        time=SimpleNamespace(monotonic=monotonic, perf_counter=lambda: pasos.ahora, sleep=nulo),
        CONF_NINFA=0.55, CONF_PLATOS=0.55, AREA_MINIMA=800, AREA_MAXIMA=85000,
        FPS_OBJETIVO=20.0, DETECT_INTERVALO=0.0, PERSISTENCIA_CAJAS=1.5,
        INFERENCIA_TIMEOUT_SEGUNDOS=30.0,
        CAMARA_FRAME_TIMEOUT_SEGUNDOS=5.0,
        es_modo_headless=lambda: True,
        IdentificadorColor=SimpleNamespace(frame_tiene_color=lambda _frame: True),
        calcular_animo=lambda *_args: "Normal",
        generar_recomendaciones=lambda *_args: [],
        crear_observaciones_comportamiento=crear_observaciones,
        procesar_eventos_comportamiento=lambda nuevos, *_args, **_kwargs: eventos.extend(nuevos),
        guardar_async=lambda *args: guardados.append(args),
        cerrar_cola_escritura=None,
        print=nulo,
    )
    iniciar = cargar_funcion("iniciar_monitoreo", contexto)
    try:
        iniciar()
    except DetenerSimulacion:
        pass
    return guardados, notificados, eventos, observaciones_creadas


class RecuperacionTrackingTests(unittest.TestCase):
    def setUp(self):
        self.reloj = SimpleNamespace(ahora=0.0)
        self.inferir = cargar_funcion("inferir", dict(
            os=SimpleNamespace(getenv=lambda *_args: "0"),
            time=SimpleNamespace(monotonic=lambda: self.reloj.ahora),
            CONF_NINFA=0.55, CONF_PLATOS=0.55, CONF_CAPTURA_ACTIVA=0.25,
            IMGSZ_INFERENCIA=512, TRACKER_CONFIG="botsort.yaml",
            TRACKING_REINTENTO_SEGUNDOS=30.0,
            print=lambda *_args: None,
        ))

    def test_error_transitorio_recupera_tracking_despues_de_la_pausa(self):
        class Modelo:
            intentos = 0

            def track(self, *_args, **_kwargs):
                self.intentos += 1
                if self.intentos == 1:
                    raise RuntimeError("fallo temporal")
                return ["track recuperado"]

            def predict(self, *_args, **_kwargs):
                return ["deteccion simple"]

        modelo = Modelo()
        self.assertEqual((["deteccion simple"], False), self.inferir(modelo, None, True))
        self.reloj.ahora = 1.0
        self.assertEqual((["deteccion simple"], False), self.inferir(modelo, None, False))
        self.assertEqual(1, modelo.intentos)
        self.reloj.ahora = 31.0
        self.assertEqual((["track recuperado"], True), self.inferir(modelo, None, False))
        # Un callback ya encolado puede conservar la bandera anterior.
        self.reloj.ahora = 32.0
        self.assertEqual((["track recuperado"], True), self.inferir(modelo, None, False))

    def test_dependencia_ausente_no_reintenta_tracking_en_cada_frame(self):
        class Modelo:
            intentos = 0

            def track(self, *_args, **_kwargs):
                self.intentos += 1
                raise ModuleNotFoundError("No module named 'lap'")

            def predict(self, *_args, **_kwargs):
                return ["deteccion simple"]

        modelo = Modelo()
        self.inferir(modelo, None, True)
        for instante in (1.0, 2.0, 29.0):
            self.reloj.ahora = instante
            # La cola puede tener una tarea capturada antes del primer error.
            self.assertEqual((["deteccion simple"], False), self.inferir(modelo, None, True))
        self.assertEqual(1, modelo.intentos)
        self.reloj.ahora = 31.0
        self.inferir(modelo, None, False)
        self.assertEqual(2, modelo.intentos)


class RecuperacionMonitorTests(unittest.TestCase):
    def test_frame_envejecido_pausa_salud_y_no_produce_observaciones_nuevas(self):
        frame = SimpleNamespace(shape=(480, 640, 3))
        paquete = ([object()], True, frame, 1)
        condiciones = []
        _, _, _, observaciones = ejecutar_monitor(
            [0.0, 600.0], paquetes={0: paquete, 1: paquete},
            estados_camara={1: {"conectada": True, "segundos_desde_frame": 600.0}},
            condiciones=condiciones,
        )
        self.assertEqual([True, False], [estado["camara_conectada"] for estado in condiciones])
        self.assertFalse(condiciones[-1]["luz_diurna"])
        self.assertEqual([0], observaciones)

    def test_primer_frame_envejecido_tambien_pausa_salud(self):
        condiciones = []
        _, _, _, observaciones = ejecutar_monitor(
            [600.0],
            estados_camara={0: {"conectada": True, "segundos_desde_frame": 600.0}},
            condiciones=condiciones,
        )
        self.assertEqual([{"camara_conectada": False, "luz_diurna": False}], condiciones)
        self.assertEqual([], observaciones)

    def test_escalada_se_guarda_y_notifica_sin_duplicar_nivel_repetido(self):
        vigilancia = {"tipo": "SinComer", "nivel": "vigilancia", "horas": 4, "texto": "observacion"}
        critica = {"tipo": "SinComer", "nivel": "critica", "horas": 8, "texto": "urgencia"}
        guardados, notificados, _, _ = ejecutar_monitor(
            [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
            alertas={0: [vigilancia], 1: [vigilancia], 2: [critica], 3: [critica], 5: [critica]},
        )
        self.assertEqual(["Vigilancia", "Alerta", "Alerta"], [fila[3] for fila in guardados])
        self.assertEqual(["vigilancia", "critica", "critica"], [item[2] for item in notificados])
        self.assertNotEqual(notificados[0][0], notificados[1][0], "La escalada debe evitar el cooldown del nivel previo")

    def test_sin_resultados_expira_consumo_sin_reutilizar_observaciones(self):
        frame = SimpleNamespace(shape=(480, 640, 3))
        paquete = ([object()], True, frame, 1)
        _, _, eventos, observaciones = ejecutar_monitor(
            [0.0, 2.0, 3.0, 33.0, 35.0], paquetes={0: paquete, 1: paquete}
        )
        finales = [evento for evento in eventos if evento.tipo == TipoEvento.FIN]
        self.assertEqual(1, len(finales))
        self.assertEqual("track_perdido", finales[0].motivo)
        self.assertEqual(2.0, finales[0].timestamp)
        self.assertEqual([0, 1], observaciones)

    def test_frame_repetido_headless_tambien_deja_expirar_consumo(self):
        frame = SimpleNamespace(shape=(480, 640, 3))
        paquete = ([object()], True, frame, 1)
        _, _, eventos, observaciones = ejecutar_monitor(
            [0.0, 2.0, 3.0, 33.0], paquetes={0: paquete, 1: paquete}, repetir_frame=True
        )
        finales = [evento for evento in eventos if evento.tipo == TipoEvento.FIN]
        self.assertEqual(["track_perdido"], [evento.motivo for evento in finales])
        self.assertEqual([0, 1], observaciones)

    def test_inferencia_saludable_lenta_conserva_candidato_entre_paquetes(self):
        frame = SimpleNamespace(shape=(480, 640, 3))
        paquete = ([object()], True, frame, 1)
        _, _, eventos, observaciones = ejecutar_monitor(
            [0.0, 1.0, 2.0, 3.1, 4.0, 5.0, 6.0, 7.1, 8.0],
            paquetes={0: paquete, 4: paquete, 8: paquete},
        )
        inicios = [evento for evento in eventos if evento.tipo == TipoEvento.INICIO]
        self.assertEqual([0.0], [evento.timestamp for evento in inicios])
        finales = [evento for evento in eventos if evento.tipo == TipoEvento.FIN]
        self.assertEqual(["cierre_monitor"], [evento.motivo for evento in finales])
        self.assertEqual([0, 4, 8], observaciones)

    def test_resultado_vacio_expira_track_con_tolerancia_habitual(self):
        frame = SimpleNamespace(shape=(480, 640, 3))
        paquete = ([object()], True, frame, 1)
        vacio = ([], True, frame, 2)
        _, _, eventos, _ = ejecutar_monitor(
            [0.0, 2.0, 3.0, 6.0], paquetes={0: paquete, 1: paquete, 2: vacio, 3: vacio}
        )
        finales = [evento for evento in eventos if evento.tipo == TipoEvento.FIN]
        self.assertEqual(["track_perdido"], [evento.motivo for evento in finales])
        self.assertEqual([2.0], [evento.timestamp for evento in finales])


class SalidaOrquestadorTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("powershell"), "Requiere PowerShell")
    def test_exit_de_main_se_propaga_despues_de_detener_api(self):
        with tempfile.TemporaryDirectory(dir=RAIZ) as temporal:
            base = Path(temporal)
            (base / "tools").mkdir()
            (base / "modulos").mkdir()
            (base / ".env").write_text("", encoding="utf-8")
            (base / "dotenv.py").write_text("def load_dotenv(*args): pass\n", encoding="utf-8")
            (base / "modulos" / "__init__.py").write_text("", encoding="utf-8")
            (base / "modulos" / "base_datos.py").write_text("def _cargar_config_azure(): return False\n", encoding="utf-8")
            (base / "tools" / "verificar_proyecto.py").write_text("pass\n", encoding="utf-8")
            (base / "main.py").write_text("raise SystemExit(17)\n", encoding="utf-8")
            python_exe = sys.executable.replace("'", "''")
            dobles = "\n".join([
                "function Join-Path { param($Path, $ChildPath)",
                f"if ($ChildPath -eq '.venv\\Scripts\\python.exe') {{ return '{python_exe}' }}",
                "Microsoft.PowerShell.Management\\Join-Path $Path $ChildPath }",
                "function Get-OdbcDriver { return @() }",
                "function Start-Process { return [pscustomobject]@{ Id = 123; HasExited = $false } }",
                "function Start-Sleep {}",
                "function Invoke-WebRequest { return [pscustomobject]@{ StatusCode = 200 } }",
                "function Stop-Process { Set-Content -LiteralPath 'api_detenida' -Value 'si' }",
                "",
            ])
            fuente = (RAIZ / "tools" / "orquestador_operativo.ps1").read_text(encoding="utf-8")
            # param debe permanecer al inicio del script de PowerShell.
            inicio = fuente.index('$ErrorActionPreference = "Stop"')
            script = base / "tools" / "orquestador_operativo.ps1"
            script.write_text(fuente[:inicio] + dobles + fuente[inicio:], encoding="utf-8-sig")
            resultado = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                cwd=base, capture_output=True, text=True, timeout=30,
            )
            self.assertTrue((base / "api_detenida").is_file(), resultado.stderr)
            self.assertEqual(17, resultado.returncode, resultado.stdout + resultado.stderr)


if __name__ == "__main__":
    unittest.main()
