import importlib.util
from pathlib import Path


def test_streamlit_app_imports_without_running_ui():
    app_path = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
    spec = importlib.util.spec_from_file_location("streamlit_app_smoke", app_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    assert hasattr(module, "main")
    assert hasattr(module, "render_dashboard")
