from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.external import ExternalChit


def _subscriber_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"phone": "8888888888", "password": "pass123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_create_external_chit(app, db_session):
    client = TestClient(app)
    response = client.post(
        "/api/external-chits",
        headers=_subscriber_headers(client),
        json={
            "title": "Neighbourhood Chit",
            "name": "Neighbourhood Ledger",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 20,
            "userSlots": 2,
            "firstMonthOrganizer": True,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "endDate": None,
            "notes": "",
            "status": "active",
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Neighbourhood Chit"
    assert response.json()["name"] == "Neighbourhood Ledger"
    assert response.json()["monthlyInstallment"] == 10000
    assert response.json()["totalMembers"] == 10
    assert response.json()["totalMonths"] == 20
    assert response.json()["userSlots"] == 2
    assert response.json()["firstMonthOrganizer"] is True
    assert response.json()["notes"] is None
    assert response.json()["endDate"] is None
    external_chit = db_session.scalar(select(ExternalChit).where(ExternalChit.title == "Neighbourhood Chit"))
    assert external_chit is not None


def test_list_external_chits_for_subscriber(app):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Neighbourhood Chit",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "endDate": None,
            "notes": "",
            "status": "active",
        },
    )
    assert create_response.status_code == 201
    response = client.get("/api/external-chits", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Neighbourhood Chit"
    assert body[0]["notes"] is None
    assert body[0]["endDate"] is None

    paginated = client.get("/api/external-chits?page=1&pageSize=1", headers=headers)
    assert paginated.status_code == 200
    paginated_body = paginated.json()
    assert paginated_body["page"] == 1
    assert paginated_body["pageSize"] == 1
    assert len(paginated_body["items"]) == 1


def test_external_chit_detail_returns_entry_history(app, db_session):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Neighbourhood Chit",
            "name": "Neighbourhood Ledger",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 20,
            "userSlots": 2,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "endDate": None,
            "notes": "Outside record",
            "status": "active",
        },
    )
    assert create_response.status_code == 201
    chit_id = create_response.json()["id"]

    entry_response = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "won",
            "entryDate": "2026-04-20",
            "amount": 20000,
            "description": "First month result",
            "monthNumber": 2,
            "bidAmount": 20000,
            "winnerType": "SELF",
            "sharePerSlot": 2500,
            "myShare": 5000,
        },
    )
    assert entry_response.status_code == 201

    detail_response = client.get(f"/api/external-chits/{chit_id}", headers=headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["notes"] == "Outside record"
    assert len(detail["entryHistory"]) == 1
    assert detail["entryHistory"][0]["description"] == "First month result"
    assert detail["entryHistory"][0]["monthNumber"] == 2
    assert detail["entryHistory"][0]["bidAmount"] == 20000
    assert detail["entryHistory"][0]["winnerType"] == "SELF"
    assert detail["entryHistory"][0]["sharePerSlot"] == 2500
    assert detail["entryHistory"][0]["myShare"] == 5000
    assert detail["entryHistory"][0]["myPayable"] == 15000
    assert detail["entryHistory"][0]["myPayout"] == 65000
    assert detail["entryHistory"][0]["isShareOverridden"] is True


def test_external_chit_entry_update_returns_stored_monthly_values(app):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Editable External Chit",
            "name": "Editable Ledger",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 20,
            "userSlots": 2,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "status": "active",
        },
    )
    chit_id = create_response.json()["id"]
    entry_response = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "won",
            "entryDate": "2026-04-20",
            "amount": 20000,
            "description": "Initial month result",
            "monthNumber": 2,
            "bidAmount": 20000,
            "winnerType": "OTHER",
        },
    )
    assert entry_response.status_code == 201
    entry_id = entry_response.json()["id"]

    update_response = client.put(
        f"/api/external-chits/{chit_id}/entries/{entry_id}",
        headers=headers,
        json={
            "winnerType": "SELF",
            "sharePerSlot": 2500,
            "myShare": 5000,
        },
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["entryType"] == "won"
    assert body["entryDate"] == "2026-04-20"
    assert body["amount"] == 20000.0
    assert body["description"] == "Initial month result"
    assert body["monthNumber"] == 2
    assert body["bidAmount"] == 20000
    assert body["winnerType"] == "SELF"
    assert body["sharePerSlot"] == 2500
    assert body["myShare"] == 5000
    assert body["myPayable"] == 15000
    assert body["myPayout"] == 65000
    assert body["isShareOverridden"] is True


def test_external_chit_entry_update_only_changes_explicit_fields(app):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Partial Update Chit",
            "name": "Partial Update Ledger",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 20,
            "userSlots": 2,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "status": "active",
        },
    )
    chit_id = create_response.json()["id"]
    entry_response = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "won",
            "entryDate": "2026-04-20",
            "amount": 20000,
            "description": "Keep my base fields",
            "monthNumber": 2,
            "bidAmount": 20000,
            "winnerType": "OTHER",
        },
    )
    entry_id = entry_response.json()["id"]

    update_response = client.put(
        f"/api/external-chits/{chit_id}/entries/{entry_id}",
        headers=headers,
        json={
            "myPayable": 12000,
        },
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["entryType"] == "won"
    assert body["entryDate"] == "2026-04-20"
    assert body["amount"] == 20000.0
    assert body["description"] == "Keep my base fields"
    assert body["monthNumber"] == 2
    assert body["bidAmount"] == 20000
    assert body["winnerType"] == "OTHER"
    assert body["myPayable"] == 12000
    assert body["isPayableOverridden"] is True


def test_external_chit_entry_create_allows_missing_bid_for_monthly_ledger(app):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Missing Bid External Chit",
            "name": "Missing Bid Ledger",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 20,
            "userSlots": 2,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "status": "active",
        },
    )
    chit_id = create_response.json()["id"]

    entry_response = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "paid",
            "entryDate": "2026-04-20",
            "amount": None,
            "description": "Month saved before bid",
            "monthNumber": 2,
            "bidAmount": None,
            "winnerType": "OTHER",
        },
    )

    assert entry_response.status_code == 201
    body = entry_response.json()
    assert body["amount"] is None
    assert body["bidAmount"] is None
    assert body["sharePerSlot"] == 0
    assert body["myShare"] == 0
    assert body["myPayable"] == 0
    assert body["myPayout"] == 0


