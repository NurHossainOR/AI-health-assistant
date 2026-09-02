from __future__ import annotations

import io
import logging
from pathlib import Path

import numpy as np
import pydicom
from PIL import Image
from pydicom.pixel_data_handlers.util import apply_modality_lut, apply_voi_lut, convert_color_space

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def is_dicom(mime_type: str, filename: str, data: bytes | None = None) -> bool:
    name = (filename or "").lower()
    mime = (mime_type or "").lower()
    if mime in {"application/dicom", "application/dicom+json"} or name.endswith(".dcm"):
        return True
    return bool(data and len(data) > 132 and data[128:132] == b"DICM")


def to_png_bytes(data: bytes) -> bytes:
    try:
        ds = pydicom.dcmread(io.BytesIO(data), force=True)
        arr = ds.pixel_array
    except Exception as exc:  # noqa: BLE001
        logger.warning("DICOM pixel decode failed: %s", type(exc).__name__)
        raise AppError(
            "Could not decode this DICOM image for viewing",
            status_code=422,
            code="dicom_undecodable",
        ) from exc

    photometric = str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2") or "MONOCHROME2")
    if arr.ndim == 4:
        arr = arr[0]
    if arr.ndim == 3 and arr.shape[-1] not in (3, 4) and arr.shape[0] not in (3, 4):
        arr = arr[0]

    if photometric.startswith("YBR"):
        try:
            arr = convert_color_space(arr, photometric, "RGB")
            photometric = "RGB"
        except Exception:  # noqa: BLE001
            pass

    if photometric in {"RGB", "PALETTE COLOR"} or (arr.ndim == 3 and arr.shape[-1] in (3, 4)):
        if arr.dtype != np.uint8:
            arr = _scale_to_uint8(arr.astype(np.float64))
        img = Image.fromarray(arr[..., :3].astype(np.uint8), mode="RGB")
    else:
        try:
            arr = apply_modality_lut(arr, ds)
        except Exception:  # noqa: BLE001
            pass
        try:
            arr = apply_voi_lut(arr, ds)
        except Exception:  # noqa: BLE001
            pass
        gray = _scale_to_uint8(np.asarray(arr, dtype=np.float64))
        if photometric == "MONOCHROME1":
            gray = 255 - gray
        img = Image.fromarray(gray, mode="L")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def preview_filename(original: str) -> str:
    stem = Path(original or "dicom").stem or "dicom"
    return f"{stem}.png"


def _scale_to_uint8(arr: np.ndarray) -> np.ndarray:
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros(arr.shape, dtype=np.uint8)
    lo = float(np.min(finite))
    hi = float(np.max(finite))
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    scaled = (arr - lo) / (hi - lo) * 255.0
    return np.clip(scaled, 0, 255).astype(np.uint8)
