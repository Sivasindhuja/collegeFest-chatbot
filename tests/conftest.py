import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from api import index


@pytest.fixture
def client():
    return TestClient(index.app)


@pytest.fixture(autouse=True)
def reset_rate_limit_store():
    index._rate_limit_store.clear()
    yield
    index._rate_limit_store.clear()
