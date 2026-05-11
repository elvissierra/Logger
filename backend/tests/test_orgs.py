def _register_and_login(client, email="admin@example.com", password="password123"):
    client.post("/api/auth/register", json={"email": email, "password": password})
    client.post("/api/auth/login", json={"email": email, "password": password})


def test_validate_code_valid(client, db):
    from app.models.organization import Organization
    import uuid
    org = Organization(
        id=str(uuid.uuid4()),
        name="Acme",
        address="123 Main",
        phone="555-0000",
        headcount=5,
        invite_code="VALID123",
    )
    db.add(org)
    db.commit()

    resp = client.get("/api/orgs/validate-code?code=VALID123")
    assert resp.status_code == 200
    assert resp.json()["org_name"] == "Acme"


def test_validate_code_invalid(client):
    resp = client.get("/api/orgs/validate-code?code=NOSUCHCODE")
    assert resp.status_code == 404


def test_create_org(client):
    _register_and_login(client)
    resp = client.post("/api/orgs/", json={
        "name": "My Company",
        "address": "456 Business Ave",
        "phone": "555-9999",
        "headcount": 20
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Company"
    assert "invite_code" in data
    assert len(data["invite_code"]) > 4


def test_create_org_sets_admin_flag(client):
    _register_and_login(client)
    client.post("/api/orgs/", json={
        "name": "Corp", "address": "1 St", "phone": "555", "headcount": 1
    })
    me = client.get("/api/auth/me").json()
    assert me["is_org_admin"] is True
    assert me["account_type"] == "org_member"


def test_create_org_twice_fails(client):
    _register_and_login(client)
    client.post("/api/orgs/", json={
        "name": "Corp", "address": "1 St", "phone": "555", "headcount": 1
    })
    resp = client.post("/api/orgs/", json={
        "name": "Corp2", "address": "2 St", "phone": "556", "headcount": 2
    })
    assert resp.status_code == 400


def test_get_org_members_non_admin_forbidden(client):
    _register_and_login(client)
    resp = client.get("/api/orgs/members")
    assert resp.status_code == 403


def test_get_org_members_as_admin(client, db):
    from app.models.organization import Organization
    from app.models.user import User
    import uuid

    _register_and_login(client)
    me = client.get("/api/auth/me").json()

    org_resp = client.post("/api/orgs/", json={
        "name": "Corp", "address": "1 St", "phone": "555", "headcount": 5
    })
    org_id = org_resp.json()["id"]

    member = User(
        id=str(uuid.uuid4()),
        email="member@example.com",
        password_hash="x",
        org_id=org_id,
        account_type="org_member",
    )
    db.add(member)
    db.commit()

    resp = client.get("/api/orgs/members")
    assert resp.status_code == 200
    emails = [m["email"] for m in resp.json()]
    assert "member@example.com" in emails
    assert me["email"] in emails
