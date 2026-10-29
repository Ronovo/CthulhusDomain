import pytest

import webapp
from helpers import SECRET_KEY


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DEAD_BUT_DREAMING_SECRET_KEY", SECRET_KEY)
    return webapp.create_app().test_client()
