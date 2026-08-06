"""Serialización de un `ProcessingResult` a fichero (JSON o JSONL) —
aísla el formato de salida en disco del resto de capas."""

from __future__ import annotations

import json
from pathlib import Path

from pdf2chunks_service.domain.models import ProcessingResult


def write_result(result: ProcessingResult, output_dir: Path, output_format: str) -> Path | None:
    """Escribe los chunks de un `ProcessingResult` en la carpeta de salida.

    Devuelve la ruta del fichero escrito, o None si no había chunks que escribir.
    """
    if not result.chunks:
        return None

    stem = Path(result.source_file).stem
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_format == "jsonl":
        out_path = output_dir / f"{stem}.jsonl"
        with out_path.open("w", encoding="utf-8") as fh:
            for chunk in result.chunks:
                fh.write(json.dumps(chunk.to_dict(), ensure_ascii=False))
                fh.write("\n")
    else:
        out_path = output_dir / f"{stem}.json"
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump([c.to_dict() for c in result.chunks], fh, ensure_ascii=False, indent=2)

    return out_path
