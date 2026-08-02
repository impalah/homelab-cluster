from whisper_service import main as main_module
from whisper_service.infrastructure import whisper_model as whisper_model_module


async def test_lifespan_loads_model_via_infrastructure_and_keeps_it_after_shutdown(monkeypatch):
    calls: list[tuple[str, str, str]] = []

    def fake_load_model(model_name: str, device: str, compute_type: str) -> str:
        calls.append((model_name, device, compute_type))
        return "fake-model"

    monkeypatch.setattr(main_module, "load_model", fake_load_model)
    monkeypatch.setattr(whisper_model_module, "_model", None)

    async with main_module.lifespan(main_module.app):
        assert whisper_model_module.get_model() == "fake-model"

    # El lifespan no limpia el modelo al salir, solo registra el apagado.
    assert whisper_model_module.get_model() == "fake-model"
    assert calls == [
        (
            main_module.settings.whisper_model,
            main_module.settings.whisper_device,
            main_module.settings.whisper_compute_type,
        )
    ]
