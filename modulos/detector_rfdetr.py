"""Adaptador del detector RF-DETR (Roboflow) compatible con BoT-SORT y Supervision.

Reemplaza a YOLOv8/YOLOv11 como detector principal manteniendo la interfaz
``track()`` / ``predict()`` que consumen ``main.py`` y ``ProcesadorDetecciones``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
import torch
from ultralytics.cfg import IterableSimpleNamespace
from ultralytics.engine.results import Boxes, Results
from ultralytics.trackers.bot_sort import BOTSORT
from ultralytics.utils import YAML

ROBOFLOW_MODEL_ID_DEFAULT = (
    "monitorninfas20/monitorninfas-5-rfdetr-nas-base-t1--96ff59"
)
IMGSZ_RFDETR = 640
NOMBRES_CLASES: dict[int, str] = {
    0: "bebedero",
    1: "comedero",
    2: "ninfa",
}
MAPA_NOMBRES_CLASES: dict[str, int] = {
    "bebedero": 0,
    "comedero": 1,
    "ninfa": 2,
}

_BOTSORT_DEFAULTS: dict[str, Any] = {
    "tracker_type": "botsort",
    "track_high_thresh": 0.45,
    "track_low_thresh": 0.15,
    "new_track_thresh": 0.55,
    "track_buffer": 45,
    "match_thresh": 0.85,
    "fuse_score": True,
    "gmc_method": "none",
    "proximity_thresh": 0.5,
    "appearance_thresh": 0.8,
    "with_reid": False,
    "model": "auto",
}


def _leer_campo(obj: Any, nombre: str, predeterminado: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(nombre, predeterminado)
    return getattr(obj, nombre, predeterminado)


def _proveedores_onnx() -> list[str]:
    """Solicita únicamente backends instalados y una GPU utilizable."""
    import onnxruntime

    disponibles = onnxruntime.get_available_providers()
    proveedores = ["CPUExecutionProvider"]
    # Importar torch al inicio también carga las DLL CUDA/cuDNN en Windows.
    if "CUDAExecutionProvider" in disponibles and torch.cuda.is_available():
        proveedores.insert(0, "CUDAExecutionProvider")
    return proveedores


def _resolver_clase_id(class_name: Any, class_id: Any) -> int | None:
    if class_name is not None:
        limpio = str(class_name).strip().lower()
        if limpio in MAPA_NOMBRES_CLASES:
            return MAPA_NOMBRES_CLASES[limpio]
    if class_id is not None:
        try:
            cid = int(class_id)
        except (TypeError, ValueError):
            return None
        if cid in NOMBRES_CLASES:
            return cid
    return None


def _crear_tracker_botsort(ruta_yaml: str | Path | None) -> BOTSORT:
    datos: dict[str, Any] = {}
    if ruta_yaml:
        ruta = Path(ruta_yaml)
        if ruta.is_file():
            cargado = YAML.load(str(ruta))
            if isinstance(cargado, dict):
                datos = cargado
    config = dict(_BOTSORT_DEFAULTS)
    config.update(datos)
    return BOTSORT(args=IterableSimpleNamespace(**config))


class DetectorRFDETR:
    """Ejecuta inferencia local con RF-DETR y asigna ``track_id`` mediante BoT-SORT."""

    def __init__(
        self,
        model_id: str | None = None,
        api_key: str | None = None,
        weights_path: str | Path | None = None,
        tracker_config: str | Path | None = None,
        predictor: Callable[[np.ndarray, float], Any] | None = None,
    ) -> None:
        env_model_id = os.getenv("ROBOFLOW_MODEL_ID", "").strip()
        self.model_id = (
            model_id.strip()
            if isinstance(model_id, str) and model_id.strip()
            else (env_model_id or ROBOFLOW_MODEL_ID_DEFAULT)
        )
        self.api_key = (
            os.getenv("ROBOFLOW_API_KEY", "").strip()
            if api_key is None
            else str(api_key).strip()
        )
        raw_weights = (
            os.getenv("RFDETR_WEIGHTS_PATH", "").strip()
            if weights_path is None
            else str(weights_path).strip()
        )
        self.weights_path = raw_weights or None
        self.tracker_config = str(tracker_config) if tracker_config else None
        self.names: dict[int, str] = dict(NOMBRES_CLASES)
        self.task = "detect"
        self.proveedores_ejecucion: list[str] = []

        self._predictor_inyectado = predictor
        self._modelo_inference = None
        self._modelo_rfdetr = None
        self._tracker: BOTSORT | None = None
        self._tracker_config_activo: str | None = self.tracker_config

        if self._predictor_inyectado is None:
            self._cargar_backend()

    def _cargar_backend(self) -> None:
        if self.weights_path:
            ruta = Path(self.weights_path).expanduser()
            if not ruta.is_absolute():
                ruta = Path(__file__).resolve().parent.parent / ruta
            if not ruta.is_file():
                raise FileNotFoundError(
                    f"No se encontraron los pesos RF-DETR en: {ruta}"
                )
            try:
                from rfdetr import RFDETRBase
            except ImportError as error:
                raise RuntimeError(
                    "Para cargar pesos .pth locales de RF-DETR instala el paquete "
                    "'rfdetr' (`pip install rfdetr`) en tu entorno virtual."
                ) from error
            self._modelo_rfdetr = RFDETRBase(pretrain_weights=str(ruta))
            return

        # En Windows, /tmp/cache puede quedar fuera del proyecto y sin permisos.
        # Se fija antes de importar Inference, que lee la ruta durante el import.
        cache_local = Path(__file__).resolve().parent.parent / ".cache" / "roboflow"
        os.environ.setdefault("MODEL_CACHE_DIR", str(cache_local))
        os.environ.setdefault("CORE_MODEL_GAZE_ENABLED", "False")
        try:
            from inference import get_model
        except ImportError as error:
            raise RuntimeError(
                "Falta la librería 'inference' / 'inference-gpu' para ejecutar "
                f"el modelo RF-DETR ({self.model_id}) en local. Instálala con "
                "`pip install inference-gpu` (con GPU CUDA) o `pip install inference` "
                "(CPU), y define `ROBOFLOW_API_KEY` en `.env` para descargarlo la "
                "primera vez."
            ) from error

        kwargs: dict[str, Any] = {
            "model_id": self.model_id,
            "onnxruntime_execution_providers": _proveedores_onnx(),
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        self._modelo_inference = get_model(**kwargs)
        sesion = getattr(self._modelo_inference, "onnx_session", None)
        if sesion is not None:
            proveedores = sesion.get_providers()
            if isinstance(proveedores, (list, tuple)):
                self.proveedores_ejecucion = list(proveedores)

    def _inferir_crudo(self, frame: np.ndarray, conf: float) -> Any:
        if self._predictor_inyectado is not None:
            return self._predictor_inyectado(frame, conf)

        if self._modelo_rfdetr is not None:
            from PIL import Image

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            imagen_pil = Image.fromarray(rgb)
            return self._modelo_rfdetr.predict(imagen_pil, threshold=float(conf))

        return self._modelo_inference.infer(frame, confidence=float(conf))

    @staticmethod
    def _convertir_predicciones(
        crudo: Any, forma_frame: tuple[int, ...], conf_min: float
    ) -> np.ndarray:
        alto, ancho = int(forma_frame[0]), int(forma_frame[1])
        vacio = np.zeros((0, 6), dtype=np.float32)
        if crudo is None:
            return vacio

        if isinstance(crudo, np.ndarray):
            if crudo.size == 0 or crudo.ndim != 2 or crudo.shape[1] < 6:
                return vacio
            mascara = crudo[:, 4] >= float(conf_min)
            return crudo[mascara, :6].astype(np.float32, copy=True)

        # Objeto sv.Detections (p. ej. devuelto por RFDETRBase.predict)
        if hasattr(crudo, "xyxy") and hasattr(crudo, "class_id"):
            xyxy = np.asarray(crudo.xyxy, dtype=np.float32)
            if len(xyxy) == 0:
                return vacio
            confs = (
                np.asarray(crudo.confidence, dtype=np.float32)
                if getattr(crudo, "confidence", None) is not None
                else np.ones(len(xyxy), dtype=np.float32)
            )
            cids_raw = crudo.class_id
            data = getattr(crudo, "data", None)
            nombres = data.get("class_name") if isinstance(data, dict) else None
            filas = []
            for idx in range(len(xyxy)):
                conf_val = float(confs[idx])
                if conf_val < float(conf_min):
                    continue
                cname = nombres[idx] if nombres is not None and idx < len(nombres) else None
                cid_raw = cids_raw[idx] if cids_raw is not None and idx < len(cids_raw) else None
                cid = _resolver_clase_id(cname, cid_raw)
                if cid is None:
                    continue
                x1, y1, x2, y2 = (float(v) for v in xyxy[idx])
                x1 = max(0.0, min(float(ancho), x1))
                x2 = max(0.0, min(float(ancho), x2))
                y1 = max(0.0, min(float(alto), y1))
                y2 = max(0.0, min(float(alto), y2))
                if x2 <= x1 or y2 <= y1:
                    continue
                filas.append([x1, y1, x2, y2, conf_val, float(cid)])
            return np.asarray(filas, dtype=np.float32) if filas else vacio

        # Respuesta de Roboflow inference: suele venir como [response] o response
        respuesta = crudo
        if (
            isinstance(respuesta, (list, tuple))
            and len(respuesta) > 0
            and (
                hasattr(respuesta[0], "predictions")
                or (isinstance(respuesta[0], dict) and "predictions" in respuesta[0])
            )
        ):
            respuesta = respuesta[0]

        preds = _leer_campo(respuesta, "predictions", None)
        while (
            preds is not None
            and not isinstance(preds, (list, tuple))
            and (hasattr(preds, "predictions") or (isinstance(preds, dict) and "predictions" in preds))
        ):
            preds = _leer_campo(preds, "predictions", None)
        if preds is None:
            preds = respuesta if isinstance(respuesta, (list, tuple)) else []

        filas = []
        for pred in preds:
            conf_raw = _leer_campo(pred, "confidence", _leer_campo(pred, "conf", 1.0))
            try:
                conf_val = float(conf_raw)
            except (TypeError, ValueError):
                continue
            if conf_val < float(conf_min):
                continue

            cname = _leer_campo(
                pred, "class_name", _leer_campo(pred, "class", None)
            )
            cid_raw = _leer_campo(pred, "class_id", None)
            cid = _resolver_clase_id(cname, cid_raw)
            if cid is None:
                continue

            bbox = _leer_campo(pred, "bbox", _leer_campo(pred, "xyxy", None))
            if bbox is not None and len(bbox) == 4:
                x1, y1, x2, y2 = (float(v) for v in bbox)
            else:
                cx = _leer_campo(pred, "x", None)
                cy = _leer_campo(pred, "y", None)
                w = _leer_campo(pred, "width", None)
                h = _leer_campo(pred, "height", None)
                if None in (cx, cy, w, h):
                    continue
                x1 = float(cx) - float(w) * 0.5
                y1 = float(cy) - float(h) * 0.5
                x2 = float(cx) + float(w) * 0.5
                y2 = float(cy) + float(h) * 0.5

            x1 = max(0.0, min(float(ancho), x1))
            x2 = max(0.0, min(float(ancho), x2))
            y1 = max(0.0, min(float(alto), y1))
            y2 = max(0.0, min(float(alto), y2))
            if x2 <= x1 or y2 <= y1:
                continue
            filas.append([x1, y1, x2, y2, conf_val, float(cid)])

        return np.asarray(filas, dtype=np.float32) if filas else vacio

    def predict(
        self,
        frame: np.ndarray,
        verbose: bool = False,
        imgsz: int = IMGSZ_RFDETR,
        conf: float = 0.5,
        iou: float = 0.5,
    ) -> list[Results]:
        del verbose, imgsz, iou
        crudo = self._inferir_crudo(frame, conf=float(conf))
        raw = self._convertir_predicciones(crudo, frame.shape, conf_min=float(conf))
        boxes_tensor = (
            torch.from_numpy(raw)
            if len(raw) > 0
            else torch.zeros((0, 6), dtype=torch.float32)
        )
        return [Results(frame, path="", names=self.names, boxes=boxes_tensor)]

    def track(
        self,
        frame: np.ndarray,
        persist: bool = True,
        verbose: bool = False,
        imgsz: int = IMGSZ_RFDETR,
        conf: float = 0.5,
        iou: float = 0.5,
        tracker: str | Path | None = None,
    ) -> list[Results]:
        del verbose, imgsz, iou
        ruta_tracker = str(tracker) if tracker else self.tracker_config
        if self._tracker is None or ruta_tracker != self._tracker_config_activo:
            self._tracker = _crear_tracker_botsort(ruta_tracker)
            self._tracker_config_activo = ruta_tracker
        elif not persist:
            self._tracker.reset()

        crudo = self._inferir_crudo(frame, conf=float(conf))
        raw = self._convertir_predicciones(crudo, frame.shape, conf_min=float(conf))

        if len(raw) > 0:
            cajas_ultralytics = Boxes(raw, frame.shape[:2])
        else:
            cajas_ultralytics = Boxes(
                np.zeros((0, 6), dtype=np.float32), frame.shape[:2]
            )

        tracked = self._tracker.update(cajas_ultralytics, frame)
        if len(tracked) > 0 and getattr(tracked, "ndim", 1) == 2:
            boxes_tensor = torch.from_numpy(tracked[:, :-1].astype(np.float32))
        elif len(raw) > 0:
            boxes_tensor = torch.from_numpy(raw)
        else:
            boxes_tensor = torch.zeros((0, 6), dtype=torch.float32)

        return [Results(frame, path="", names=self.names, boxes=boxes_tensor)]
