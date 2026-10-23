# VisionGuard AI — Phase 4.7: Maintenance Assignment and Team Workflow

## Overview
Phase 4.7 extends VisionGuard AI's infrastructure maintenance operations by introducing role-scoped maintenance task assignments, administrative dispatch workflows, technician work queues, assignment audit logging, and strict cross-user access enforcement.

---

## 1. Objectives & Delivered Capabilities

1. **Administrative Task Assignment**: Administrators can allocate any saved defect inspection to an active Maintenance Staff technician with optional field dispatch instructions.
2. **Assignment Database Architecture**: Full assignment audit history stored in `maintenance_assignments` table alongside assignment metadata stored directly on `defect_inspections`.
3. **Dedicated Maintenance Work Queue**: Technicians receive a personalized queue (`GET /api/maintenance/queue`) displaying defects, geographic location, target repair dates, deadline compliance urgency, workflow status, and special instructions.
4. **Rich Multi-Dimensional Filtering**: Real-time filtering by assignment status (`assigned`, `in_progress`, `completed`, `cancelled`), deadline urgency (`overdue`, `due_today`, `upcoming`, `resolved`, `no_deadline`), defect category (`Longitudinal`, `Transverse`, `Alligator`, `Pothole`, `Sound`), and free-text location/road search.
5. **Reassignment and Cancellation**: Administrators can reassign tasks to another technician or cancel an active assignment with complete audit trail attribution.
6. **Backend Authorization & Cross-User Denial**:
   - Only Administrators can assign, reassign, or cancel tasks (`POST /api/inspections/<id>/assign`, `POST /api/inspections/<id>/cancel-assignment`).
   - Maintenance Staff can only view and update inspections assigned to them. Attempting to view or update tasks assigned to other technicians returns HTTP 403 `FORBIDDEN_TASK_NOT_ASSIGNED`.
   - Inspectors retain full reporting and inspection access but cannot manage assignments or update repair workflows.
7. **Status Synchronization**: Inspection lifecycle updates ("Repair in Progress" / "Resolved") automatically synchronize assignment states to `in_progress` and `completed`.
8. **Legacy Record Preservation**: Historical inspections retain `NULL` assignees and `unassigned` status without arbitrary automatic assignment.
9. **Inactive Account Protection**: Deactivated accounts cannot receive new assignments (HTTP 400 `CANNOT_ASSIGN_TO_INACTIVE_USER`). When an account is deactivated, existing assignments display clear warning badges without breaking record history.
10. **Civil Engineering Safety Disclaimers**: Disclaimers in UI and reports emphasize that administrative delegation and status changes do not certify physical engineering repair completion.

---

## 2. Database Schema & Migration Details

All migrations execute safely using SQLite-compatible `ALTER TABLE` and `CREATE TABLE IF NOT EXISTS` clauses without dropping existing data.

### 2.1 Table: `defect_inspections` (New Columns)
| Column Name | Type | Description |
| :--- | :--- | :--- |
| `assigned_to_user_id` | `INTEGER` | Foreign key referencing `users(id)` for the assigned technician (or `NULL` if unassigned). |
| `assigned_to_username`| `TEXT` | Cached username of the assigned technician. |
| `assigned_by_user_id` | `INTEGER` | Foreign key referencing `users(id)` for the assigning administrator. |
| `assigned_by_username`| `TEXT` | Cached username of the assigning administrator. |
| `assigned_at` | `TEXT` | ISO 8601 timestamp of initial assignment. |
| `assignment_instructions` | `TEXT` | Fieldwork instructions, repair guidelines, or work order notes. |
| `assignment_status` | `TEXT` | Status: `unassigned`, `assigned`, `in_progress`, `completed`, `cancelled`. Default: `'unassigned'`. |
| `assignment_updated_at` | `TEXT` | ISO 8601 timestamp of last assignment state modification. |

### 2.2 Table: `maintenance_assignments` (Audit Log)
```sql
CREATE TABLE IF NOT EXISTS maintenance_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id INTEGER NOT NULL,
    assigned_to_user_id INTEGER NOT NULL,
    assigned_to_username TEXT NOT NULL,
    assigned_by_user_id INTEGER,
    assigned_by_username TEXT,
    instructions TEXT,
    assignment_status TEXT NOT NULL DEFAULT 'assigned',
    created_at TEXT NOT NULL,
    FOREIGN KEY (inspection_id) REFERENCES defect_inspections(id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_to_user_id) REFERENCES users(id),
    FOREIGN KEY (assigned_by_user_id) REFERENCES users(id)
);
```

### 2.3 Indexes for High-Performance Queries
- `CREATE INDEX IF NOT EXISTS idx_defect_inspections_assigned_user ON defect_inspections(assigned_to_user_id);`
- `CREATE INDEX IF NOT EXISTS idx_defect_inspections_assignment_status ON defect_inspections(assignment_status);`
- `CREATE INDEX IF NOT EXISTS idx_assignments_inspection_id ON maintenance_assignments(inspection_id);`
- `CREATE INDEX IF NOT EXISTS idx_assignments_assigned_to ON maintenance_assignments(assigned_to_user_id);`

---

## 3. REST API Endpoints Reference

### 3.1 List Active Maintenance Staff
- **Endpoint**: `GET /api/maintenance/staff`
- **Access**: Administrator (`admin`) only
- **Response**:
```json
{
  "status": "success",
  "staff": [
    { "id": 2, "username": "tech_bob", "email": "bob@cityworks.gov", "role": "maintenance", "is_active": true }
  ]
}
```

