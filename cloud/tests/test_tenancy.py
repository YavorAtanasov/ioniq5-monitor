def test_one_tenant_cannot_read_anothers_series(client, account):
    owner = account()
    intruder = account(email="intruder@example.com")

    client.post(
        "/v1/ingest",
        json={
            "readings": [
                {
                    "measurement": "vehicle_status",
                    "timestamp": "2026-01-01T10:00:00+00:00",
                    "fields": {"soc_pct": 80.0},
                    "tags": {},
                }
            ]
        },
        headers=owner["agent_headers"],
    )

    response = client.get(
        f"/v1/vehicles/{owner['vehicle_id']}/series",
        params={"measurement": "vehicle_status"},
        headers=intruder["headers"],
    )
    assert response.status_code == 404


def test_one_tenant_cannot_enroll_against_anothers_vehicle(client, account):
    owner = account()
    intruder = account(email="intruder@example.com")

    response = client.post(
        f"/v1/vehicles/{owner['vehicle_id']}/enrollment-codes",
        headers=intruder["headers"],
    )
    assert response.status_code == 404


def test_vehicle_listing_is_scoped_to_the_org(client, account):
    account()
    intruder = account(email="intruder@example.com")

    vehicles = client.get("/v1/vehicles", headers=intruder["headers"]).json()
    assert [v["id"] for v in vehicles] == [intruder["vehicle_id"]]


def test_duplicate_signup_is_rejected(client, account):
    account()
    response = client.post(
        "/v1/auth/signup",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 409
