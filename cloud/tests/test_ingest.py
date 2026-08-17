from datetime import datetime, timedelta, timezone


def reading(ts="2026-01-01T10:00:00+00:00", soc=80.0, tags=None):
    return {
        "measurement": "vehicle_status",
        "timestamp": ts,
        "fields": {"soc_pct": soc},
        "tags": tags or {},
    }


def test_ingest_stores_readings_against_the_agents_vehicle(client, account):
    acct = account()

    response = client.post(
        "/v1/ingest", json={"readings": [reading()]}, headers=acct["agent_headers"]
    )
    assert response.json() == {"accepted": 1, "updated": 0, "rejected": 0}

    points = client.get(
        f"/v1/vehicles/{acct['vehicle_id']}/series",
        params={"measurement": "vehicle_status"},
        headers=acct["headers"],
    ).json()["points"]
    assert [p["fields"]["soc_pct"] for p in points] == [80.0]


def test_replayed_readings_update_rather_than_duplicate(client, account):
    acct = account()
    client.post(
        "/v1/ingest", json={"readings": [reading()]}, headers=acct["agent_headers"]
    )

    response = client.post(
        "/v1/ingest",
        json={"readings": [reading(soc=81.0)]},
        headers=acct["agent_headers"],
    )
    assert response.json() == {"accepted": 0, "updated": 1, "rejected": 0}

    points = client.get(
        f"/v1/vehicles/{acct['vehicle_id']}/series",
        params={"measurement": "vehicle_status"},
        headers=acct["headers"],
    ).json()["points"]
    assert [p["fields"]["soc_pct"] for p in points] == [81.0]


def test_readings_differing_only_by_tags_are_distinct(client, account):
    acct = account()
    client.post(
        "/v1/ingest",
        json={
            "readings": [
                reading(tags={"trip_index": "0"}),
                reading(tags={"trip_index": "1"}),
            ]
        },
        headers=acct["agent_headers"],
    )

    points = client.get(
        f"/v1/vehicles/{acct['vehicle_id']}/series",
        params={"measurement": "vehicle_status"},
        headers=acct["headers"],
    ).json()["points"]
    assert len(points) == 2


def test_far_future_readings_are_rejected(client, account):
    acct = account()
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    response = client.post(
        "/v1/ingest",
        json={"readings": [reading(ts=future)]},
        headers=acct["agent_headers"],
    )
    assert response.json()["rejected"] == 1


def test_client_supplied_vehicle_tag_cannot_redirect_a_reading(client, account):
    """The agent's key decides the vehicle - the payload never does."""
    acct = account()
    other = account(email="other@example.com")

    payload = reading()
    payload["vehicle"] = other["vehicle_id"]
    client.post(
        "/v1/ingest", json={"readings": [payload]}, headers=acct["agent_headers"]
    )

    other_points = client.get(
        f"/v1/vehicles/{other['vehicle_id']}/series",
        params={"measurement": "vehicle_status"},
        headers=other["headers"],
    ).json()["points"]
    assert other_points == []


def test_ingest_requires_an_agent_key(client):
    assert client.post("/v1/ingest", json={"readings": [reading()]}).status_code == 401
