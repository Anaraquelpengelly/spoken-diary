import os
import sys
from unittest.mock import MagicMock
import pytest

# 1. Add the project root directory to sys.path (keep your existing logic)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 2. Add this NEW fixture to mock env vars and dependencies
@pytest.fixture(scope="session", autouse=True)
def mock_env_vars():
    """
    Set mock environment variables and sys.modules BEFORE any test imports the app.
    This prevents the app from crashing due to missing .env file or making real network calls.
    """
    # Mock environment variables required by the app
    os.environ["DEEPGRAM_API_KEY"] = "fake_key"
    os.environ["PCLOUD_USERNAME"] = "fake_user"
    os.environ["PCLOUD_PASSWORD"] = "fake_pass"
    os.environ["APP_USERNAME"] = "admin"       # Added for login
    os.environ["APP_PASSWORD"] = "secret"      # Added for login

    # Mock external libraries to avoid ModuleNotFoundError or real connections
    # This assumes you don't want to actually load these heavy libraries during tests
    sys.modules["gradio"] = MagicMock()
    sys.modules["pcloud"] = MagicMock()
    sys.modules["deepgram"] = MagicMock()
