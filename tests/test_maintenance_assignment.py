"""
VisionGuard AI - Phase 4.7: Maintenance Task Assignment and Team Workflow Test Suite.

Validates:
1. Task assignment creation by administrator to active Maintenance Staff.
2. Validation rules: invalid users, non-maintenance roles, and inactive accounts rejected.
3. Task reassignment with audit trail and cancellation of prior active assignments.
4. Task assignment cancellation by administrator.
5. Role authorization: only administrators can assign/reassign/cancel.
6. Maintenance Work Queue scoping: technicians only see tasks assigned to them; admins see all.
7. Cross-user access denial: preventing a technician from viewing or modifying another technician's task.
8. Status synchronization between workflow states and assignment states.
9. Queue filters: assignment status, deadline urgency, defect category, and location.
10. Legacy records preservation: unassigned inspections maintain NULL assignees.
11. Account deactivation safety and reassignment capability.
"""

import io
import json
import sqlite3
import pytest
import datetime
from unittest.mock import MagicMock

from database.db import (
    init_db,
    save_inspection,
    get_inspection_by_id,
    get_inspection_activity,
    update_inspection_status,
)
from database.auth import (
    ROLE_ADMIN,
    ROLE_INSPECTOR,
    ROLE_MAINTENANCE,
    create_user,
    update_user,
)
from database.assignments import (
    assign_inspection_task,
    cancel_inspection_assignment,
    get_maintenance_work_queue,
    get_inspection_assignment_history,
    list_active_maintenance_staff,
    check_user_can_maintain_inspection,
    ASSIGNMENT_STATUS_ASSIGNED,
    ASSIGNMENT_STATUS_IN_PROGRESS,
    ASSIGNMENT_STATUS_COMPLETED,
    ASSIGNMENT_STATUS_CANCELLED,
    ASSIGNMENT_STATUS_UNASSIGNED,
)
from app.server import create_app


@pytest.fixture
def test_db_path(tmp_path):
    """Provides a fresh isolated database path for each test."""
    db_file = tmp_path / "test_assignments.db"
    return str(db_file)


@pytest.fixture
def mock_detector():
    """Mock DefectDetectionService to avoid loading YOLO model in tests."""
    mock = MagicMock()
    mock.is_loaded = True
    mock.load_model.return_value = True
    mock.status_message = "Mock Detector Ready"
    mock.model_path = "models/best.pt"
    return mock


@pytest.fixture
def auth_app(test_db_path, mock_detector):
    """Creates a Flask application instance with authentication and CSRF strictly enforced."""
    app = create_app(
        detector=mock_detector,
        test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db_path,
            "AUTH_ENABLED": True,
            "ENFORCE_CSRF": True,
            "SECRET_KEY": "test-secret-key-32-chars-minimum-visionguard",
        }
    )
    return app


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


