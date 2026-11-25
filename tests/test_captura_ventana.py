"""Selección y captura por HWND sin tocar ventanas reales del escritorio."""

import ctypes
import unittest
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from modulos import captura_ventana


def ventana(hwnd, titulo, proceso, ancho=1280, alto=720, minimizada=False):
    return dict(
        hwnd=hwnd, titulo=titulo, proceso=proceso,
        ancho=ancho, alto=alto, minimizada=minimizada,
    )


class SeleccionBlueStacksTests(unittest.TestCase):
    def test_titulo_chrome_con_bluestacks_no_es_una_fuente_del_emulador(self):
        chrome = ventana(10, "BlueStack Desktop - Google Chrome", r"C:\Chrome\chrome.exe")
        self.assertIsNone(captura_ventana.buscar_ventana("BlueStack Desktop", [chrome]))

    def test_proceso_desconocido_no_se_acepta_solo_por_titulo(self):
        desconocida = ventana(10, "BlueStack Desktop", "")
        self.assertIsNone(captura_ventana.buscar_ventana("BlueStack Desktop", [desconocida]))

    def test_instalador_y_launcher_se_excluyen_aunque_el_titulo_coincida(self):
        for ejecutable in ("BlueStacksInstaller.exe", "HD-MultiInstanceManager.exe", "HD-Player.exe.bak", "launcher.exe"):
            with self.subTest(ejecutable=ejecutable):
                candidata = ventana(10, "BlueStack Desktop", rf"C:\BlueStacks\{ejecutable}")
                self.assertIsNone(captura_ventana.buscar_ventana("BlueStack Desktop", [candidata]))

    def test_elige_hd_player_real_aunque_chrome_tenga_mayor_superficie(self):
        chrome = ventana(10, "BlueStack Desktop - Google Chrome", r"C:\Chrome\chrome.exe", 2000, 1600)
        emulador = ventana(20, "BlueStacks App Player", r"C:\BlueStacks_polar\HD-Player.EXE", 800, 600)
        elegida = captura_ventana.buscar_ventana("BlueStack Desktop", [chrome, emulador])
        self.assertEqual(20, elegida["hwnd"])

    def test_instancias_ambiguas_exigen_un_titulo_especifico(self):
        ventanas = [
            ventana(20, "BlueStacks App Player 1", r"C:\BlueStacks\HD-Player.exe"),
            ventana(30, "BlueStacks App Player 2", r"C:\BlueStacks\HD-Player.exe"),
        ]
        with self.assertRaisesRegex(ValueError, "(?i)varias.*BlueStacks"):
            captura_ventana.buscar_ventana("BlueStack Desktop", ventanas)
        self.assertEqual(30, captura_ventana.buscar_ventana("BlueStacks App Player 2", ventanas)["hwnd"])

    def test_seleccion_generica_conserva_coincidencia_por_titulo(self):
        bloc = ventana(15, "Notas cámara - Bloc de notas", r"C:\Windows\notepad.exe")
        self.assertEqual(15, captura_ventana.buscar_ventana("Notas cámara", [bloc])["hwnd"])


