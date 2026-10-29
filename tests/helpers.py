from ronovo_portfolio_auth.security_questions import QUESTIONS

from signing import Signer

SECRET_KEY = "test"
PASSWORD = "longpassword"
ANSWER = "blue"
signer = Signer(SECRET_KEY)


def new_game(client, name="Azathoth", difficulty="quick"):
    return client.post("/api/new-game", json={"name": name, "difficulty": difficulty}).get_json()["save"]


def register(client, username="pilot"):
    response = client.post("/api/register", json={"username": username, "password": PASSWORD,
                                                  "question": QUESTIONS[0], "answer": ANSWER})
    assert response.status_code == 200, response.get_json()


def play(client, save, record=None, actions=(), backup=False):
    return client.post("/api/play", json={"save": save, "record": record, "actions": list(actions), "backup": backup})


def sync(client, *saves, deleted=(), record=None):
    return client.post("/api/sync", json={"saves": {str(n): save for n, save in enumerate(saves)},
                                          "deleted": list(deleted), "record": record}).get_json()
