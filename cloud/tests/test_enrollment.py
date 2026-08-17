def test_enrollment_code_is_single_use(client, account):
    acct = account()
    code = client.post(
        f"/v1/vehicles/{acct['vehicle_id']}/enrollment-codes", headers=acct["headers"]
    ).json()["code"]

    assert client.post("/v1/agents/enroll", json={"code": code}).status_code == 201
    assert client.post("/v1/agents/enroll", json={"code": code}).status_code == 400


def test_unknown_enrollment_code_is_rejected(client):
    response = client.post("/v1/agents/enroll", json={"code": "AAAA-BBBB-CCCC"})
    assert response.status_code == 400


def test_api_key_is_never_returned_again(client, account):
    acct = account()
    agents = client.get(
        f"/v1/vehicles/{acct['vehicle_id']}/agents", headers=acct["headers"]
    ).json()

    assert len(agents) == 1
    assert acct["api_key"].startswith(agents[0]["key_prefix"])
    assert acct["api_key"] not in str(agents)


def test_revoked_agent_cannot_ingest(client, account):
    acct = account()
    agent_id = client.get(
        f"/v1/vehicles/{acct['vehicle_id']}/agents", headers=acct["headers"]
    ).json()[0]["id"]

    client.delete(
        f"/v1/vehicles/{acct['vehicle_id']}/agents/{agent_id}", headers=acct["headers"]
    )

    response = client.post(
        "/v1/ingest",
        json={"readings": [_reading()]},
        headers=acct["agent_headers"],
    )
    assert response.status_code == 401


def _reading():
    return {
        "measurement": "vehicle_status",
        "timestamp": "2026-01-01T10:00:00+00:00",
        "fields": {"soc_pct": 80.0},
        "tags": {},
    }
