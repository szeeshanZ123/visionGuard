"""
Test suite verifying the new modern Tailwind frontend architecture:
- /dashboard (Modern Administrative & Authority Operations Dashboard)
- /users (User Access & Role Management Console)
- /maintenance (Maintenance Work Order Dispatch Queue)
- Role-based access and security guards
- Dynamic telemetry placeholders (Neon PostgreSQL & Google Gemini Vision)
"""

import pytest
from app.server import create_app
from database.db import init_db
from database.auth import ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN, create_user


@pytest.fixture
def auth_client(tmp_path):
    db_file = str(tmp_path / "test_modern_fe.db")
    init_db(db_file)
    app = create_app(
        test_config={
            "TESTING": True,
            "AUTH_ENABLED_EXPLICIT": True,
            "AUTH_ENABLED": True,
            "DATABASE_PATH": db_file,
            "SECRET_KEY": "test-secret-key-modern-tailwind-frontend-32chars",
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
    """Unauthenticated users must be redirected to /login with return query parameter."""
    for path in ["/dashboard", "/users", "/maintenance"]:
        res = auth_client.get(path)
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]


def test_citizen_access_restricted(auth_client):
    """Citizens cannot access internal administrative pages."""
    login_as(auth_client, "test_citizen", "CitizenPass123!")
    
    res = auth_client.get("/dashboard")
    assert res.status_code == 302
    assert "/create_home" in res.headers["Location"]

    res = auth_client.get("/users")
    assert res.status_code == 302

    res = auth_client.get("/maintenance")
    assert res.status_code == 302


def test_admin_access_allowed(auth_client):
    """Administrators have access to dashboard, users, and maintenance."""
    login_as(auth_client, "test_admin", "AdminPass123!")

    # 1. Modern Dashboard
    res_dash = auth_client.get("/dashboard")
    assert res_dash.status_code == 200
    html_dash = res_dash.get_data(as_text=True)
    assert "Municipal Operations Dashboard" in html_dash
    assert "Live Infrastructure Telemetry" in html_dash
    assert "Distress Classification" in html_dash

    # 2. User Management
    res_users = auth_client.get("/users")
    assert res_users.status_code == 200
    html_users = res_users.get_data(as_text=True)
    assert "User Access & Role Management" in html_users
    assert "Create Staff User" in html_users

    # 3. Maintenance Queue
    res_maint = auth_client.get("/maintenance")
    assert res_maint.status_code == 200
    html_maint = res_maint.get_data(as_text=True)
    assert "Maintenance Work Orders" in html_maint
    assert "Overdue Repairs" in html_maint


def test_maintenance_staff_access(auth_client):
    """Maintenance staff can access dashboard and maintenance queue, but not user management."""
    login_as(auth_client, "test_maint", "MaintPass123!")

    res_dash = auth_client.get("/dashboard")
    assert res_dash.status_code == 200

    res_maint = auth_client.get("/maintenance")
    assert res_maint.status_code == 200

    # Restricted from user management
    res_users = auth_client.get("/users")
    assert res_users.status_code == 302
    assert "/dashboard" in res_users.headers["Location"]


def test_inspector_access(auth_client):
    """Inspectors can access dashboard, but not user management or maintenance queue."""
    login_as(auth_client, "test_inspector", "InspectPass123!")

    res_dash = auth_client.get("/dashboard")
    assert res_dash.status_code == 200

    res_users = auth_client.get("/users")
    assert res_users.status_code == 302

    res_maint = auth_client.get("/maintenance")
    assert res_maint.status_code == 302
