"""
VisionGuard AI - Authentication, User Roles, and Access Control Module (Phase 4.6).

Provides user credential management, strong password hashing (scrypt via werkzeug),
role-based permissions (Admin, Inspector, Maintenance Staff), account lifecycle (activation/deactivation),
and secure initialization procedures.
"""

import os
import re
import sys
import sqlite3
import argparse
import getpass
import datetime
from typing import Dict, Any, List, Optional, Tuple

from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db_connection, init_db, DEFAULT_DB_PATH


# Allowed application roles
ROLE_ADMIN = "admin"
ROLE_INSPECTOR = "inspector"
ROLE_MAINTENANCE = "maintenance"
ROLE_CITIZEN = "citizen"

ALLOWED_ROLES = [ROLE_ADMIN, ROLE_INSPECTOR, ROLE_MAINTENANCE, ROLE_CITIZEN]
ROLE_DISPLAY_NAMES = {
    ROLE_ADMIN: "Administrator",
    ROLE_INSPECTOR: "Inspector",
    ROLE_MAINTENANCE: "Maintenance Staff",
    ROLE_CITIZEN: "Citizen",
}

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Hashes a plaintext password using werkzeug scrypt algorithm."""
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verifies a plaintext password against a stored scrypt password hash."""
    if not password_hash or not password:
        return False
    return check_password_hash(password_hash, password)


def validate_username(username: Any) -> Tuple[bool, Optional[str]]:
    """Validates username format and character set."""
    if not username or not str(username).strip():
        return False, "Username is required."
    u = str(username).strip()
    if not USERNAME_REGEX.match(u):
        return False, "Username must be 3-40 characters long and contain only letters, numbers, dots, hyphens, or underscores."
    return True, None


def validate_password_strength(password: Any) -> Tuple[bool, Optional[str]]:
    """Enforces minimum password security standards."""
    if not password or not isinstance(password, str):
        return False, "Password is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters in length."
    return True, None


def validate_role(role: Any) -> Tuple[bool, Optional[str]]:
    """Validates user role against allowed role definitions."""
    if not role or str(role).strip().lower() not in ALLOWED_ROLES:
        return False, f"Role '{role}' is invalid. Allowed roles: {ALLOWED_ROLES}"
    return True, None


def sanitize_user_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Converts a user database row to a dict, strictly omitting the password hash."""
    d = dict(row)
    if "password_hash" in d:
        del d["password_hash"]
    d["role_display"] = ROLE_DISPLAY_NAMES.get(d.get("role"), d.get("role"))
    d["is_active"] = bool(d.get("is_active", 1))
    return d


def create_user(
    username: str,
    password: str,
    role: str = ROLE_INSPECTOR,
    email: Optional[str] = None,
    is_active: int = 1,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Creates a new user account with hashed password storage.
    Raises ValueError on validation or uniqueness violation.
    """
    init_db(db_path)

    # 1. Validate inputs
    is_valid_u, u_err = validate_username(username)
    if not is_valid_u:
        raise ValueError(u_err)

    is_valid_p, p_err = validate_password_strength(password)
    if not is_valid_p:
        raise ValueError(p_err)

    norm_role = str(role).strip().lower()
    is_valid_r, r_err = validate_role(norm_role)
    if not is_valid_r:
        raise ValueError(r_err)

    norm_username = str(username).strip()
    norm_email = str(email).strip().lower() if email and str(email).strip() else None

    # 2. Hash password with scrypt
    pw_hash = generate_password_hash(password)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
        INSERT INTO users (username, email, password_hash, role, is_active)
        VALUES (?, ?, ?, ?, ?);
        """, (norm_username, norm_email, pw_hash, norm_role, 1 if is_active else 0))
        new_id = cursor.lastrowid
        conn.commit()

        cursor.execute("SELECT * FROM users WHERE id = ?;", (new_id,))
        row = cursor.fetchone()
        conn.close()
        return sanitize_user_dict(row)
    except sqlite3.IntegrityError as e:
        conn.close()
        if "UNIQUE constraint failed: users.username" in str(e) or "users.username" in str(e):
            raise ValueError(f"Username '{norm_username}' is already in use.")
        elif norm_email and ("UNIQUE" in str(e) and "email" in str(e)):
            raise ValueError(f"Email '{norm_email}' is already in use.")
        raise ValueError(f"Database integrity error: {str(e)}")


def get_user_by_id(user_id: int, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Fetches user by primary key ID (excluding password hash)."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return sanitize_user_dict(row) if row else None


def get_user_by_username(
    username: str,
    include_password_hash: bool = False,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Fetches user record by username (case-insensitive).
    Optionally includes password_hash solely for authentication routines.
    """
    if not username:
        return None
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?);", (str(username).strip(),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None

    if include_password_hash:
        d = dict(row)
        d["role_display"] = ROLE_DISPLAY_NAMES.get(d.get("role"), d.get("role"))
        d["is_active"] = bool(d.get("is_active", 1))
        return d
    return sanitize_user_dict(row)


def list_users(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Returns a list of all user records ordered chronologically by ID."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY id ASC;")
    rows = cursor.fetchall()
    conn.close()
    return [sanitize_user_dict(r) for r in rows]


