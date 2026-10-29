import os
import tempfile

import pytest

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["DEAD_BUT_DREAMING_SECRET_KEY"] = "test"

import webapp  # noqa: E402
from ronovo_portfolio_auth.security_questions import QUESTIONS  # noqa: E402

PASSWORD = "longpassword"


@pytest.fixture
def client():
    return webapp.create_app().test_client()


def new_game(client, name="Azathoth", difficulty="quick"):
    return client.post("/api/new-game", json={"name": name, "difficulty": difficulty}).get_json()["save"]


def register(client, username):
    response = client.post("/api/register", json={"username": username, "password": PASSWORD,
                                                  "question": QUESTIONS[0], "answer": "blue"})
    assert response.status_code == 200, response.get_json()
