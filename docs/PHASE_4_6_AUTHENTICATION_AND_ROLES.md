# VisionGuard AI — Phase 4.6: Authentication, User Roles, and Access Control

## Overview
Phase 4.6 introduces enterprise-grade authentication, role-based access control (RBAC), secure session management, CSRF protection, and audit log user attribution to VisionGuard AI.

---

## 1. Role-Based Access Control (RBAC) Architecture

VisionGuard AI defines three discrete roles with strict backend permission enforcement on every protected Flask API endpoint:

| Feature / Endpoint | Administrator (`admin`) | Inspector (`inspector`) | Maintenance Staff (`maintenance`) | Unauthenticated (`guest`) |
| :--- | :---: | :---: | :---: | :---: |
| **Defect Detection Inference** (`POST /api/inspect`) | ✅ Allowed | ✅ Allowed | ❌ Denied (403) | ❌ Denied (401) |
| **Save Inspection Record** (`POST /api/inspections`) | ✅ Allowed | ✅ Allowed | ❌ Denied (403) | ❌ Denied (401) |
| **View Dashboard Analytics** (`GET /api/dashboard/stats`) | ✅ Allowed | ✅ Allowed | ✅ Allowed | ❌ Denied (401)* |
| **View Inspection Records** (`GET /api/inspections`, `/api/inspections/<id>`) | ✅ Allowed | ✅ Allowed | ✅ Allowed | ❌ Denied (401)* |
| **View Defect Map Records** (`GET /api/inspections?has_coords=1`) | ✅ Allowed | ✅ Allowed | ✅ Allowed | ❌ Denied (401)* |
| **Update Status, Notes & Deadlines** (`PATCH /api/inspections/<id>/status`) | ✅ Allowed | ❌ Denied (403) | ✅ Allowed | ❌ Denied (401) |
| **Update Full Inspection Details** (`PATCH /api/inspections/<id>`) | ✅ Allowed | ❌ Denied (403) | ✅ Allowed | ❌ Denied (401) |
| **Preview Inspection Report** (`GET /api/reports/preview`) | ✅ Allowed | ✅ Allowed | ❌ Denied (403) | ❌ Denied (401) |
| **Export CSV Report** (`GET /api/reports/export/csv`) | ✅ Allowed | ✅ Allowed | ❌ Denied (403) | ❌ Denied (401) |
| **Export PDF Report** (`GET /api/reports/export/pdf`) | ✅ Allowed | ✅ Allowed | ❌ Denied (403) | ❌ Denied (401) |
| **Reload AI Model Checkpoint** (`POST /api/reload-model`) | ✅ Allowed | ❌ Denied (403) | ❌ Denied (403) | ❌ Denied (401) |
| **Delete Inspection Record** (`DELETE /api/inspections/<id>`) | ✅ Allowed | ❌ Denied (403) | ❌ Denied (403) | ❌ Denied (401) |
| **User Directory & Account Creation** (`GET/POST /api/users`) | ✅ Allowed | ❌ Denied (403) | ❌ Denied (403) | ❌ Denied (401) |
| **User Role / Status Update** (`PATCH /api/users/<id>`) | ✅ Allowed | ❌ Denied (403) | ❌ Denied (403) | ❌ Denied (401) |

*\*Note: In non-explicit development mode without users present, read-only telemetry endpoints permit public onboarding until the primary admin account is provisioned.*

---

## 2. Security Implementations

### 2.1 Cryptographic Password Hashing
- Stored using `werkzeug.security.generate_password_hash` utilizing `scrypt` key derivation with standard work factors.
- Plaintext passwords are never logged, serialized, or returned in API responses.
- Minimum password length: 8 characters. Minimum username length: 3 characters (regex `^[a-zA-Z0-9_.-]{3,40}$`).

### 2.2 Generic Credential Errors
- All authentication failures (`POST /api/auth/login`) return the generic message:
  `"Invalid username or password."` with HTTP 401.
- This prevents username enumeration attacks. Deactivated accounts explicitly return an account disabled notification.

### 2.3 Session & Cookie Hardening
- Session cookies configured with:
  - `httponly = True`: Prevents client-side script access to session tokens.
  - `samesite = "Lax"`: Protects against cross-site request forgery via navigational links.
  - `permanent_session_lifetime = 8 hours`: Enforces session expiration.
  - `secure = True`: Automatically applied when running over HTTPS.

