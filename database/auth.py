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
import secrets
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
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# Pre-computed dummy hash to guarantee constant-time verification on missing users without runtime overhead
_DUMMY_PASSWORD_HASH = generate_password_hash("dummy_protection_hash_visionguard")


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
    """Enforces minimum and maximum password security standards."""
    if not password or not isinstance(password, str):
        return False, "Password is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters in length."
    if len(password) > MAX_PASSWORD_LENGTH:
        return False, f"Password cannot exceed {MAX_PASSWORD_LENGTH} characters in length."
    return True, None


def validate_email(email: Any) -> Tuple[bool, Optional[str]]:
    """Validates optional email format and maximum length."""
    if email is None or str(email).strip() == "":
        return True, None
    e = str(email).strip()
    if len(e) > 120:
        return False, "Email address cannot exceed 120 characters."
    if not EMAIL_REGEX.match(e):
        return False, "Invalid email address format."
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

    is_valid_e, e_err = validate_email(email)
    if not is_valid_e:
        raise ValueError(e_err)

    norm_username = str(username).strip()
    norm_email = str(email).strip().lower() if email and str(email).strip() else None

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Pre-insert uniqueness checks (case-insensitive) to prevent SQLite binary collation collisions
    cursor.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?);", (norm_username,))
    if cursor.fetchone():
        conn.close()
        raise ValueError(f"Username '{norm_username}' is already in use.")

    if norm_email:
        cursor.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?);", (norm_email,))
        if cursor.fetchone():
            conn.close()
            raise ValueError(f"Email '{norm_email}' is already in use.")

    # 2. Hash password with scrypt
    pw_hash = generate_password_hash(password)

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
        err_str = str(e).lower()
        if "username" in err_str:
            raise ValueError(f"Username '{norm_username}' is already in use.")
        elif norm_email and "email" in err_str:
            raise ValueError(f"Email '{norm_email}' is already in use.")
        raise ValueError(f"Database integrity error: {str(e)}")


def get_user_by_id(
    user_id: int,
    include_password_hash: bool = False,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """Fetches user by primary key ID (optionally including password hash for secure verification)."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
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


def get_user_by_email(
    email: str,
    include_password_hash: bool = False,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Fetches user record by email address (case-insensitive).
    Optionally includes password_hash solely for authentication routines.
    """
    if not email or not str(email).strip():
        return None
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?);", (str(email).strip(),))
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


