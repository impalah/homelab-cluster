import logging
from unittest.mock import MagicMock, patch

from apikey_service.logging_setup import audit_logger, setup_logging


def test_setup_logging_configures_audit_logger_without_real_network_io():
    # Se mockean el exporter y el processor para no abrir sockets de verdad
    # ni dejar un hilo en segundo plano intentando exportar a un collector
    # que no existe durante los tests.
    with (
        patch("apikey_service.logging_setup.OTLPLogExporter") as exporter_cls,
        patch("apikey_service.logging_setup.BatchLogRecordProcessor") as processor_cls,
    ):
        exporter_cls.return_value = MagicMock()
        processor_cls.return_value = MagicMock()

        setup_logging()

        exporter_cls.assert_called_once()
        processor_cls.assert_called_once_with(exporter_cls.return_value)

    assert audit_logger.level == logging.WARNING
    assert audit_logger.propagate is False
    assert len(audit_logger.handlers) >= 1