def count_users(db_path: str = DEFAULT_DB_PATH) -> int:
    """Returns total registered user count."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users;")
    count = cursor.fetchone()["count"]
    conn.close()
    return count


def update_user(
    user_id: int,
    updates: Dict[str, Any],
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Updates role, active status, email, or password for a user.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    current = cursor.fetchone()
    if not current:
        conn.close()
        return None

    fields = []
    params = []

    if "role" in updates:
        new_role = str(updates["role"]).strip().lower()
        is_valid_r, r_err = validate_role(new_role)
        if not is_valid_r:
            conn.close()
            raise ValueError(r_err)
        fields.append("role = ?")
        params.append(new_role)

    if "is_active" in updates:
        val = 1 if updates["is_active"] else 0
        fields.append("is_active = ?")
        params.append(val)

    if "email" in updates:
        new_email = str(updates["email"]).strip().lower() if updates["email"] and str(updates["email"]).strip() else None
        fields.append("email = ?")
        params.append(new_email)

    if "password" in updates and updates["password"]:
        new_pw = updates["password"]
        is_valid_p, p_err = validate_password_strength(new_pw)
        if not is_valid_p:
            conn.close()
            raise ValueError(p_err)
        fields.append("password_hash = ?")
        params.append(generate_password_hash(new_pw))

    if not fields:
        conn.close()
        return sanitize_user_dict(current)

    fields.append("updated_at = CURRENT_TIMESTAMP")
    sql = f"UPDATE users SET {', '.join(fields)} WHERE id = ?;"
    params.append(user_id)

    cursor.execute(sql, tuple(params))
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    updated_row = cursor.fetchone()
    conn.close()
    return sanitize_user_dict(updated_row)


def authenticate_user(
    username: str,
    password: str,
    db_path: str = DEFAULT_DB_PATH
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Authenticates username and password securely.
    Returns: (is_authenticated, user_dict_or_none, error_message_or_none)
    Protects against timing attacks and username enumeration by using generic error messages.
    """
    if not username or not password:
        return False, None, "Invalid username or password."

    user = get_user_by_username(username, include_password_hash=True, db_path=db_path)
    if not user:
        # Dummy verification to prevent timing discrepancy
        check_password_hash(generate_password_hash("dummy"), password)
        return False, None, "Invalid username or password."

    if not check_password_hash(user["password_hash"], password):
        return False, None, "Invalid username or password."

    # Verify account activation status
    if not user.get("is_active"):
        return False, None, "Account has been deactivated. Please contact an administrator."

    # Update last login timestamp
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?;", (user["id"],))
    conn.commit()
    conn.close()

    del user["password_hash"]
    return True, user, None


def init_admin_from_env(db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """
    Safely bootstraps the first administrator if environment variables are provided:
    - VISIONGUARD_ADMIN_USERNAME
    - VISIONGUARD_ADMIN_PASSWORD
    - VISIONGUARD_ADMIN_EMAIL (optional)
    Never creates an admin with empty or hardcoded credentials.
    """
    admin_user = os.environ.get("VISIONGUARD_ADMIN_USERNAME", "").strip()
    admin_pw = os.environ.get("VISIONGUARD_ADMIN_PASSWORD", "").strip()
    admin_email = os.environ.get("VISIONGUARD_ADMIN_EMAIL", "").strip() or None

    if not admin_user or not admin_pw:
        return None

    existing = get_user_by_username(admin_user, include_password_hash=True, db_path=db_path)
    if existing:
        # Update credentials and ensure admin role
        update_user(
            existing["id"],
            {"password": admin_pw, "role": ROLE_ADMIN, "is_active": 1, "email": admin_email or existing.get("email")},
            db_path=db_path
        )
        return get_user_by_id(existing["id"], db_path=db_path)
    else:
        return create_user(
            username=admin_user,
            password=admin_pw,
            role=ROLE_ADMIN,
            email=admin_email,
            is_active=1,
            db_path=db_path
        )


def main():
    """CLI tool for administrator setup and user management."""
    parser = argparse.ArgumentParser(description="VisionGuard AI User Management & Administrator Setup")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init-admin
    init_parser = subparsers.add_parser("init-admin", help="Create or update initial administrator account")
    init_parser.add_argument("--username", "-u", help="Administrator username", default=None)
    init_parser.add_argument("--password", "-p", help="Administrator password", default=None)
    init_parser.add_argument("--email", "-e", help="Administrator email", default=None)
    init_parser.add_argument("--db", help="SQLite database path", default=DEFAULT_DB_PATH)

    # list-users
    list_parser = subparsers.add_parser("list-users", help="List all registered user accounts")
    list_parser.add_argument("--db", help="SQLite database path", default=DEFAULT_DB_PATH)

    args = parser.parse_args()

    if args.command == "init-admin":
        username = args.username
        if not username:
            username = input("Enter administrator username: ").strip()

        password = args.password
        if not password:
            password = getpass.getpass("Enter administrator password (min 8 chars): ")

        try:
            admin = create_user(
                username=username,
                password=password,
                role=ROLE_ADMIN,
                email=args.email,
                is_active=1,
                db_path=args.db
            )
            print(f"✓ Administrator '{admin['username']}' created successfully (ID: {admin['id']}).")
        except ValueError as e:
            if "already in use" in str(e):
                existing = get_user_by_username(username, db_path=args.db)
                if existing:
                    update_user(existing["id"], {"password": password, "role": ROLE_ADMIN, "is_active": 1}, db_path=args.db)
                    print(f"✓ Administrator '{username}' credentials updated successfully.")
                    return
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list-users":
        users = list_users(db_path=args.db)
        if not users:
            print("No users registered.")
            return
        print(f"{'ID':<4} {'Username':<20} {'Role':<15} {'Active':<8} {'Last Login':<20}")
        print("-" * 70)
        for u in users:
            print(f"{u['id']:<4} {u['username']:<20} {u['role_display']:<15} {str(u['is_active']):<8} {str(u.get('last_login_at') or 'Never'):<20}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
