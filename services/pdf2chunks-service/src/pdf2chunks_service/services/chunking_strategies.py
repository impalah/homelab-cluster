"""Estrategias de troceado (chunking) de texto — patrón Strategy.

`ChunkingStrategy` es la interfaz común, `FixedSizeChunkingStrategy` la
implementación por defecto. Para añadir una estrategia nueva (recursive,
semantic...), basta con subclasificar `ChunkingStrategy`, implementar
`split(text)` y registrarla en `get_chunking_strategy`."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ChunkingStrategy(ABC):
    """Interfaz común para las estrategias de troceado de texto."""

    @abstractmethod
    def split(self, text: str) -> list[str]:
        """Divide `text` (normalmente el texto de una página) en una lista
        de fragmentos no vacíos."""
        raise NotImplementedError


class FixedSizeChunkingStrategy(ChunkingStrategy):
    """Trocea el texto en ventanas de tamaño fijo (tokens aproximados por
    palabras) con un porcentaje de solapamiento configurable. Tokeniza por
    espacios en blanco y agrupa en ventanas deslizantes."""

    def __init__(self, chunk_size_tokens: int = 400, overlap_ratio: float = 0.15) -> None:
        if chunk_size_tokens <= 0:
            raise ValueError("chunk_size_tokens debe ser positivo")
        if not (0 <= overlap_ratio < 1):
            raise ValueError("overlap_ratio debe estar en el rango [0, 1)")

        self.chunk_size_tokens = chunk_size_tokens
        self.overlap_ratio = overlap_ratio
        self.overlap_tokens = int(chunk_size_tokens * overlap_ratio)

    def split(self, text: str) -> list[str]:
        tokens = text.split()
        if not tokens:
            return []

        step = max(1, self.chunk_size_tokens - self.overlap_tokens)
        chunks: list[str] = []
        start = 0
        n = len(tokens)

        while start < n:
            end = min(start + self.chunk_size_tokens, n)
            fragment = " ".join(tokens[start:end])
            if fragment.strip():
                chunks.append(fragment)
            if end == n:
                break
            start += step

        return chunks


def get_chunking_strategy(
    name: str,
    *,
    chunk_size_tokens: int = 400,
    overlap_ratio: float = 0.15,
) -> ChunkingStrategy:
    """Factory que resuelve el nombre de estrategia (vía configuración) a
    una instancia. Solo "fixed_size" está implementada; "recursive" y
    "semantic" están reservadas como puntos de extensión futuros."""
    normalized = name.strip().lower()

    if normalized == "fixed_size":
        return FixedSizeChunkingStrategy(
            chunk_size_tokens=chunk_size_tokens, overlap_ratio=overlap_ratio
        )
    if normalized in {"recursive", "semantic"}:
        raise ValueError(
            f"La estrategia de chunking '{normalized}' está reservada como punto de "
            "extensión futuro pero aún no está implementada."
        )
    raise ValueError(f"Estrategia de chunking desconocida: '{name}'")