class TestMaintenanceTaskAssignments:
    @pytest.fixture(autouse=True)
    def setup_users_and_inspections(self, test_db_path):
        """Prepares users with discrete roles and baseline inspection records."""
        self.admin = create_user("super_admin", "AdminPassword123", role=ROLE_ADMIN, db_path=test_db_path)
        self.inspector = create_user("field_inspector", "InspectorPassword123", role=ROLE_INSPECTOR, db_path=test_db_path)
        self.tech_alice = create_user("tech_alice", "AlicePassword123", role=ROLE_MAINTENANCE, email="alice@visionguard.gov", db_path=test_db_path)
        self.tech_bob = create_user("tech_bob", "BobPassword123", role=ROLE_MAINTENANCE, email="bob@visionguard.gov", db_path=test_db_path)

        self.inspection1 = save_inspection({
            "image_name": "pothole_main_st.jpg",
            "road_name": "Main Street",
            "area": "Downtown",
            "city": "Metropolis",
            "status": "Open",
            "defect_count": 2,
            "defect_type": "Pothole",
            "target_repair_date": (datetime.date.today() + datetime.timedelta(days=3)).isoformat(),
        }, db_path=test_db_path)

        self.inspection2 = save_inspection({
            "image_name": "crack_highway.jpg",
            "road_name": "Highway 101",
            "area": "North Sector",
            "city": "Metropolis",
            "status": "Open",
            "defect_count": 1,
            "defect_type": "Longitudinal Crack",
            "target_repair_date": (datetime.date.today() - datetime.timedelta(days=2)).isoformat(),
        }, db_path=test_db_path)

    def _login(self, client, username, password):
        res = client.post("/api/auth/login", json={"username": username, "password": password})
        assert res.status_code == 200
        return res.get_json()["csrf_token"]

    def test_admin_can_assign_task_to_maintenance_user(self, client, test_db_path):
        """Admin assigns inspection to active Maintenance Staff user with instructions."""
        csrf = self._login(client, "super_admin", "AdminPassword123")

        res = client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={
                "assigned_to_user_id": self.tech_alice["id"],
                "instructions": "Inspect road shoulder and prepare cold-patch asphalt mix."
            },
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert "tech_alice" in data["message"]

        # Verify database fields
        insp = get_inspection_by_id(self.inspection1["id"], db_path=test_db_path)
        assert insp["assigned_to_user_id"] == self.tech_alice["id"]
        assert insp["assigned_to_username"] == "tech_alice"
        assert insp["assignment_status"] == ASSIGNMENT_STATUS_ASSIGNED
        assert insp["assignment_instructions"] == "Inspect road shoulder and prepare cold-patch asphalt mix."
        assert insp["assigned_by_user_id"] == self.admin["id"]

        # Verify audit activity log
        activities = get_inspection_activity(self.inspection1["id"], db_path=test_db_path)
        assign_act = [a for a in activities if a["action_type"] == "assigned"]
        assert len(assign_act) == 1
        assert "tech_alice" in assign_act[0]["notes"]
        assert assign_act[0]["user_id"] == self.admin["id"]

        # Verify maintenance_assignments table
        assignments = get_inspection_assignment_history(self.inspection1["id"], db_path=test_db_path)
        assert len(assignments) == 1
        assert assignments[0]["assigned_to_username"] == "tech_alice"
        assert assignments[0]["status"] == "assigned"

    def test_assign_to_invalid_or_non_maintenance_user_fails(self, client):
        """Task assignment rejected for non-existent users, inspectors, or administrators."""
        csrf = self._login(client, "super_admin", "AdminPassword123")

        # 1. Non-existent user
        res1 = client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={"assigned_to_user_id": 99999},
            headers={"X-CSRF-Token": csrf}
        )
        assert res1.status_code == 400
        assert "does not exist" in res1.get_json()["message"]

        # 2. Inspector role
        res2 = client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={"assigned_to_user_id": self.inspector["id"]},
            headers={"X-CSRF-Token": csrf}
        )
        assert res2.status_code == 400
        assert "Only Maintenance Staff" in res2.get_json()["message"]

        # 3. Admin role
        res3 = client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={"assigned_to_user_id": self.admin["id"]},
            headers={"X-CSRF-Token": csrf}
        )
        assert res3.status_code == 400
        assert "Only Maintenance Staff" in res3.get_json()["message"]

    def test_assign_to_deactivated_account_rejected(self, client, test_db_path):
        """Inactive accounts cannot receive new maintenance task assignments."""
        csrf = self._login(client, "super_admin", "AdminPassword123")

        # Deactivate Alice
        update_user(self.tech_alice["id"], {"is_active": False}, db_path=test_db_path)

        res = client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={"assigned_to_user_id": self.tech_alice["id"]},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 400
        assert "deactivated" in res.get_json()["message"].lower()

    def test_reassignment_with_audit_trail(self, client, test_db_path):
        """Reassigning an inspection cancels the previous assignment and logs the transition."""
        csrf = self._login(client, "super_admin", "AdminPassword123")

        # Initial assignment to Alice
        client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={"assigned_to_user_id": self.tech_alice["id"], "instructions": "Initial task"},
            headers={"X-CSRF-Token": csrf}
        )

        # Reassign to Bob
        res = client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={"assigned_to_user_id": self.tech_bob["id"], "instructions": "Reassigned for urgent team rebalance."},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 200

        # Check inspection record
        insp = get_inspection_by_id(self.inspection1["id"], db_path=test_db_path)
        assert insp["assigned_to_user_id"] == self.tech_bob["id"]
        assert insp["assigned_to_username"] == "tech_bob"
        assert insp["assignment_instructions"] == "Reassigned for urgent team rebalance."

        # Check assignment history
        history = get_inspection_assignment_history(self.inspection1["id"], db_path=test_db_path)
        assert len(history) == 2
        assert history[0]["assigned_to_username"] == "tech_alice"
        assert history[0]["status"] == "cancelled"
        assert "Reassigned to tech_bob" in history[0]["cancellation_reason"]

        assert history[1]["assigned_to_username"] == "tech_bob"
        assert history[1]["status"] == "assigned"

        # Check activity log for 'reassigned' entry
        activities = get_inspection_activity(self.inspection1["id"], db_path=test_db_path)
        reassign_acts = [a for a in activities if a["action_type"] == "reassigned"]
        assert len(reassign_acts) == 1
        assert "Reassigned from tech_alice to tech_bob" in reassign_acts[0]["notes"]

    def test_cancellation_of_assignment(self, client, test_db_path):
        """Admin cancels an assignment, clearing active assignee while preserving audit history."""
        csrf = self._login(client, "super_admin", "AdminPassword123")

        # Assign first
        client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={"assigned_to_user_id": self.tech_alice["id"]},
            headers={"X-CSRF-Token": csrf}
        )

        # Cancel assignment
        cancel_res = client.post(
            f"/api/inspections/{self.inspection1['id']}/cancel-assignment",
            json={"reason": "Jurisdiction transferred to state highway agency."},
            headers={"X-CSRF-Token": csrf}
        )
        assert cancel_res.status_code == 200

        insp = get_inspection_by_id(self.inspection1["id"], db_path=test_db_path)
        assert insp["assigned_to_user_id"] is None
        assert insp["assigned_to_username"] is None
        assert insp["assignment_status"] == ASSIGNMENT_STATUS_CANCELLED

        # Check activity log
        activities = get_inspection_activity(self.inspection1["id"], db_path=test_db_path)
        cancel_acts = [a for a in activities if a["action_type"] == "assignment_cancelled"]
        assert len(cancel_acts) == 1
        assert "state highway agency" in cancel_acts[0]["notes"]

    def test_non_admin_cannot_assign_or_cancel(self, client):
        """Inspectors and Maintenance Staff are forbidden from assigning or cancelling tasks."""
        # 1. Inspector
        insp_csrf = self._login(client, "field_inspector", "InspectorPassword123")
        res1 = client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={"assigned_to_user_id": self.tech_alice["id"]},
            headers={"X-CSRF-Token": insp_csrf}
        )
        assert res1.status_code == 403

        # 2. Maintenance Staff
        maint_csrf = self._login(client, "tech_alice", "AlicePassword123")
        res2 = client.post(
            f"/api/inspections/{self.inspection1['id']}/assign",
            json={"assigned_to_user_id": self.tech_bob["id"]},
            headers={"X-CSRF-Token": maint_csrf}
        )
        assert res2.status_code == 403

        # 3. Cancel forbidden
        res3 = client.post(
            f"/api/inspections/{self.inspection1['id']}/cancel-assignment",
            json={"reason": "Cancel attempt"},
            headers={"X-CSRF-Token": maint_csrf}
        )
        assert res3.status_code == 403

    def test_maintenance_work_queue_scoping(self, client, test_db_path):
        """Work queue returns only tasks assigned to the authenticated maintenance user."""
        csrf = self._login(client, "super_admin", "AdminPassword123")

        # Assign inspection1 to Alice, inspection2 to Bob
        assign_inspection_task(self.inspection1["id"], self.tech_alice["id"], self.admin["id"], "Task Alice", db_path=test_db_path)
        assign_inspection_task(self.inspection2["id"], self.tech_bob["id"], self.admin["id"], "Task Bob", db_path=test_db_path)

        # Tech Alice checks her queue
        alice_csrf = self._login(client, "tech_alice", "AlicePassword123")
        alice_res = client.get("/api/maintenance/queue")
        assert alice_res.status_code == 200
        alice_data = alice_res.get_json()
        assert alice_data["count"] == 1
        assert alice_data["tasks"][0]["id"] == self.inspection1["id"]
        assert alice_data["tasks"][0]["assigned_to_username"] == "tech_alice"

        # Tech Bob checks his queue
        bob_csrf = self._login(client, "tech_bob", "BobPassword123")
        bob_res = client.get("/api/maintenance/queue")
        assert bob_res.status_code == 200
        bob_data = bob_res.get_json()
        assert bob_data["count"] == 1
        assert bob_data["tasks"][0]["id"] == self.inspection2["id"]
        assert bob_data["tasks"][0]["assigned_to_username"] == "tech_bob"

        # Admin checks queue (sees both)
        admin_csrf = self._login(client, "super_admin", "AdminPassword123")
        admin_res = client.get("/api/maintenance/queue")
        assert admin_res.status_code == 200
        assert admin_res.get_json()["count"] == 2

    def test_cross_user_access_denial(self, client, test_db_path):
        """A maintenance user cannot view or mutate another maintenance user's assigned task."""
        # Inspection 1 is assigned to Alice
        assign_inspection_task(self.inspection1["id"], self.tech_alice["id"], self.admin["id"], "Task Alice", db_path=test_db_path)

        # Bob logs in and tries to access Inspection 1
        bob_csrf = self._login(client, "tech_bob", "BobPassword123")

        # 1. Bob tries to view Inspection 1 details
        res_view = client.get(f"/api/inspections/{self.inspection1['id']}")
        assert res_view.status_code == 403
        assert res_view.get_json()["error_code"] == "FORBIDDEN_TASK_NOT_ASSIGNED"

        # 2. Bob tries to update Inspection 1 status
        res_status = client.patch(
            f"/api/inspections/{self.inspection1['id']}/status",
            json={"status": "Repair in Progress", "notes": "Bob tampering attempt"},
            headers={"X-CSRF-Token": bob_csrf}
        )
        assert res_status.status_code == 403
        assert res_status.get_json()["error_code"] == "FORBIDDEN_TASK_NOT_ASSIGNED"

        # 3. Bob tries to update Inspection 1 general details
        res_update = client.patch(
            f"/api/inspections/{self.inspection1['id']}",
            json={"location_notes": "Bob tampering notes"},
            headers={"X-CSRF-Token": bob_csrf}
        )
        assert res_update.status_code == 403
        assert res_update.get_json()["error_code"] == "FORBIDDEN_TASK_NOT_ASSIGNED"

        # 4. Bob tries to view Inspection 1 assignment history
        res_assign = client.get(f"/api/inspections/{self.inspection1['id']}/assignments")
        assert res_assign.status_code == 403

        # 5. Alice (assigned user) CAN view and update Inspection 1
        alice_csrf = self._login(client, "tech_alice", "AlicePassword123")
        res_alice_view = client.get(f"/api/inspections/{self.inspection1['id']}")
        assert res_alice_view.status_code == 200

        res_alice_status = client.patch(
            f"/api/inspections/{self.inspection1['id']}/status",
            json={"status": "Repair in Progress", "notes": "Alice starting work on site."},
            headers={"X-CSRF-Token": alice_csrf}
        )
        assert res_alice_status.status_code == 200
        assert res_alice_status.get_json()["inspection"]["status"] == "Repair in Progress"

    def test_status_synchronization_with_assignment(self, client, test_db_path):
        """Workflow status transitions automatically synchronize the active assignment status."""
        assign_inspection_task(self.inspection1["id"], self.tech_alice["id"], self.admin["id"], "Task Alice", db_path=test_db_path)
        alice_csrf = self._login(client, "tech_alice", "AlicePassword123")

        # 1. Update to Repair in Progress -> assignment_status becomes in_progress
        client.patch(
            f"/api/inspections/{self.inspection1['id']}/status",
            json={"status": "Repair in Progress", "notes": "Crews on site."},
            headers={"X-CSRF-Token": alice_csrf}
        )
        insp = get_inspection_by_id(self.inspection1["id"], db_path=test_db_path)
        assert insp["assignment_status"] == ASSIGNMENT_STATUS_IN_PROGRESS

        # 2. Update to Resolved -> assignment_status becomes completed
        client.patch(
            f"/api/inspections/{self.inspection1['id']}/status",
            json={"status": "Resolved", "notes": "Pavement patched and sealed."},
            headers={"X-CSRF-Token": alice_csrf}
        )
        insp2 = get_inspection_by_id(self.inspection1["id"], db_path=test_db_path)
        assert insp2["assignment_status"] == ASSIGNMENT_STATUS_COMPLETED

        # Check completed_at in maintenance_assignments table
        assignments = get_inspection_assignment_history(self.inspection1["id"], db_path=test_db_path)
        assert assignments[0]["status"] == "completed"
        assert assignments[0]["completed_at"] is not None

    def test_work_queue_filtering(self, client, test_db_path):
        """Queue supports filtering by category, urgency, city, and assignment status."""
        # Setup: Inspection 1 is upcoming Pothole in Downtown Metropolis assigned to Alice
        assign_inspection_task(self.inspection1["id"], self.tech_alice["id"], self.admin["id"], "Pothole task", db_path=test_db_path)

        # Inspection 2 is overdue Longitudinal Crack in North Sector Metropolis assigned to Alice
        assign_inspection_task(self.inspection2["id"], self.tech_alice["id"], self.admin["id"], "Crack task", db_path=test_db_path)

        alice_csrf = self._login(client, "tech_alice", "AlicePassword123")

        # Filter by category
        res_cat = client.get("/api/maintenance/queue?category=Pothole")
        assert res_cat.status_code == 200
        assert res_cat.get_json()["count"] == 1
        assert res_cat.get_json()["tasks"][0]["defect_type"] == "Pothole"

        # Filter by urgency
        res_urg = client.get("/api/maintenance/queue?urgency=overdue")
        assert res_urg.status_code == 200
        assert res_urg.get_json()["count"] == 1
        assert res_urg.get_json()["tasks"][0]["id"] == self.inspection2["id"]

        # Filter by location search query
        res_q = client.get("/api/maintenance/queue?q=Downtown")
        assert res_q.status_code == 200
        assert res_q.get_json()["count"] == 1
        assert res_q.get_json()["tasks"][0]["area"] == "Downtown"

    def test_legacy_unassigned_records_preserved(self, tmp_path):
        """Verifies that pre-existing inspections maintain NULL assignees with 'unassigned' status."""
        legacy_db = str(tmp_path / "legacy_assignments.db")
        conn = sqlite3.connect(legacy_db)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE defect_inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_name TEXT NOT NULL,
                status TEXT DEFAULT 'Open',
                road_name TEXT
            );
        """)
        cur.execute("INSERT INTO defect_inspections (image_name, road_name) VALUES ('old_road.jpg', 'County Road 5');")
        conn.commit()
        conn.close()

        # Initialize schema migrations
        init_db(legacy_db)

        insp = get_inspection_by_id(1, db_path=legacy_db)
        assert insp["road_name"] == "County Road 5"
        assert insp["assigned_to_user_id"] is None
        assert insp["assigned_to_username"] is None
        assert insp["assignment_status"] == ASSIGNMENT_STATUS_UNASSIGNED
