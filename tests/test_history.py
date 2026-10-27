import uuid

import pytest


@pytest.fixture
def account_with_history(client, make_account):
    """7 credits and 5 debits, created in this order: c0, d0, c1, d1, ... ."""
    acc = make_account()
    refs = []
    for i in range(7):
        client.post(f"/accounts/{acc['id']}/transactions",
                    json={"type": "credit", "amount": "100", "reference_id": f"c{i}"})
        refs.append(f"c{i}")
        if i < 5:
            client.post(f"/accounts/{acc['id']}/transactions",
                        json={"type": "debit", "amount": "10", "reference_id": f"d{i}"})
            refs.append(f"d{i}")
    return acc, refs


def history(client, account_id, **params):
    return client.get(f"/accounts/{account_id}/transactions", params=params)


def test_default_returns_both_types_newest_first(client, account_with_history):
    acc, refs = account_with_history
    resp = history(client, acc["id"], limit=100)
    assert resp.status_code == 200
    body = resp.json()
    assert [t["reference_id"] for t in body["data"]] == list(reversed(refs))
    created = [t["created_at"] for t in body["data"]]
    assert created == sorted(created, reverse=True)
    assert body["pagination"] == {"page": 1, "limit": 100, "total_records": 12, "total_pages": 1}


def test_default_page_and_limit(client, account_with_history):
    acc, _ = account_with_history
    body = history(client, acc["id"]).json()
    assert body["pagination"] == {"page": 1, "limit": 10, "total_records": 12, "total_pages": 2}
    assert len(body["data"]) == 10


def test_filter_credit(client, account_with_history):
    acc, _ = account_with_history
    body = history(client, acc["id"], type="credit").json()
    assert {t["type"] for t in body["data"]} == {"credit"}
    assert body["pagination"]["total_records"] == 7


def test_filter_debit(client, account_with_history):
    acc, _ = account_with_history
    body = history(client, acc["id"], type="debit").json()
    assert {t["type"] for t in body["data"]} == {"debit"}
    assert body["pagination"]["total_records"] == 5
    assert [t["reference_id"] for t in body["data"]] == ["d4", "d3", "d2", "d1", "d0"]


def test_pagination_metadata_and_pages(client, account_with_history):
    acc, refs = account_with_history
    newest_first = list(reversed(refs))
    pages = []
    for page in (1, 2, 3):
        body = history(client, acc["id"], page=page, limit=5).json()
        assert body["pagination"] == {"page": page, "limit": 5, "total_records": 12, "total_pages": 3}
        pages.append([t["reference_id"] for t in body["data"]])
    assert [len(p) for p in pages] == [5, 5, 2]
    assert sum(pages, []) == newest_first  # no gaps, no repeats


def test_page_past_the_end_is_empty(client, account_with_history):
    acc, _ = account_with_history
    body = history(client, acc["id"], page=99, limit=5).json()
    assert body["data"] == []
    assert body["pagination"]["total_pages"] == 3


def test_empty_history(client, make_account):
    acc = make_account()
    body = history(client, acc["id"]).json()
    assert body == {"data": [], "pagination": {"page": 1, "limit": 10, "total_records": 0, "total_pages": 0}}


def test_history_only_shows_own_account(client, make_account, account_with_history):
    other = make_account("Other", credit="5")
    body = history(client, other["id"]).json()
    assert body["pagination"]["total_records"] == 1


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page": -1}, {"page": "abc"}, {"limit": 0}, {"limit": 101}, {"limit": "x"}, {"page": "1.5"},
])
def test_invalid_pagination_is_400(client, make_account, params):
    acc = make_account()
    resp = history(client, acc["id"], **params)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_PAGINATION"


def test_invalid_type_filter_is_422(client, make_account):
    acc = make_account()
    resp = history(client, acc["id"], type="refund")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0]["field"] == "query.type"


def test_history_unknown_account_is_404(client):
    resp = history(client, str(uuid.uuid4()))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"
