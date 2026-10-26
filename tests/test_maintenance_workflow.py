"""
VisionGuard AI — Phase 5: Maintenance Assignment & Resolution Workflow Test Suite.

Validates the full lifecycle from citizen submission to staff review, assignment,
repair progress, and verified resolution:
1. Role authorization: citizen blocked from staff queue, assignment, status updates.
2. Assignee validation: non-existent users, deactivated accounts, and citizens rejected.
3. Assignment persistence & audit trail: assigned_to, assigned_by, timestamps, status sync.
4. Complete status lifecycle: Open -> Assigned -> Repair in Progress -> Resolved -> Reopened.
5. Strict resolution note validation: required non-empty evidence notes before marking Resolved.
6. Reopening enforcement: requires reason notes; direct jumping from Resolved to other states blocked.
7. Staff queue filtering, sorting (domain, urgency, status, newest/oldest/priority/deadline), search.
8. Citizen read-only privacy guardrail: internal staff IDs, technician usernames, and dispatch notes redacted.
9. Cross-citizen isolation: citizen cannot view another citizen's inspection record.
10. Preservation of defect detection metadata and complaint drafts across workflow updates.
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
    update_inspection,
)
from database.complaints import (
    get_or_create_complaint_draft,
    update_complaint_draft,
)
from database.auth import (
    ROLE_ADMIN,
    ROLE_INSPECTOR,
    ROLE_MAINTENANCE,
    ROLE_CITIZEN,
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
    db_file = tmp_path / "test_phase5_workflow.db"
    return str(db_file)


@pytest.fixture
def mock_detector():
    """Mock DefectDetectionService to avoid loading YOLO model weights in tests."""
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
            "SECRET_KEY": "phase5-workflow-secret-key-32-chars-visionguard",
        }
    )
    return app


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


def get_csrf_token(client):
    """Fetches an active CSRF token from the server."""
    res = client.get("/api/auth/status")
    data = res.get_json()
    return data.get("csrf_token", "")


def login_user(client, username, password):
    """Signs in a user and returns the response."""
    csrf = get_csrf_token(client)
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"X-CSRF-Token": csrf}
    )


class TestPhase5MaintenanceWorkflow:
    @pytest.fixture(autouse=True)
    def setup_data(self, test_db_path):
        """Seed users and baseline inspection records."""
        self.db_path = test_db_path
        init_db(test_db_path)

        # Create distinct test users
        self.admin = create_user("workflow_admin", "AdminPass123", role=ROLE_ADMIN, db_path=test_db_path)
        self.tech_1 = create_user("tech_carol", "CarolPass123", role=ROLE_MAINTENANCE, email="carol@visionguard.gov", db_path=test_db_path)
        self.tech_2 = create_user("tech_dave", "DavePass123", role=ROLE_MAINTENANCE, email="dave@visionguard.gov", db_path=test_db_path)
        self.citizen_alice = create_user("citizen_alice", "AliceCitizen123", role=ROLE_CITIZEN, email="alice@example.com", db_path=test_db_path)
        self.citizen_bob = create_user("citizen_bob", "BobCitizen123", role=ROLE_CITIZEN, email="bob@example.com", db_path=test_db_path)

        # Create road inspection belonging to citizen_alice
        today = datetime.date.today()
        target_due = (today + datetime.timedelta(days=7)).isoformat()

        self.insp_road = save_inspection({
            "image_name": "pothole_main_st.jpg",
            "defect_count": 2,
            "defect_type": "Pothole",
            "confidence": 0.88,
            "road_name": "Main Street",
            "area": "Downtown",
            "city": "Metropolis",
            "status": "Open",
            "inspection_type": "road",
            "user_id": self.citizen_alice["id"],
            "target_repair_date": target_due,
            "detections": [
                {"class_name": "Pothole", "confidence": 0.88, "bbox": {"x1": 10, "y1": 20, "x2": 100, "y2": 150}},
                {"class_name": "Pothole", "confidence": 0.84, "bbox": {"x1": 120, "y1": 50, "x2": 200, "y2": 180}}
            ]
        }, db_path=test_db_path)

        # Create home inspection belonging to citizen_alice
        self.insp_home = save_inspection({
            "image_name": "roof_damage.jpg",
            "defect_count": 1,
            "defect_type": "Roof Damage",
            "confidence": 0.92,
            "road_name": "Oak Avenue Residence",
            "area": "Suburbs",
            "city": "Metropolis",
            "status": "Open",
            "inspection_type": "home",
            "user_id": self.citizen_alice["id"],
            "detections": [
                {"class_name": "Roof Damage", "confidence": 0.92, "bbox": {"x1": 30, "y1": 40, "x2": 300, "y2": 400}}
            ]
        }, db_path=test_db_path)

        # Create road inspection belonging to citizen_bob
        self.insp_bob = save_inspection({
            "image_name": "crosswalk_crack.jpg",
            "defect_count": 1,
            "defect_type": "Longitudinal Crack",
            "confidence": 0.79,
            "road_name": "Elm Street",
            "area": "Uptown",
            "city": "Metropolis",
            "status": "Open",
            "inspection_type": "road",
            "user_id": self.citizen_bob["id"],
            "detections": []
        }, db_path=test_db_path)

    # -------------------------------------------------------------------------
    # 1. Authorization: Citizen Access Restrictions
    # -------------------------------------------------------------------------
    def test_citizen_cannot_access_staff_queue(self, client):
        """Citizen cannot fetch staff maintenance queue."""
        login_user(client, "citizen_alice", "AliceCitizen123")
        res = client.get("/api/maintenance/queue")
        assert res.status_code == 403
        data = res.get_json()
        assert data["error_code"] in ("FORBIDDEN", "FORBIDDEN_ROLE")

    def test_citizen_cannot_assign_inspection(self, client):
        """Citizen cannot assign an inspection task."""
        login_user(client, "citizen_alice", "AliceCitizen123")
        csrf = get_csrf_token(client)
        res = client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.tech_1["id"], "instructions": "Dispatch immediately"},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 403
        data = res.get_json()
        assert data["error_code"] in ("FORBIDDEN", "FORBIDDEN_ROLE")

    def test_citizen_cannot_cancel_assignment(self, client):
        """Citizen cannot cancel a task assignment."""
        login_user(client, "citizen_alice", "AliceCitizen123")
        csrf = get_csrf_token(client)
        res = client.post(
            f"/api/inspections/{self.insp_road['id']}/cancel-assignment",
            json={"reason": "Cancel this"},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 403
        data = res.get_json()
        assert data["error_code"] in ("FORBIDDEN", "FORBIDDEN_ROLE")

    def test_citizen_cannot_update_status(self, client):
        """Citizen cannot directly transition an inspection status."""
        login_user(client, "citizen_alice", "AliceCitizen123")
        csrf = get_csrf_token(client)
        res = client.patch(
            f"/api/inspections/{self.insp_road['id']}/status",
            json={"status": "Resolved", "notes": "I fixed it myself"},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 403
        data = res.get_json()
        assert data["error_code"] in ("FORBIDDEN", "FORBIDDEN_ROLE")

    # -------------------------------------------------------------------------
    # 2. Assignee Validations
    # -------------------------------------------------------------------------
    def test_assign_to_nonexistent_user_rejected(self, client):
        """Assigning to an unknown user ID returns HTTP 400."""
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)
        res = client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": 99999, "instructions": "Repair pothole"},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 400
        data = res.get_json()
        assert data["error_code"] in ("INVALID_ASSIGNEE", "ASSIGNMENT_FAILED")
        assert "not exist" in data["message"].lower() or "invalid" in data["message"].lower()

    def test_assign_to_citizen_rejected(self, client):
        """Assigning to a citizen account returns HTTP 400."""
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)
        res = client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.citizen_alice["id"], "instructions": "Repair pothole"},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 400
        data = res.get_json()
        assert data["error_code"] in ("INVALID_ASSIGNEE_ROLE", "ASSIGNMENT_FAILED")
        assert "maintenance" in data["message"].lower()

    def test_assign_to_deactivated_user_rejected(self, client):
        """Assigning to a deactivated technician returns HTTP 400."""
        update_user(self.tech_2["id"], updates={"is_active": False}, db_path=self.db_path)
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)
        res = client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.tech_2["id"], "instructions": "Repair pothole"},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 400
        data = res.get_json()
        assert data["error_code"] in ("ASSIGNEE_DEACTIVATED", "ASSIGNMENT_FAILED")
        assert "deactivated" in data["message"].lower()

    # -------------------------------------------------------------------------
    # 3. Assignment Persistence, Status Sync & Audit Trail
    # -------------------------------------------------------------------------
    def test_admin_assignment_workflow(self, client):
        """Admin assigns task; status advances to Assigned; audit trail recorded."""
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)

        res = client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.tech_1["id"], "instructions": "High priority: fill potholes on lane 2"},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"

        # Verify inspection state in DB
        insp = get_inspection_by_id(self.insp_road["id"], db_path=self.db_path)
        assert insp["status"] == "Assigned"
        assert insp["assigned_to_user_id"] == self.tech_1["id"]
        assert insp["assigned_to_username"] == "tech_carol"
        assert insp["assigned_by_user_id"] == self.admin["id"]
        assert insp["assigned_by_username"] == "workflow_admin"
        assert insp["assigned_at"] is not None
        assert insp["assignment_instructions"] == "High priority: fill potholes on lane 2"

        # Verify audit activity
        activities = get_inspection_activity(self.insp_road["id"], db_path=self.db_path)
        assigned_acts = [a for a in activities if a["action_type"] == "assigned"]
        assert len(assigned_acts) >= 1
        assert assigned_acts[0]["user_id"] == self.admin["id"]
        assert assigned_acts[0]["username"] == "workflow_admin"
        assert "tech_carol" in assigned_acts[0]["notes"]

    def test_reassignment_audit_trail(self, client):
        """Reassigning an already assigned task logs reassigned action."""
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)

        # Initial assignment
        client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.tech_1["id"]},
            headers={"X-CSRF-Token": csrf}
        )

        # Reassign to tech_2
        res = client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.tech_2["id"], "instructions": "Take over from Carol"},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 200

        insp = get_inspection_by_id(self.insp_road["id"], db_path=self.db_path)
        assert insp["assigned_to_user_id"] == self.tech_2["id"]
        assert insp["assigned_to_username"] == "tech_dave"

        activities = get_inspection_activity(self.insp_road["id"], db_path=self.db_path)
        reassign_acts = [a for a in activities if a["action_type"] == "reassigned"]
        assert len(reassign_acts) >= 1
        assert "tech_dave" in reassign_acts[0]["notes"]

    # -------------------------------------------------------------------------
    # 4. Status Lifecycle & Validation
    # -------------------------------------------------------------------------
    def test_complete_status_lifecycle(self, client):
        """Lifecycle: Open -> Assigned -> Repair in Progress -> Resolved -> Reopened."""
        # 1. Admin assigns -> Assigned
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)
        client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.tech_1["id"]},
            headers={"X-CSRF-Token": csrf}
        )

        # 2. Technician logs in and starts repair -> Repair in Progress
        login_user(client, "tech_carol", "CarolPass123")
        csrf = get_csrf_token(client)
        res_progress = client.patch(
            f"/api/inspections/{self.insp_road['id']}/status",
            json={"status": "Repair in Progress", "notes": "Asphalt crew on site with hot-mix batch."},
            headers={"X-CSRF-Token": csrf}
        )
        assert res_progress.status_code == 200
        insp = get_inspection_by_id(self.insp_road["id"], db_path=self.db_path)
        assert insp["status"] == "Repair in Progress"

        # 3. Technician marks Resolved without notes -> rejected 400
        res_no_notes = client.patch(
            f"/api/inspections/{self.insp_road['id']}/status",
            json={"status": "Resolved", "notes": "   "},
            headers={"X-CSRF-Token": csrf}
        )
        assert res_no_notes.status_code == 400
        assert res_no_notes.get_json()["error_code"] == "MISSING_RESOLUTION_NOTES"

        # 4. Technician marks Resolved with physical repair notes -> 200
        res_resolved = client.patch(
            f"/api/inspections/{self.insp_road['id']}/status",
            json={
                "status": "Resolved",
                "notes": "Potholes excavated to 50mm, compacted with vibrating roller, asphalt seal applied."
            },
            headers={"X-CSRF-Token": csrf}
        )
        assert res_resolved.status_code == 200
        insp = get_inspection_by_id(self.insp_road["id"], db_path=self.db_path)
        assert insp["status"] == "Resolved"
        assert insp["assignment_status"] == "completed"

        # 5. Attempting to directly change from Resolved to Repair in Progress without reopening -> rejected 400
        res_jump = client.patch(
            f"/api/inspections/{self.insp_road['id']}/status",
            json={"status": "Repair in Progress", "notes": "Trying to skip reopen"},
            headers={"X-CSRF-Token": csrf}
        )
        assert res_jump.status_code == 400
        assert res_jump.get_json()["error_code"] == "INVALID_STATUS_TRANSITION"

        # 6. Admin attempts to Reopen without notes -> rejected 400
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)
        res_reopen_no_notes = client.patch(
            f"/api/inspections/{self.insp_road['id']}/status",
            json={"status": "Reopened", "notes": ""},
            headers={"X-CSRF-Token": csrf}
        )
        assert res_reopen_no_notes.status_code == 400
        assert res_reopen_no_notes.get_json()["error_code"] == "MISSING_REOPEN_NOTES"

        # 7. Admin reopens with reason notes -> 200
        res_reopen = client.patch(
            f"/api/inspections/{self.insp_road['id']}/status",
            json={"status": "Reopened", "notes": "Citizen reports patch sunken after heavy rain; requires reinspection."},
            headers={"X-CSRF-Token": csrf}
        )
        assert res_reopen.status_code == 200
        insp = get_inspection_by_id(self.insp_road["id"], db_path=self.db_path)
        assert insp["status"] == "Reopened"

    # -------------------------------------------------------------------------
    # 5. Staff Work Queue: Filtering, Sorting & Scoping
    # -------------------------------------------------------------------------
    def test_maintenance_queue_scoping_and_filters(self, client):
        """Technician sees only their tasks; admin sees all; domain/sort filters work."""
        # Admin assigns insp_road to tech_carol, insp_home to tech_dave
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)

        client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.tech_1["id"]},
            headers={"X-CSRF-Token": csrf}
        )
        client.post(
            f"/api/inspections/{self.insp_home['id']}/assign",
            json={"assigned_to_user_id": self.tech_2["id"]},
            headers={"X-CSRF-Token": csrf}
        )

        # 1. Tech Carol queue view: only insp_road
        login_user(client, "tech_carol", "CarolPass123")
        res_carol = client.get("/api/maintenance/queue")
        assert res_carol.status_code == 200
        tasks_carol = res_carol.get_json()["tasks"]
        task_ids_carol = [t["id"] for t in tasks_carol]
        assert self.insp_road["id"] in task_ids_carol
        assert self.insp_home["id"] not in task_ids_carol

        # 2. Tech Dave queue view: only insp_home
        login_user(client, "tech_dave", "DavePass123")
        res_dave = client.get("/api/maintenance/queue")
        assert res_dave.status_code == 200
        tasks_dave = res_dave.get_json()["tasks"]
        task_ids_dave = [t["id"] for t in tasks_dave]
        assert self.insp_home["id"] in task_ids_dave
        assert self.insp_road["id"] not in task_ids_dave

        # 3. Admin queue view: sees both
        login_user(client, "workflow_admin", "AdminPass123")
        res_admin = client.get("/api/maintenance/queue")
        assert res_admin.status_code == 200
        tasks_admin = res_admin.get_json()["tasks"]
        task_ids_admin = [t["id"] for t in tasks_admin]
        assert self.insp_road["id"] in task_ids_admin
        assert self.insp_home["id"] in task_ids_admin

        # 4. Domain filtering: road vs home
        res_road_filter = client.get("/api/maintenance/queue?domain=road")
        tasks_road = res_road_filter.get_json()["tasks"]
        assert all((t.get("inspection_type") or "road").lower() == "road" for t in tasks_road)

        res_home_filter = client.get("/api/maintenance/queue?domain=home")
        tasks_home = res_home_filter.get_json()["tasks"]
        assert all((t.get("inspection_type") or "").lower() == "home" for t in tasks_home)

        # 5. Sorting: newest vs oldest
        res_newest = client.get("/api/maintenance/queue?sort_by=newest")
        tasks_newest = res_newest.get_json()["tasks"]
        if len(tasks_newest) >= 2:
            assert tasks_newest[0]["id"] >= tasks_newest[1]["id"]

        # 6. Search query
        res_search = client.get("/api/maintenance/queue?q=Pothole")
        tasks_search = res_search.get_json()["tasks"]
        assert any("Pothole" in (t.get("defect_type") or "") for t in tasks_search)

    # -------------------------------------------------------------------------
    # 6. Citizen Read-Only Privacy Guardrails
    # -------------------------------------------------------------------------
    def test_citizen_privacy_guardrail_sanitization(self, client):
        """Citizen gets sanitized timeline: no technician user_id, generic name, redacted dispatch notes."""
        # Admin assigns insp_road to tech_carol with private dispatch note
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)
        client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.tech_1["id"], "instructions": "INTERNAL DISPATCH: Use truck #4 and caution at valve box."},
            headers={"X-CSRF-Token": csrf}
        )

        # Citizen Alice queries her report detail
        login_user(client, "citizen_alice", "AliceCitizen123")
        res_detail = client.get(f"/api/inspections/{self.insp_road['id']}")
        assert res_detail.status_code == 200
        data = res_detail.get_json()
        insp = data["inspection"]

        # Assignments array scrubbed for citizen privacy
        assert insp.get("assignments") == []

        # Activity log scrubbed
        activity_log = insp.get("activity_log") or []
        assign_entry = next((a for a in activity_log if a.get("action_type") == "assigned"), None)
        assert assign_entry is not None
        assert assign_entry.get("user_id") is None
        assert assign_entry.get("username") == "Operations Team"
        assert "INTERNAL DISPATCH" not in assign_entry.get("notes")
        assert "Remediation crew dispatched" in assign_entry.get("notes")

    def test_cross_citizen_access_denied(self, client):
        """Citizen Alice cannot inspect Citizen Bob's report."""
        login_user(client, "citizen_alice", "AliceCitizen123")
        res = client.get(f"/api/inspections/{self.insp_bob['id']}")
        assert res.status_code == 403
        data = res.get_json()
        assert data["error_code"] == "FORBIDDEN_REPORT_ACCESS"

    # -------------------------------------------------------------------------
    # 7. Preservation of Defect Telemetry & Complaint Drafts
    # -------------------------------------------------------------------------
    def test_preservation_of_telemetry_and_complaint_draft(self, client):
        """Status transitions and assignments preserve detections and civic complaint draft data."""
        # Create a civic complaint draft for insp_road
        draft = get_or_create_complaint_draft(
            self.insp_road["id"],
            user_id=self.citizen_alice["id"],
            username="citizen_alice",
            db_path=self.db_path
        )
        assert draft is not None
        assert draft["inspection_id"] == self.insp_road["id"]

        # Admin assigns and transitions through workflow
        login_user(client, "workflow_admin", "AdminPass123")
        csrf = get_csrf_token(client)
        client.post(
            f"/api/inspections/{self.insp_road['id']}/assign",
            json={"assigned_to_user_id": self.tech_1["id"]},
            headers={"X-CSRF-Token": csrf}
        )
        client.patch(
            f"/api/inspections/{self.insp_road['id']}/status",
            json={"status": "Repair in Progress", "notes": "Work underway"},
            headers={"X-CSRF-Token": csrf}
        )

        # Verify inspection detail preserves detections and complaint draft
        insp = get_inspection_by_id(self.insp_road["id"], db_path=self.db_path)
        assert insp["defect_count"] == 2
        assert len(insp["detections"]) == 2
        assert insp["detections"][0]["class_name"] == "Pothole"

        draft_after = get_or_create_complaint_draft(self.insp_road["id"], db_path=self.db_path)
        assert draft_after is not None
        assert draft_after["inspection_id"] == self.insp_road["id"]
        assert "Pothole" in draft_after["complaint_body"]