def get_user_by_google_sub(
    google_sub: str,
    include_password_hash: bool = False,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Fetches a user record by their unique Google Subject identifier.
    Returns None if not found or if google_sub is blank.
    """
    if not google_sub or not str(google_sub).strip():
        return None
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE google_sub = ?;", (str(google_sub).strip(),))
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


def create_google_user(
    username: str,
    email: str,
    google_sub: str,
    avatar_url: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Registers a new citizen account authenticated via Google OAuth.
    Strictly assigns role = ROLE_CITIZEN.
    Generates an unguessable disabled password hash satisfying NOT NULL constraint.
    """
    init_db(db_path)

    if not google_sub or not str(google_sub).strip():
        raise ValueError("Google Subject ID (sub) is required.")

    norm_sub = str(google_sub).strip()
    norm_email = str(email).strip().lower() if email and str(email).strip() else None
    if not norm_email:
        raise ValueError("Verified email address is required for Google authentication.")

    is_valid_e, e_err = validate_email(norm_email)
    if not is_valid_e:
        raise ValueError(e_err)

    norm_username = str(username).strip()
    is_valid_u, u_err = validate_username(norm_username)
    if not is_valid_u:
        sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", norm_username)[:30]
        if len(sanitized) < 3:
            sanitized = f"citizen_{secrets.token_hex(4)}"
        norm_username = sanitized

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Pre-insert uniqueness check for google_sub
    cursor.execute("SELECT id FROM users WHERE google_sub = ?;", (norm_sub,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("Google identity is already registered to an existing account.")

    # Pre-insert uniqueness check for email
    cursor.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?);", (norm_email,))
    if cursor.fetchone():
        conn.close()
        raise ValueError(f"Email '{norm_email}' is already in use.")

    # Uniqueness check for username, appending suffix if already in use
    cursor.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?);", (norm_username,))
    if cursor.fetchone():
        norm_username = f"{norm_username[:30]}_{secrets.token_hex(3)}"

    disabled_pw_hash = f"!google_oauth_disabled_{secrets.token_hex(16)}"

    try:
        cursor.execute("""
        INSERT INTO users (
            username, email, password_hash, role, is_active,
            google_sub, google_email, auth_provider, avatar_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            norm_username,
            norm_email,
            disabled_pw_hash,
            ROLE_CITIZEN,
            1,
            norm_sub,
            norm_email,
            "google",
            str(avatar_url).strip() if avatar_url else None
        ))
        new_id = cursor.lastrowid
        conn.commit()

        cursor.execute("SELECT * FROM users WHERE id = ?;", (new_id,))
        row = cursor.fetchone()
        conn.close()
        return sanitize_user_dict(row)
    except Exception as e:
        conn.close()
        raise ValueError(f"Failed to create Google user: {str(e)}")


def link_google_to_user(
    user_id: int,
    google_sub: str,
    google_email: Optional[str] = None,
    avatar_url: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Links a verified Google identity to an existing user account.
    Enforces that google_sub is not already bound to another user.
    Sets auth_provider = 'both'.
    """
    init_db(db_path)

    if not google_sub or not str(google_sub).strip():
        raise ValueError("Google Subject ID (sub) is required.")

    norm_sub = str(google_sub).strip()
    norm_email = str(google_email).strip().lower() if google_email and str(google_email).strip() else None

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise ValueError(f"User ID {user_id} not found.")

    # Verify google_sub is not linked to someone else
    cursor.execute("SELECT id FROM users WHERE google_sub = ? AND id != ?;", (norm_sub, user_id))
    conflict = cursor.fetchone()
    if conflict:
        conn.close()
        raise ValueError("This Google identity is already linked to another user account.")

    user_dict = dict(user)
    curr_email = user_dict.get("email")
    final_email = norm_email or curr_email
    final_avatar = str(avatar_url).strip() if avatar_url else user_dict.get("avatar_url")

    cursor.execute("""
    UPDATE users SET
        google_sub = ?,
        google_email = ?,
        auth_provider = 'both',
        avatar_url = COALESCE(?, avatar_url),
        updated_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """, (norm_sub, final_email, final_avatar, user_id))
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    updated_row = cursor.fetchone()
    conn.close()
    return sanitize_user_dict(updated_row)


def unlink_google_from_user(
    user_id: int,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Unlinks Google identity from an account.
    Fails if the account has no password set (pure Google account) to prevent account lockout.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise ValueError(f"User ID {user_id} not found.")

    u_dict = dict(user)
    pw_hash = u_dict.get("password_hash") or ""
    if pw_hash.startswith("!google_oauth_disabled_"):
        conn.close()
        raise ValueError("Cannot unlink Google identity without first setting a local password.")

    cursor.execute("""
    UPDATE users SET
        google_sub = NULL,
        google_email = NULL,
        auth_provider = 'local',
        updated_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """, (user_id,))
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    updated_row = cursor.fetchone()
    conn.close()
    return sanitize_user_dict(updated_row)


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


def count_admin_users(db_path: str = DEFAULT_DB_PATH) -> int:
    """Returns total number of active administrator accounts."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = ? AND is_active = 1;", (ROLE_ADMIN,))
    row = cursor.fetchone()
    count = row["count"] if row else 0
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
        if new_email:
            is_valid_e, e_err = validate_email(new_email)
            if not is_valid_e:
                conn.close()
                raise ValueError(e_err)
            cursor.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?) AND id != ?;", (new_email, user_id))
            if cursor.fetchone():
                conn.close()
                raise ValueError(f"Email '{new_email}' is already in use.")
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

    try:
        cursor.execute(sql, tuple(params))
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.close()
        err_str = str(e).lower()
        if "email" in err_str:
            raise ValueError(f"Email '{new_email}' is already in use.")
        raise ValueError(f"Database integrity error: {str(e)}")

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

    norm_username = str(username).strip()
    user = get_user_by_username(norm_username, include_password_hash=True, db_path=db_path)
    if not user:
        # Precomputed dummy verification to prevent timing discrepancy without runtime overhead
        check_password_hash(_DUMMY_PASSWORD_HASH, password)
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
