import sys
import os
import os
import pytest
from unittest.mock import MagicMock

# Add the project root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture(scope="session", autouse=True)
def mock_env_vars():
    """Set mock env vars before any test runs"""
    os.environ["DEEPGRAM_API_KEY"] = "fake_key"
    os.environ["PCLOUD_USERNAME"] = "fake_user"
    os.environ["PCLOUD_PASSWORD"] = "fake_pass"

