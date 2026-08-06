"""Envoltorio sobre el binario `ebook-convert` de Calibre — aísla la
dependencia externa del resto de capas (el service no invoca subprocess
directamente, igual que markitdown_service.infrastructure.document_converter
aísla la librería MarkItDown)."""

from __future__ import annotations

import subprocess
from pathlib import Path

DRM_MARKERS = (
    "drm",
    "encrypted",
    "adept",
    "cannot be converted due to drm",
)


def is_drm_error(stderr_text: str) -> bool:
    """Detecta si un fallo de Calibre se debe a protección DRM, a partir
    de su salida de error. Calibre no distingue esto con un código de
    salida propio, solo con el texto del mensaje."""
    lowered = stderr_text.lower()
    return any(marker in lowered for marker in DRM_MARKERS)


class CalibreConverter:
    """Ejecuta `ebook-convert` vía subprocess. No conoce metadatos EPUB,
    resolución de nombres de fichero ni reglas de negocio — solo sabe
    invocar el binario y devolver el resultado crudo."""

    def __init__(self, binary: str) -> None:
        self._binary = binary

    def convert(
        self,
        source_epub: Path,
        output_pdf: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        """Invoca `ebook-convert`. Lanza `subprocess.TimeoutExpired` si
        supera `timeout_seconds` — no lo captura, es responsabilidad de
        quien orquesta la conversión (services.conversion_service)."""
        command = [self._binary, str(source_epub), str(output_pdf)]
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
