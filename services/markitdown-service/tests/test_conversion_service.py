from unittest.mock import MagicMock

import pytest

from markitdown_service.services.conversion_service import (
    ConversionFailedError,
    ConversionProducedNoContentError,
    ConversionService,
    EmptyFileError,
    FileTooLargeError,
    UnsupportedFormatError,
)


@pytest.fixture
def mock_converter():
    converter = MagicMock()
    converter.convert.return_value = "# Hello\n\nWorld"
    return converter


@pytest.fixture
def service(mock_converter):
    return ConversionService(mock_converter, max_file_size=52_428_800)


def test_convert_returns_result_for_supported_extension(service, mock_converter):
    result = service.convert(b"contenido", "documento.txt")

    assert result.filename == "documento.txt"
    assert result.extension == ".txt"
    assert result.size_bytes == len(b"contenido")
    assert result.markdown == "# Hello\n\nWorld"
    assert result.characters == len("# Hello\n\nWorld")
    mock_converter.convert.assert_called_once()


def test_convert_rejects_unsupported_extension(service):
    with pytest.raises(UnsupportedFormatError) as exc_info:
        service.convert(b"whatever", "virus.exe")

    assert exc_info.value.extension == ".exe"


def test_convert_rejects_empty_file(service):
    with pytest.raises(EmptyFileError):
        service.convert(b"", "vacio.txt")


def test_convert_rejects_file_over_max_size(mock_converter):
    service = ConversionService(mock_converter, max_file_size=10)

    with pytest.raises(FileTooLargeError) as exc_info:
        service.convert(b"esto es mas de diez bytes", "grande.txt")

    assert exc_info.value.size_bytes == len(b"esto es mas de diez bytes")
    assert exc_info.value.max_bytes == 10


def test_convert_raises_when_no_content_produced(service, mock_converter):
    mock_converter.convert.return_value = "   "

    with pytest.raises(ConversionProducedNoContentError):
        service.convert(b"contenido", "vacio.txt")


def test_convert_raises_conversion_failed_on_generic_error(service, mock_converter):
    mock_converter.convert.side_effect = RuntimeError("boom")

    with pytest.raises(ConversionFailedError) as exc_info:
        service.convert(b"contenido", "documento.txt")

    assert "boom" in str(exc_info.value)


def test_convert_without_extension_still_attempts_conversion(service, mock_converter):
    mock_converter.convert.return_value = "Plain content"

    result = service.convert(b"Plain content", "noext")

    assert result.extension == "desconocida"
    assert result.markdown == "Plain content"


def test_convert_cleans_up_temp_file_even_when_conversion_fails(
    service, mock_converter, monkeypatch
):
    # El "finally" borra el temporal incluso si la conversión falla — se
    # comprueba interceptando os.unlink en el módulo del service.
    import markitdown_service.services.conversion_service as conversion_service_module

    unlink_calls: list[str] = []
    monkeypatch.setattr(conversion_service_module.os, "unlink", unlink_calls.append)
    mock_converter.convert.side_effect = RuntimeError("boom")

    with pytest.raises(ConversionFailedError):
        service.convert(b"contenido", "documento.txt")

    assert len(unlink_calls) == 1


def test_convert_ignores_failure_cleaning_up_the_temp_file(service, mock_converter, monkeypatch):
    # Igual que arriba pero además el propio borrado falla — no debe tapar
    # el resultado correcto de una conversión que sí tuvo éxito.
    import markitdown_service.services.conversion_service as conversion_service_module

    def _raise(path: str) -> None:
        raise OSError("boom")

    monkeypatch.setattr(conversion_service_module.os, "unlink", _raise)

    result = service.convert(b"contenido", "documento.txt")

    assert result.markdown == "# Hello\n\nWorld"