### 3.2 Assign / Reassign Task
- **Endpoint**: `POST /api/inspections/<int:inspection_id>/assign`
- **Access**: Administrator (`admin`) only
- **Payload**:
```json
{
  "assigned_to_user_id": 2,
  "instructions": "Inspect pothole depth; apply hot-mix asphalt sealant and post-repair photographic evidence."
}
```
- **Error Responses**:
  - `400 CANNOT_ASSIGN_TO_INACTIVE_USER`: Target user account is inactive.
  - `400 INVALID_ASSIGNEE_ROLE`: Target user role is not `maintenance`.
  - `404 INSPECTION_NOT_FOUND`: Inspection record does not exist.

### 3.3 Cancel Task Assignment
- **Endpoint**: `POST /api/inspections/<int:inspection_id>/cancel-assignment`
- **Access**: Administrator (`admin`) only
- **Payload**:
```json
{
  "reason": "Road resurfacing contracted to external paving authority."
}
```

### 3.4 Maintenance Work Queue
- **Endpoint**: `GET /api/maintenance/queue`
- **Access**: Administrator (`admin`) or Maintenance Staff (`maintenance`)
- **Query Parameters**:
  - `status`: Filter by assignment status (`assigned`, `in_progress`, `completed`, `cancelled`).
  - `urgency`: Filter by deadline urgency (`overdue`, `due_today`, `upcoming`, `resolved`, `no_deadline`).
  - `category`: Filter by defect category (`Longitudinal`, `Transverse`, `Alligator`, `Pothole`, `Sound`).
  - `q`: Search keyword across road name, area, city, notes, and instructions.
- **Scoping Rule**:
  - Maintenance Staff only receive tasks where `assigned_to_user_id == current_user.id`.
  - Administrators view all assigned tasks across the entire team.

### 3.5 Assignment Audit History
- **Endpoint**: `GET /api/inspections/<int:inspection_id>/assignments`
- **Access**: Authenticated users (`admin`, `inspector`, `maintenance`)

---

## 4. Role Authorization Matrix

| Feature / Action | Admin | Maintenance Staff | Inspector | Unauthenticated |
| :--- | :---: | :---: | :---: | :---: |
| **Assign / Reassign Task** | ✅ Allowed | ❌ Denied (403) | ❌ Denied (403) | ❌ Denied (401) |
| **Cancel Assignment** | ✅ Allowed | ❌ Denied (403) | ❌ Denied (403) | ❌ Denied (401) |
| **View Maintenance Queue** | ✅ Full Team | ✅ Own Tasks Only | ❌ Hidden | ❌ Denied (401) |
| **Update Assigned Task Status** | ✅ Allowed | ✅ Allowed (Own Tasks) | ❌ Denied (403) | ❌ Denied (401) |
| **Update Other Tech's Task** | ✅ Allowed | ❌ Denied (403)* | ❌ Denied (403) | ❌ Denied (401) |
| **View Other Tech's Task Detail** | ✅ Allowed | ❌ Denied (403)* | ✅ Allowed (Read) | ❌ Denied (401) |
| **Run AI Defect Detection** | ✅ Allowed | ❌ Denied (403) | ✅ Allowed | ❌ Denied (401) |
| **Export PDF/CSV Reports** | ✅ Allowed | ❌ Denied (403) | ✅ Allowed | ❌ Denied (401) |

*\*Returns HTTP 403 `FORBIDDEN_TASK_NOT_ASSIGNED`: "Access denied: This maintenance task is assigned to another technician."*

---

## 5. UI Features & Workflows

1. **Header Navigation**:
   - `🛠️ Maintenance Queue` button with badge count appears dynamically when logged in as `admin` or `maintenance`.
2. **Work Queue View (`#queueSection`)**:
   - Summary telemetry KPI cards: Total Assigned, Pending / In Progress, Urgent / Overdue, Completed Tasks.
   - Comprehensive filter bar with assignment status, deadline urgency, defect category, and location search.
   - Actionable data table with direct "👁️ Open Task" links to inspection details.
3. **Record Detail Assignment Card (`#detailAssignmentCard`)**:
   - Assignment status badge (`Assigned`, `In Progress`, `Completed`, `Cancelled`, `Unassigned`).
   - Assigned technician username with active/deactivated badge.
   - Dispatcher username, assignment timestamp, last update timestamp, and instructions block.
   - Administrator controls: "👤 Assign / Reassign Task" modal launcher and "🚫 Cancel Assignment" button.
   - Chronological assignment audit history list.
4. **Assignment Modal (`#assignTaskModal`)**:
   - Live dropdown populated from `GET /api/maintenance/staff` filtering out inactive and non-maintenance users.
   - Instruction text area for field observations and directives.
5. **CSV Export Integration**:
   - Inspection reports include `Assigned Technician` and `Assignment Status` columns.

---

## 6. Civil Engineering Disclaimer & Boundaries

> **Safety Notice:**
> Task assignment, status transitions, and technician notes represent clerical administrative coordination within local database records. 
> Assigning a task or updating a status marker to "In Progress" or "Resolved" **does not certify physical pavement repair, cavity compaction, sub-base structural safety, or compliance with municipal road engineering standards**.