class ProcesoWin32Tests(unittest.TestCase):
    def test_handle_de_proceso_de_64_bits_conserva_ruta_y_se_cierra(self):
        handle_completo = 0x12345678ABCDEF01
        ruta = r"C:\Program Files\BlueStacks_polar\HD-Player.exe"
        # Un DLL sin restype devuelve c_int por defecto: reproduce el truncado.
        abrir = ctypes.CFUNCTYPE(wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)(
            lambda *_args: handle_completo
        )
        abrir.restype = ctypes.c_int

        def consultar(handle, _flags, buffer, tamano):
            if handle != handle_completo:
                return 0
            buffer.value = ruta
            tamano._obj.value = len(ruta)
            return 1

        kernel32 = SimpleNamespace(
            OpenProcess=abrir,
            QueryFullProcessImageNameW=Mock(side_effect=consultar),
            CloseHandle=Mock(return_value=1),
        )
        dlls = SimpleNamespace(user32=Mock(), gdi32=Mock(), kernel32=kernel32)
        with (
            patch.object(captura_ventana.os, "name", "nt"),
            patch.object(captura_ventana.ctypes, "windll", dlls, create=True),
            patch.object(captura_ventana, "_WIN32_CONFIGURADO", False),
        ):
            self.assertEqual(ruta, captura_ventana._obtener_ejecutable_pid(321))
        kernel32.CloseHandle.assert_called_once_with(handle_completo)

    def test_hwnd_reutilizado_por_chrome_no_conserva_captura_del_emulador(self):
        captura = captura_ventana.CapturaVentana.__new__(captura_ventana.CapturaVentana)
        captura._abierta = True
        captura._hwnd = 20
        captura.filtro_titulo = "BlueStack Desktop"
        user32 = SimpleNamespace(
            IsWindow=lambda _hwnd: True,
            IsWindowVisible=lambda _hwnd: True,
            IsIconic=lambda _hwnd: False,
            GetWindowThreadProcessId=lambda _hwnd, pid: setattr(pid._obj, "value", 123),
        )
        with (
            patch.object(captura_ventana.os, "name", "nt"),
            patch.object(captura_ventana.ctypes, "windll", SimpleNamespace(user32=user32), create=True),
            patch.object(captura_ventana, "_obtener_ejecutable_pid", return_value=r"C:\Chrome\chrome.exe"),
            patch.object(captura_ventana, "buscar_ventana", return_value=None),
        ):
            self.assertFalse(captura.isOpened())
        self.assertIsNone(captura._hwnd)


class CapturaAisladaTests(unittest.TestCase):
    def capturar_con_fallback(self, grab):
        captura = captura_ventana.CapturaVentana.__new__(captura_ventana.CapturaVentana)
        captura._hwnd = 0x12345678ABCDEF01
        captura.intervalo = 0.0
        captura._ultimo_ts = 0.0

        def obtener_rect(_hwnd, rect):
            rect._obj.right = 64
            rect._obj.bottom = 48
            return 1

        user32 = SimpleNamespace(GetClientRect=obtener_rect, ClientToScreen=lambda *_args: 1)
        with (
            patch.object(captura, "isOpened", return_value=True),
            patch.object(captura, "_capturar_printwindow", return_value=None),
            patch.object(captura_ventana.ctypes, "windll", SimpleNamespace(user32=user32), create=True),
            patch.object(captura_ventana, "ImageGrab", SimpleNamespace(grab=grab)),
        ):
            return captura.read()

    def test_fallback_captura_hwnd_y_no_pixeles_del_chrome_superpuesto(self):
        llamadas = []

        def grab(**kwargs):
            llamadas.append(kwargs)
            rgb = np.empty((48, 64, 3), dtype=np.uint8)
            rgb[:] = [10, 20, 30] if kwargs.get("window") == 0x12345678ABCDEF01 else [200, 0, 0]
            return rgb

        exito, frame = self.capturar_con_fallback(grab)
        self.assertTrue(exito)
        np.testing.assert_array_equal(frame[0, 0], [30, 20, 10])
        self.assertEqual([{"window": 0x12345678ABCDEF01}], llamadas)

    def test_pillow_sin_soporte_hwnd_falla_sin_recortar_el_escritorio(self):
        llamadas = []

        def grab(**kwargs):
            llamadas.append(kwargs)
            if "window" in kwargs:
                raise TypeError("window no soportado")
            return np.full((48, 64, 3), 200, dtype=np.uint8)

        self.assertEqual((False, None), self.capturar_con_fallback(grab))
        self.assertEqual([{"window": 0x12345678ABCDEF01}], llamadas)

    def test_captura_hwnd_vacia_no_se_publica_como_frame_valido(self):
        self.assertEqual((False, None), self.capturar_con_fallback(lambda **_kwargs: np.zeros((48, 64, 3), dtype=np.uint8)))


if __name__ == "__main__":
    unittest.main()
