"""Tests run offline: no Nosana, no Ollama. Force the local backend before any
project module reads the environment (load_dotenv never overrides it)."""

import os

os.environ["MODEL_TYPE"] = "OLLAMA"
os.environ["OLLAMA_MODEL"] = "test-model"

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_selector():
    """Each test installs its own fake models; put the previous selector back."""
    from models import selector

    saved = selector._current
    yield
    selector._current = saved
