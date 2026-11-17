"""Captura de una ventana de escritorio (p. ej. BlueStacks) como fuente OpenCV."""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

import numpy as np

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


_PW_CLIENTONLY = 0x00000001
_PW_RENDERFULLCONTENT = 0x00000002
_DPI_INICIALIZADO = False
_WIN32_CONFIGURADO = False


def _configurar_win32() -> None:
    """Declara argtypes y restype de 64 bits para user32 y gdi32 en Windows."""
    global _WIN32_CONFIGURADO
    if _WIN32_CONFIGURADO or os.name != "nt":
        return
    _WIN32_CONFIGURADO = True

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [
        wintypes.HWND,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClientRect.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.RECT),
    ]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(_POINT),
    ]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
    ]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(_BITMAPINFOHEADER),
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int


def _activar_dpi_real() -> None:
    """Evita recortes cuando Windows aplica escala de pantalla (125%, 150%, etc.)."""
    global _DPI_INICIALIZADO
    if _DPI_INICIALIZADO or os.name != "nt":
        return
    _DPI_INICIALIZADO = True
    _configurar_win32()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _obtener_ejecutable_pid(pid: int) -> str:
    """Obtiene la ruta del ejecutable de un proceso sin requerir permisos de administrador."""
    if os.name != "nt" or pid <= 0:
        return ""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(512)
        tamano = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(tamano)
        ):
            return buffer.value.strip()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _terminos_busqueda(filtro_titulo: str) -> tuple[str, ...]:
    limpio = filtro_titulo.strip().lower()
    if not limpio:
        return ()
    if limpio.startswith(("bluestack", "blue stack")):
        return (
            limpio,
            "bluestack desktop",
            "bluestacks desktop",
            "bluestacks",
            "bluestack",
            "hd-player",
            "app player",
            "bluestacks_polar",
        )
    return (limpio,)


def listar_ventanas_visibles() -> list[dict]:
    """Enumera las ventanas visibles del escritorio de Windows."""
    if os.name != "nt":
        return []

    _activar_dpi_real()
    user32 = ctypes.windll.user32
    pid_actual = os.getpid()
    ventanas: list[dict] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == pid_actual:
            return True

        proceso = _obtener_ejecutable_pid(int(pid.value))
        largo = user32.GetWindowTextLengthW(hwnd)
        titulo = ""
        if largo > 0:
            buffer = ctypes.create_unicode_buffer(largo + 1)
            user32.GetWindowTextW(hwnd, buffer, largo + 1)
            titulo = buffer.value.strip()
        if not titulo and "hd-player" in proceso.lower():
            titulo = "BlueStack Desktop (HD-Player)"
        if not titulo:
            return True

        minimizada = bool(user32.IsIconic(hwnd))
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        ancho = int(rect.right - rect.left)
        alto = int(rect.bottom - rect.top)
        if not minimizada and (ancho < 32 or alto < 32):
            return True

        ventanas.append(
            {
                "hwnd": int(hwnd),
                "titulo": titulo,
                "proceso": proceso,
                "ancho": ancho,
                "alto": alto,
                "minimizada": minimizada,
            }
        )
        return True

    user32.EnumWindows(_callback, 0)
    return ventanas


def buscar_ventana(
    filtro_titulo: str,
    ventanas: list[dict] | None = None,
) -> dict | None:
    """Devuelve la ventana que mejor coincide con el título o proceso indicado."""
    terminos = _terminos_busqueda(filtro_titulo)
    if not terminos:
        return None

    disponibles = ventanas if ventanas is not None else listar_ventanas_visibles()
    candidatas = [
        ventana
        for ventana in disponibles
        if any(
            termino in ventana["titulo"].lower()
            or termino in ventana.get("proceso", "").lower()
            for termino in terminos
        )
    ]
    if not candidatas:
        return None

    def _prioridad(ventana: dict) -> tuple:
        titulo_min = ventana["titulo"].lower()
        proceso_min = ventana.get("proceso", "").lower()
        es_gestor = any(
            palabra in titulo_min
            for palabra in ("multi-instance", "installer", "instalador")
        )
        es_hd_player = "hd-player" in proceso_min
        es_reproductor = (
            "app player" in titulo_min or "bluestack desktop" in titulo_min
        )
        area = max(0, int(ventana.get("ancho", 0)) * int(ventana.get("alto", 0)))
        return (
            not ventana.get("minimizada", False),
            not es_gestor,
            es_hd_player,
            es_reproductor,
            area,
        )

    candidatas.sort(key=_prioridad, reverse=True)
    return candidatas[0]