def test_external_chit_entry_create_rejects_duplicate_and_out_of_order_months(app):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Validated External Chit",
            "name": "Validated Ledger",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 20,
            "userSlots": 2,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "status": "active",
        },
    )
    chit_id = create_response.json()["id"]

    month_three = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "paid",
            "entryDate": "2026-04-20",
            "amount": 20000,
            "description": "Month three",
            "monthNumber": 3,
            "bidAmount": 20000,
            "winnerType": "OTHER",
        },
    )
    assert month_three.status_code == 201

    out_of_order = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "paid",
            "entryDate": "2026-04-15",
            "amount": 18000,
            "description": "Month two added later",
            "monthNumber": 2,
            "bidAmount": 18000,
            "winnerType": "OTHER",
        },
    )
    assert out_of_order.status_code == 422
    assert out_of_order.json()["detail"] == "Month entries must be added in ascending order"

    duplicate = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "paid",
            "entryDate": "2026-04-22",
            "amount": 22000,
            "description": "Duplicate month three",
            "monthNumber": 3,
            "bidAmount": 22000,
            "winnerType": "OTHER",
        },
    )
    assert duplicate.status_code == 422
    assert duplicate.json()["detail"] == "Month number already exists for this chit"


def test_external_chit_entries_support_pagination(app):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Paged External Chit",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "endDate": None,
            "notes": "",
            "status": "active",
        },
    )
    chit_id = create_response.json()["id"]
    client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={"entryType": "note", "entryDate": "2026-04-20", "amount": None, "description": "First"},
    )
    client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={"entryType": "note", "entryDate": "2026-04-21", "amount": None, "description": "Second"},
    )

    response = client.get(f"/api/external-chits/{chit_id}/entries?page=1&pageSize=1", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["pageSize"] == 1
    assert len(body["items"]) == 1


def test_external_chit_summary_returns_totals_profit_and_winning_month(app):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Summary External Chit",
            "name": "Summary Ledger",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 20,
            "userSlots": 2,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "status": "active",
        },
    )
    chit_id = create_response.json()["id"]

    month_one = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "won",
            "entryDate": "2026-04-10",
            "amount": 20000,
            "description": "Month one result",
            "monthNumber": 1,
            "bidAmount": 20000,
            "winnerType": "OTHER",
        },
    )
    assert month_one.status_code == 201

    month_two = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "won",
            "entryDate": "2026-04-20",
            "amount": 18000,
            "description": "Month two result",
            "monthNumber": 2,
            "bidAmount": 18000,
            "winnerType": "SELF",
            "myPayable": 13000,
        },
    )
    assert month_two.status_code == 201

    summary_response = client.get(f"/api/external-chits/{chit_id}/summary", headers=headers)

    assert summary_response.status_code == 200
    body = summary_response.json()
    assert body == {
        "totalPaid": 29000,
        "totalReceived": 73200,
        "profit": 44200,
        "winningMonth": 2,
    }


