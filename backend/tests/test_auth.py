def test_register_solo(client):
    resp = client.post("/api/auth/register", json={
        "email": "solo@example.com",
        "password": "password123"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["account_type"] == "solo"
    assert data["org_id"] is None
    assert data["is_org_admin"] is False


def test_register_with_valid_invite_code(client, db):
    from app.models.organization import Organization
    import uuid
    org = Organization(
        id=str(uuid.uuid4()),
        name="Acme Corp",
        address="123 Main St",
        phone="555-1234",
        headcount=10,
        invite_code="TESTCODE1",
    )
    db.add(org)
    db.commit()

    resp = client.post("/api/auth/register", json={
        "email": "member@example.com",
        "password": "password123",
        "invite_code": "TESTCODE1"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["account_type"] == "org_member"
    assert data["org_id"] == org.id
    assert data["is_org_admin"] is False


def test_register_with_invalid_invite_code(client):
    resp = client.post("/api/auth/register", json={
        "email": "bad@example.com",
        "password": "password123",
        "invite_code": "BADCODE"
    })
    assert resp.status_code == 400
    assert "invite code" in resp.json()["detail"].lower()


def test_register_duplicate_email(client):
    client.post("/api/auth/register", json={
        "email": "dup@example.com", "password": "password123"
    })
    resp = client.post("/api/auth/register", json={
        "email": "dup@example.com", "password": "password123"
    })
    assert resp.status_code in (400, 409)


def test_login_success(client):
    client.post("/api/auth/register", json={
        "email": "login@example.com", "password": "password123"
    })
    resp = client.post("/api/auth/login", json={
        "email": "login@example.com", "password": "password123"
    })
    assert resp.status_code == 200
    assert resp.json()["email"] == "login@example.com"
