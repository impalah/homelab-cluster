"""Tests para pdf2chunks_service.services.chunking_strategies."""

from __future__ import annotations

import pytest

from pdf2chunks_service.services.chunking_strategies import (
    ChunkingStrategy,
    FixedSizeChunkingStrategy,
    get_chunking_strategy,
)


def test_fixed_size_split_basic():
    strategy = FixedSizeChunkingStrategy(chunk_size_tokens=5, overlap_ratio=0.2)
    text = "one two three four five six seven eight nine ten"
    chunks = strategy.split(text)

    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)
    assert len(chunks[0].split()) == 5


def test_fixed_size_split_empty_text():
    strategy = FixedSizeChunkingStrategy(chunk_size_tokens=10, overlap_ratio=0.1)
    assert strategy.split("") == []
    assert strategy.split("   ") == []


def test_fixed_size_split_short_text_single_chunk():
    strategy = FixedSizeChunkingStrategy(chunk_size_tokens=100, overlap_ratio=0.15)
    text = "solo unas pocas palabras"
    chunks = strategy.split(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_fixed_size_overlap_produces_repeated_tokens():
    strategy = FixedSizeChunkingStrategy(chunk_size_tokens=4, overlap_ratio=0.5)
    tokens = [f"tok{i}" for i in range(12)]
    text = " ".join(tokens)
    chunks = strategy.split(text)

    assert len(chunks) > 1
    first_tokens = chunks[0].split()
    second_tokens = chunks[1].split()
    overlap = set(first_tokens) & set(second_tokens)
    assert len(overlap) > 0


def test_invalid_chunk_size_raises():
    with pytest.raises(ValueError):
        FixedSizeChunkingStrategy(chunk_size_tokens=0)
    with pytest.raises(ValueError):
        FixedSizeChunkingStrategy(chunk_size_tokens=-5)


def test_invalid_overlap_ratio_raises():
    with pytest.raises(ValueError):
        FixedSizeChunkingStrategy(chunk_size_tokens=10, overlap_ratio=1.0)
    with pytest.raises(ValueError):
        FixedSizeChunkingStrategy(chunk_size_tokens=10, overlap_ratio=-0.1)


def test_get_chunking_strategy_fixed_size():
    strategy = get_chunking_strategy("fixed_size", chunk_size_tokens=400, overlap_ratio=0.15)
    assert isinstance(strategy, FixedSizeChunkingStrategy)
    assert isinstance(strategy, ChunkingStrategy)


def test_get_chunking_strategy_case_insensitive():
    strategy = get_chunking_strategy("FIXED_SIZE")
    assert isinstance(strategy, FixedSizeChunkingStrategy)


@pytest.mark.parametrize("name", ["recursive", "semantic"])
def test_get_chunking_strategy_reserved_not_implemented(name):
    with pytest.raises(ValueError, match="reservada"):
        get_chunking_strategy(name)


def test_get_chunking_strategy_unknown_raises():
    with pytest.raises(ValueError, match="desconocida"):
        get_chunking_strategy("no-existe")


def test_chunking_strategy_is_abstract():
    with pytest.raises(TypeError):
        ChunkingStrategy()  # type: ignore[abstract]
