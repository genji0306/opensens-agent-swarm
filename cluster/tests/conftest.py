"""Pytest configuration for DarkLab agent tests.

The pyproject.toml sets pythonpath = ["agents"], which lets pytest resolve
imports like `from shared.models import Task`. This conftest provides
shared fixtures used across test modules.
"""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def darklab_home(tmp_path):
    """Provide a temporary DARKLAB_HOME with standard subdirectories."""
    for subdir in ("logs", "artifacts", "data", "keys"):
        (tmp_path / subdir).mkdir()
    return tmp_path


@pytest.fixture
def mock_settings(darklab_home):
    """Patch shared.config.settings with a test-safe configuration."""
    with patch("shared.config.settings") as ms:
        ms.darklab_home = darklab_home
        ms.darklab_role = "academic"
        ms.anthropic_api_key = "test-key"
        ms.openai_api_key = "test-key"
        ms.google_ai_api_key = "test-key"
        ms.perplexity_api_key = "test-key"
        ms.artifacts_dir = darklab_home / "artifacts"
        ms.logs_dir = darklab_home / "logs"
        ms.data_dir = darklab_home / "data"
        yield ms
