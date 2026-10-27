import uuid


def test_create_account_starts_at_zero(client):
    resp = client.post("/accounts", json={"name": "Shalini"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Shalini"
    assert body["balance"] == "0.00"
    uuid.UUID(body["id"])  # id is a valid UUID
    assert body["created_at"]


def test_account_ids_are_unique(client):
    ids = {client.post("/accounts", json={"name": f"user {i}"}).json()["id"] for i in range(5)}
    assert len(ids) == 5


def test_client_cannot_set_balance(client):
    resp = client.post("/accounts", json={"name": "Hacker", "balance": 1000})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "balance" in resp.json()["error"]["message"]


def test_client_cannot_set_id_or_created_at(client):
    resp = client.post("/accounts", json={"name": "X", "id": str(uuid.uuid4()), "created_at": "2020-01-01T00:00:00Z"})
    assert resp.status_code == 422


def test_name_is_required(client):
    resp = client.post("/accounts", json={})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"][0]["field"] == "body.name"


def test_blank_name_rejected(client):
    assert client.post("/accounts", json={"name": "   "}).status_code == 422


def test_name_is_trimmed(client):
    assert client.post("/accounts", json={"name": "  Asha  "}).json()["name"] == "Asha"


def test_invalid_json_body(client):
    resp = client.post("/accounts", content="{not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_REQUEST_BODY"


def test_get_account_and_balance(client, make_account):
    acc = make_account("Ravi", credit="250.75")
    resp = client.get(f"/accounts/{acc['id']}")
    assert resp.status_code == 200
    assert resp.json()["balance"] == "250.75"

    resp = client.get(f"/accounts/{acc['id']}/balance")
    assert resp.status_code == 200
    assert resp.json() == {"account_id": acc["id"], "balance": "250.75"}


def test_balance_of_unknown_account_is_404(client):
    resp = client.get(f"/accounts/{uuid.uuid4()}/balance")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_malformed_account_id_is_422(client):
    resp = client.get("/accounts/not-a-uuid/balance")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