### 2.4 CSRF Protection
- Cryptographic CSRF tokens generated via `secrets.token_urlsafe(32)`.
- Validated on all state-changing requests (`POST`, `PATCH`, `PUT`, `DELETE`).
- Sent via standard `X-CSRF-Token` request header or `csrf_token` body payload.
- Automatically injected on client-side requests via `window.fetch` interceptor in `app.js`.

### 2.5 Administrator Self-Protection Guards
- An active administrator cannot deactivate their own account (`SELF_DEACTIVATION_DENIED`).
- An active administrator cannot demote their own account role (`SELF_DEMOTION_DENIED`).

---

## 3. Initial Administrator Setup Instructions

VisionGuard AI **does not** use hard-coded default credentials. You can bootstrap the primary system administrator using any of the following three secure methods:

### Option A: Environment Variables (Automated Server Boot)
Set the administrator credentials in your environment before launching the server:
```bash
# Windows PowerShell
$env:VISIONGUARD_ADMIN_USERNAME = "sysadmin"
$env:VISIONGUARD_ADMIN_PASSWORD = "StrongSecurePassword123!"
$env:VISIONGUARD_ADMIN_EMAIL = "admin@visionguard.gov"
python app/server.py
```
Upon startup, `init_admin_from_env()` checks if zero users exist and initializes the administrator account automatically.

### Option B: CLI Setup Command
Run the interactive CLI bootstrap tool directly against the database:
```bash
python -m database.auth init-admin --username sysadmin --email admin@visionguard.gov
```
If `--password` is omitted, you will be prompted securely without echo.

### Option C: First-Run Web Interface Setup
When the application starts with 0 user accounts:
1. Navigate to `http://localhost:5000/`.
2. The UI detects `requires_setup: true` and displays the **🚀 Setup Admin** button in the header.
3. Submitting the First-Time Setup form calls `POST /api/auth/setup-admin`.
4. The backend verifies that `count_users() == 0`, creates the administrator, and automatically establishes the session. Once any account exists, this endpoint is permanently sealed (HTTP 403 `SETUP_FORBIDDEN`).

---

## 4. Configuration & Environment Variables Reference

| Variable | Description | Default |
| :--- | :--- | :--- |
| `VISIONGUARD_SECRET_KEY` | Flask session and cryptographic CSRF secret key. Must be a high-entropy string in production. | Randomized local secret |
| `VISIONGUARD_AUTH_ENABLED` | Set to `true` or `1` to strictly enforce login on all routes. Defaults to true when users exist. | Auto-detected |
| `VISIONGUARD_ENFORCE_CSRF` | Set to `true` or `1` to require CSRF tokens on all mutating requests. | `true` |
| `VISIONGUARD_ADMIN_USERNAME`| Username for automated administrator bootstrapping. | None |
| `VISIONGUARD_ADMIN_PASSWORD`| Password for automated administrator bootstrapping (min 8 chars). | None |
| `VISIONGUARD_ADMIN_EMAIL`   | Email for automated administrator bootstrapping. | None |

---

## 5. Database Schema & Migration Compatibility

The SQLite database migration adds the `users` table and extends existing audit tables safely:

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'inspector',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);
```

### Table Migrations
- `defect_inspections`: Added `created_by_user_id INTEGER`, `created_by_username TEXT`.
- `maintenance_activity_log`: Added `user_id INTEGER`, `username TEXT`.
- **Legacy Compatibility**: Pre-existing records maintain `NULL` identities, guaranteeing zero historical data corruption or invented personas.

---

## 6. Known Security Limitations & Production Deployment Guidance

1. **Production Reverse Proxy / TLS**: In production, place VisionGuard AI behind an HTTPS reverse proxy (e.g. Nginx, Caddy, or AWS ALB) and set `SESSION_COOKIE_SECURE = True`.
2. **Secret Key Management**: Always set `VISIONGUARD_SECRET_KEY` to a 64+ character random secret stored in a secure secret manager (e.g., HashiCorp Vault, AWS Secrets Manager).
3. **Rate Limiting**: For public or internet-facing endpoints, add rate limiting (e.g. `Flask-Limiter` or Nginx `limit_req_zone`) to `/api/auth/login` to thwart brute-force password guessing.