def test_external_chit_summary_defaults_to_zero_without_entries(app):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Empty Summary Chit",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 20,
            "userSlots": 2,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "status": "active",
        },
    )
    chit_id = create_response.json()["id"]

    summary_response = client.get(f"/api/external-chits/{chit_id}/summary", headers=headers)

    assert summary_response.status_code == 200
    assert summary_response.json() == {
        "totalPaid": 0,
        "totalReceived": 0,
        "profit": 0,
        "winningMonth": None,
    }


def test_external_chit_three_month_flow_keeps_totals_and_types_consistent(app):
    client = TestClient(app)
    headers = _subscriber_headers(client)
    create_response = client.post(
        "/api/external-chits",
        headers=headers,
        json={
            "title": "Integration External Chit",
            "name": "Integration Ledger",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "monthlyInstallment": 10000,
            "totalMembers": 10,
            "totalMonths": 12,
            "userSlots": 2,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "status": "active",
        },
    )
    assert create_response.status_code == 201
    chit_id = create_response.json()["id"]

    month_one = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "paid",
            "entryDate": "2026-04-05",
            "amount": 20000,
            "description": "Month one ledger entry",
            "monthNumber": 1,
            "bidAmount": 20000,
            "winnerType": "OTHER",
        },
    )
    assert month_one.status_code == 201
    month_one_body = month_one.json()
    assert month_one_body["sharePerSlot"] == 2000
    assert month_one_body["myShare"] == 4000
    assert month_one_body["myPayable"] == 16000
    assert month_one_body["myPayout"] == 0

    month_two = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "won",
            "entryDate": "2026-04-10",
            "amount": 18000,
            "description": "Month two ledger entry",
            "monthNumber": 2,
            "bidAmount": 18000,
            "winnerType": "SELF",
        },
    )
    assert month_two.status_code == 201
    month_two_body = month_two.json()
    assert month_two_body["sharePerSlot"] == 1800
    assert month_two_body["myShare"] == 3600
    assert month_two_body["myPayable"] == 16400
    assert month_two_body["myPayout"] == 65600

    month_three = client.post(
        f"/api/external-chits/{chit_id}/entries",
        headers=headers,
        json={
            "entryType": "paid",
            "entryDate": "2026-04-15",
            "amount": 15000,
            "description": "Month three ledger entry",
            "monthNumber": 3,
            "bidAmount": 15000,
            "winnerType": "OTHER",
            "myPayable": 16800,
        },
    )
    assert month_three.status_code == 201
    month_three_body = month_three.json()
    assert month_three_body["sharePerSlot"] == 1500
    assert month_three_body["myShare"] == 3000
    assert month_three_body["myPayable"] == 16800
    assert month_three_body["myPayout"] == 0
    assert month_three_body["isPayableOverridden"] is True

    detail_response = client.get(f"/api/external-chits/{chit_id}", headers=headers)
    summary_response = client.get(f"/api/external-chits/{chit_id}/summary", headers=headers)

    assert detail_response.status_code == 200
    assert summary_response.status_code == 200

    detail = detail_response.json()
    summary = summary_response.json()

    assert [entry["monthNumber"] for entry in detail["entryHistory"]] == [1, 2, 3]
    assert summary == {
        "totalPaid": 49200,
        "totalReceived": 76200,
        "profit": 27000,
        "winningMonth": 2,
    }

    for entry in detail["entryHistory"]:
        assert isinstance(entry["sharePerSlot"], int)
        assert isinstance(entry["myShare"], int)
        assert isinstance(entry["myPayable"], int)
        assert isinstance(entry["myPayout"], int)

    assert isinstance(summary["totalPaid"], int)
    assert isinstance(summary["totalReceived"], int)
    assert isinstance(summary["profit"], int)
