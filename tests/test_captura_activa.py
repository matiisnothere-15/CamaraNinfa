import tempfile
import threading
import types
import unittest
from pathlib import Path

import numpy as np

from modulos.captura_activa import RecolectorActivoDataset


def crear_resultado_falso(num_aves: int, num_comederos: int, confianzas: list[float]):
    detecciones = types.SimpleNamespace(
        confidence=np.array(confianzas, dtype=float) if confianzas else np.array([])
    )
    return types.SimpleNamespace(
        aves=list(range(num_aves)),
        comederos=list(range(num_comederos)),
        bebederos=[1],
        detecciones=detecciones,
    )


class CapturaActivaTests(unittest.TestCase):
    def test_desactivado_por_defecto_no_guarda(self):
        recolector = RecolectorActivoDataset(habilitado=False)
        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        resultado = crear_resultado_falso(1, 0, [0.85])
        self.assertIsNone(recolector.evaluar_y_guardar(frame, resultado, ahora=10.0))

    def test_captura_cuando_hay_ave_pero_falta_comedero_y_respeta_cooldown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guardados = []

            def escritor_falso(ruta: Path, _frame: np.ndarray) -> bool:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(b"jpg")
                guardados.append(ruta)
                return True

            recolector = RecolectorActivoDataset(
                directorio=tmpdir,
                habilitado=True,
                intervalo_minimo_segundos=600,
                max_archivos=2,
                escritor_imagen=escritor_falso,
            )
            frame = np.zeros((32, 32, 3), dtype=np.uint8)
            sin_comedero = crear_resultado_falso(1, 0, [0.90])

            ruta1 = recolector.evaluar_y_guardar(frame, sin_comedero, ahora=100.0)
            self.assertIsNotNone(ruta1)
            self.assertIn("comedero_no_detectado", ruta1.name)

            # Dentro del cooldown de 600s -> no guarda
            self.assertIsNone(
                recolector.evaluar_y_guardar(frame, sin_comedero, ahora=300.0)
            )

            # Pasado el cooldown y con baja confianza -> guarda segundo archivo
            baja_conf = crear_resultado_falso(1, 1, [0.32, 0.88])
            ruta2 = recolector.evaluar_y_guardar(frame, baja_conf, ahora=800.0)
            self.assertIsNotNone(ruta2)
            self.assertIn("baja_confianza_32", ruta2.name)

            # Tope de max_archivos=2 alcanzado -> ya no guarda más
            self.assertIsNone(
                recolector.evaluar_y_guardar(frame, sin_comedero, ahora=1600.0)
            )
            self.assertEqual(2, len(guardados))

    def test_evalua_confianzas_crudas_antes_del_filtro_y_guarda_en_hilo_secundario(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guardados = []
            hilos = []

            def escritor_falso(ruta: Path, _frame: np.ndarray) -> bool:
                hilos.append(threading.current_thread())
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(b"jpg")
                guardados.append(ruta)
                return True

            recolector = RecolectorActivoDataset(
                directorio=tmpdir,
                habilitado=True,
                intervalo_minimo_segundos=600,
                max_archivos=5,
                escritor_imagen=escritor_falso,
                asincrono=True,
            )
            frame = np.zeros((32, 32, 3), dtype=np.uint8)
            resultado_filtrado = crear_resultado_falso(1, 1, [0.88, 0.79])
            resultados_crudos = [
                types.SimpleNamespace(
                    boxes=types.SimpleNamespace(
                        conf=np.array([0.88, 0.79, 0.42], dtype=float)
                    )
                )
            ]

            ruta = recolector.evaluar_y_guardar(
                frame,
                resultado_filtrado,
                ahora=100.0,
                resultados_crudos=resultados_crudos,
            )
            recolector.stop()

            self.assertIsNotNone(ruta)
            self.assertIn("baja_confianza_42", ruta.name)
            self.assertEqual([ruta], guardados)
            self.assertEqual(1, len(hilos))
            self.assertIsNot(threading.main_thread(), hilos[0])

    def test_evidencia_de_eventos_desactivada_por_defecto_no_crea_imagenes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guardados = []

            def escritor_falso(ruta: Path, _frame: np.ndarray) -> bool:
                guardados.append(ruta)
                return True

            recolector = RecolectorActivoDataset(
                directorio=tmpdir,
                habilitado=True,
                escritor_imagen=escritor_falso,
            )
            self.assertFalse(recolector.evidencia_habilitada)
            recolector.registrar_frame(np.full((8, 8, 3), 11, dtype=np.uint8), 10.0)
            ruta = recolector.guardar_evidencia_evento(
                "COMIENDO", "Inicio", 1, nombre_ave="Mushu", ahora=10.0
            )
            recolector.stop()
            self.assertIsNone(ruta)
            self.assertEqual([], guardados)

    def test_guarda_evidencia_visual_de_evento_desde_buffer_temporal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guardados = []

            def escritor_falso(ruta: Path, frame_guardado: np.ndarray) -> bool:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(bytes([int(frame_guardado[0, 0, 0])]))
                guardados.append((ruta, int(frame_guardado[0, 0, 0])))
                return True

            recolector = RecolectorActivoDataset(
                directorio=tmpdir,
                habilitado=True,
                max_archivos=5,
                escritor_imagen=escritor_falso,
                asincrono=True,
                max_frames_buffer=5,
                evidencia_habilitada=True,
            )
            recolector.registrar_frame(np.full((8, 8, 3), 11, dtype=np.uint8), 10.0)
            recolector.registrar_frame(np.full((8, 8, 3), 22, dtype=np.uint8), 12.0)
            recolector.registrar_frame(np.full((8, 8, 3), 33, dtype=np.uint8), 15.0)

            ruta = recolector.guardar_evidencia_evento(
                "COMIENDO", "Inicio", 1, nombre_ave="Mushu", ahora=12.1
            )
            recolector.stop()

            self.assertIsNotNone(ruta)
            self.assertIn("evidencia_", ruta.name)
            self.assertIn("comiendo_Mushu", ruta.name)
            self.assertEqual([(ruta, 22)], guardados)

    def test_evidencia_evento_rota_archivos_antiguos_al_superar_cuota(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            def escritor_falso(ruta: Path, frame_guardado: np.ndarray) -> bool:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(bytes([int(frame_guardado[0, 0, 0])]))
                return True

            with patch.dict("os.environ", {"NINFAS_AUTO_DATASET": "0"}, clear=False):
                recolector = RecolectorActivoDataset(
                    directorio=tmpdir,
                    max_archivos=2,
                    escritor_imagen=escritor_falso,
                    asincrono=True,
                    max_frames_buffer=5,
                    evidencia_habilitada=True,
                )
            self.assertFalse(recolector.habilitado)
            self.assertTrue(recolector.evidencia_habilitada)

            recolector.registrar_frame(np.full((8, 8, 3), 1, dtype=np.uint8), 10.0)
            ruta1 = recolector.guardar_evidencia_evento(
                "COMIENDO", "Inicio", 1, nombre_ave="Mushu", ahora=10.0
            )
            recolector.registrar_frame(np.full((8, 8, 3), 2, dtype=np.uint8), 20.0)
            ruta2 = recolector.guardar_evidencia_evento(
                "BEBIENDO", "Inicio", 2, nombre_ave="Yukki", ahora=20.0
            )
            recolector.registrar_frame(np.full((8, 8, 3), 3, dtype=np.uint8), 30.0)
            ruta3 = recolector.guardar_evidencia_evento(
                "COMIENDO", "Fin", 1, nombre_ave="Mushu", ahora=30.0
            )
            recolector.stop()

            self.assertIsNotNone(ruta1)
            self.assertIsNotNone(ruta2)
            self.assertIsNotNone(ruta3)
            restantes = sorted(Path(tmpdir).glob("*.jpg"))
            self.assertEqual(2, len(restantes))
            self.assertFalse(ruta1.exists())
            self.assertTrue(ruta2.exists())
            self.assertTrue(ruta3.exists())

    def test_rotacion_no_elimina_evidencia_ya_escrita_aun_en_vuelo(self):
        primera_escrita = threading.Event()
        segunda_escrita = threading.Event()
        soltar_primera = threading.Event()
        soltar_segunda = threading.Event()

        with tempfile.TemporaryDirectory() as tmpdir:
            def escritor_pausado(ruta: Path, frame: np.ndarray) -> bool:
                valor = int(frame[0, 0, 0])
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(bytes([valor]))
                if valor == 1:
                    primera_escrita.set()
                    soltar_primera.wait()
                elif valor == 2:
                    segunda_escrita.set()
                    soltar_segunda.wait()
                return True

            recolector = RecolectorActivoDataset(
                directorio=tmpdir,
                habilitado=False,
                evidencia_habilitada=True,
                max_archivos=2,
                escritor_imagen=escritor_pausado,
                asincrono=True,
            )
            rutas = []
            try:
                for valor, instante in ((1, 10.0), (2, 20.0), (3, 30.0)):
                    recolector.registrar_frame(
                        np.full((8, 8, 3), valor, dtype=np.uint8), instante
                    )
                    rutas.append(recolector.guardar_evidencia_evento(
                        "COMIENDO", "Inicio", 1, nombre_ave="Mushu", ahora=instante
                    ))
                    if valor == 1:
                        self.assertTrue(primera_escrita.wait(timeout=5))
                    elif valor == 2:
                        soltar_primera.set()
                        self.assertTrue(segunda_escrita.wait(timeout=5))
            finally:
                soltar_primera.set()
                soltar_segunda.set()
                recolector.stop()

            self.assertTrue(all(ruta is not None for ruta in rutas))
            self.assertFalse(rutas[0].exists())
            self.assertEqual(b"\x02", rutas[1].read_bytes())
            self.assertEqual(b"\x03", rutas[2].read_bytes())
            self.assertEqual(2, len(list(Path(tmpdir).glob("*.jpg"))))


if __name__ == "__main__":
    unittest.main()
