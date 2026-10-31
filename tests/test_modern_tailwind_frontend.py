"""
Test suite verifying the streamlined citizen architecture:
- Core citizen routes: /create_home, /map, /report, /landing, /login
- Legacy /dashboard and /profile redirect safely to /create_home for citizens
- Staff routes (/staff/dashboard, /users, /maintenance) strictly protected from citizens
"""

import pytest
from app.server import create_app
from database.db import init_db
from database.auth import ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN, create_user


@pytest.fixture
def auth_client(tmp_path):
    db_file = str(tmp_path / "test_streamlined.db")
    init_db(db_file)
    app = create_app(
        test_config={
            "TESTING": True,
            "AUTH_ENABLED_EXPLICIT": True,
            "AUTH_ENABLED": True,
            "DATABASE_PATH": db_file,
            "SECRET_KEY": "test-secret-key-streamlined-32chars",
        }
    )
    with app.test_client() as client:
        with app.app_context():
            create_user("test_admin", "AdminPass123!", role=ROLE_ADMIN, db_path=db_file)
            create_user("test_inspector", "InspectPass123!", role=ROLE_INSPECTOR, db_path=db_file)
            create_user("test_maint", "MaintPass123!", role=ROLE_MAINTENANCE, db_path=db_file)
            create_user("test_citizen", "CitizenPass123!", role=ROLE_CITIZEN, db_path=db_file)
        yield client


def login_as(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_unauthenticated_access_redirects(auth_client):
    """Unauthenticated users accessing staff routes are redirected to /login."""
    for path in ["/users", "/maintenance", "/staff/dashboard"]:
        res = auth_client.get(path)
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]


def test_citizen_routes_and_staff_isolation(auth_client):
    """Citizens have clean access to create_home, map, and report, and are barred from staff modules."""
    login_as(auth_client, "test_citizen", "CitizenPass123!")
    
    # Core citizen pages
    res_home = auth_client.get("/create_home")
    assert res_home.status_code == 200

    res_map = auth_client.get("/map")
    assert res_map.status_code == 200

    res_rep = auth_client.get("/report")
    assert res_rep.status_code == 200

    # /dashboard and /profile safely redirect citizen to /create_home
    res_dash = auth_client.get("/dashboard")
    assert res_dash.status_code == 302
    assert "/create_home" in res_dash.headers["Location"]

    res_prof = auth_client.get("/profile")
    assert res_prof.status_code == 302
    assert "/create_home" in res_prof.headers["Location"]

    # Staff routes blocked for citizens
    for staff_path in ["/users", "/maintenance", "/staff/dashboard"]:
        res_staff = auth_client.get(staff_path)
        assert res_staff.status_code == 302
        assert "restricted=1" in res_staff.headers["Location"]


def test_staff_portal_access(auth_client):
    """Administrators and staff can access their internal operations console."""
    login_as(auth_client, "test_admin", "AdminPass123!")

    res_staff = auth_client.get("/staff/dashboard")
    assert res_staff.status_code == 200
    assert "Municipal Operations Dashboard" in res_staff.get_data(as_text=True)

    res_users = auth_client.get("/users")
    assert res_users.status_code == 200

    res_maint = auth_client.get("/maintenance")
    assert res_maint.status_code == 200