class CapturaVentana:
    """Imita la interfaz de cv2.VideoCapture capturando una ventana de Windows."""

    def __init__(self, filtro_titulo: str, fps_max: float = 30.0) -> None:
        _activar_dpi_real()
        self.filtro_titulo = filtro_titulo.strip()
        self.intervalo = 1.0 / max(1.0, float(fps_max))
        self._ultimo_ts = 0.0
        self._abierta = True
        self._hwnd: int | None = None
        self._actualizar_hwnd()

    def _actualizar_hwnd(self) -> int | None:
        encontrada = buscar_ventana(self.filtro_titulo)
        self._hwnd = encontrada["hwnd"] if encontrada else None
        return self._hwnd

    def isOpened(self) -> bool:
        if not self._abierta or os.name != "nt":
            return False
        user32 = ctypes.windll.user32
        if self._hwnd and user32.IsWindow(self._hwnd) and user32.IsWindowVisible(self._hwnd):
            return not bool(user32.IsIconic(self._hwnd))
        encontrada = buscar_ventana(self.filtro_titulo)
        if not encontrada or encontrada.get("minimizada"):
            self._hwnd = None
            return False
        self._hwnd = encontrada["hwnd"]
        return True

    def set(self, _prop_id: int, _valor: float) -> bool:
        return False

    def _capturar_printwindow(self, hwnd: int, ancho: int, alto: int) -> np.ndarray | None:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hdc_ventana = user32.GetDC(hwnd)
        if not hdc_ventana:
            return None
        hdc_mem = gdi32.CreateCompatibleDC(hdc_ventana)
        if not hdc_mem:
            user32.ReleaseDC(hwnd, hdc_ventana)
            return None
        hbitmap = gdi32.CreateCompatibleBitmap(hdc_ventana, ancho, alto)
        if not hbitmap:
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(hwnd, hdc_ventana)
            return None

        viejo = gdi32.SelectObject(hdc_mem, hbitmap)
        try:
            banderas = _PW_CLIENTONLY | _PW_RENDERFULLCONTENT
            exito = user32.PrintWindow(hwnd, hdc_mem, banderas)
            if not exito:
                return None

            encabezado = _BITMAPINFOHEADER()
            encabezado.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            encabezado.biWidth = ancho
            encabezado.biHeight = -alto
            encabezado.biPlanes = 1
            encabezado.biBitCount = 32
            encabezado.biCompression = 0

            tamano = ancho * alto * 4
            buffer = ctypes.create_string_buffer(tamano)
            lineas = gdi32.GetDIBits(
                hdc_mem,
                hbitmap,
                0,
                alto,
                buffer,
                ctypes.byref(encabezado),
                0,
            )
            if lineas != alto:
                return None

            bgra = np.frombuffer(buffer, dtype=np.uint8).reshape((alto, ancho, 4))
            frame = bgra[:, :, :3].copy()
            centro = frame[
                alto // 4 : (alto * 3) // 4,
                ancho // 4 : (ancho * 3) // 4,
            ]
            if not np.any(centro):
                return None
            return frame
        finally:
            gdi32.SelectObject(hdc_mem, viejo)
            gdi32.DeleteObject(hbitmap)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(hwnd, hdc_ventana)

    def _capturar_pantalla(
        self, left: int, top: int, ancho: int, alto: int
    ) -> np.ndarray | None:
        if ImageGrab is None:
            return None
        try:
            imagen = ImageGrab.grab(
                bbox=(left, top, left + ancho, top + alto),
                all_screens=True,
            )
            rgb = np.asarray(imagen, dtype=np.uint8)
            if rgb.ndim != 3 or rgb.shape[2] < 3:
                return None
            return rgb[:, :, :3][:, :, ::-1].copy()
        except Exception:
            return None

    def read(self) -> tuple[bool, np.ndarray | None]:
        if not self.isOpened() or self._hwnd is None:
            return False, None

        ahora = time.perf_counter()
        espera = self.intervalo - (ahora - self._ultimo_ts)
        if espera > 0.001:
            time.sleep(espera)
        self._ultimo_ts = time.perf_counter()

        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        if not user32.GetClientRect(self._hwnd, ctypes.byref(rect)):
            return False, None

        ancho = int(rect.right - rect.left)
        alto = int(rect.bottom - rect.top)
        if ancho < 32 or alto < 32:
            return False, None

        frame = self._capturar_printwindow(self._hwnd, ancho, alto)
        if frame is not None:
            return True, frame

        origen = _POINT(0, 0)
        if not user32.ClientToScreen(self._hwnd, ctypes.byref(origen)):
            return False, None

        frame = self._capturar_pantalla(int(origen.x), int(origen.y), ancho, alto)
        if frame is None:
            return False, None
        return True, frame

    def release(self) -> None:
        self._abierta = False
        self._hwnd = None
