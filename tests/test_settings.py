import pytest

from src.main import CONFIG_DIR, load_settings


def test_project_settings_yaml_loads_portfolio_cash_fields():
    settings = load_settings(CONFIG_DIR / "settings.example.yaml")

    assert settings["fx"]["USD_TWD"] == 32.0
    assert "cash_twd" in settings["portfolio"]
    assert "cash_usd" in settings["portfolio"]
    assert isinstance(settings["portfolio"]["cash_twd"], int | float)
    assert isinstance(settings["portfolio"]["cash_usd"], int | float)
    assert settings["portfolio"]["cash_twd"] >= 0
    assert settings["portfolio"]["cash_usd"] >= 0


def test_load_settings_raises_clear_error_for_missing_file(tmp_path):
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match="Settings file not found"):
        load_settings(missing_path)


def test_load_settings_rejects_empty_settings_file(tmp_path):
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty or invalid"):
        load_settings(settings_path)
