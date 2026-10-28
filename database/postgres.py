"""
PostgreSQL Backend Adapter for VisionGuard AI (Neon Serverless PostgreSQL).

Features:
- Thread-safe connection pooling for serverless and containerized deployments.
- Automatic query parameter placeholder translation (? -> %s).
- Non-destructive PostgreSQL schema creation with identical tables, types, constraints, and indexes.
- Sequence and primary key handling (RETURNING id).
- Safe credential handling (never logs passwords or connection strings).
"""

import os
import re
import logging
from typing import Optional, Dict, Any, Tuple, List, Generator
from contextlib import contextmanager

logger = logging.getLogger("visionguard.database.postgres")

# Global connection pool instance
_PG_POOL = None


def sanitize_db_url(url: str) -> str:
    """Masks credentials in database URL for safe logging."""
    if not url:
        return ""
    # Matches ://user:password@ and replaces with ://user:****@
    return re.sub(r"(://[^:]+):([^@]+)@", r"\1:****@", url)


def normalize_postgres_url(url: str) -> str:
    """Normalizes postgres:// scheme to postgresql:// for psycopg2 compatibility."""
    if not url:
        return ""
    clean = url.strip()
    if clean.startswith("postgres://"):
        return "postgresql://" + clean[11:]
    return clean


def adapt_sql(query: str, backend: str = "postgres") -> str:
    """
    Translates parameter placeholders between SQLite (?) and PostgreSQL (%s).
    Handles string literals safely to avoid replacing ? inside quotes.
    Translates sqlite_master to information_schema subquery for schema introspection.
    """
    if backend != "postgres":
        return query

    # Translate sqlite_master if present outside quotes
    adapted = query
    if "sqlite_master" in adapted:
        adapted = re.sub(
            r"\bsqlite_master\b",
            "(SELECT table_name AS name, 'table' AS type FROM information_schema.tables WHERE table_schema='public')",
            adapted,
            flags=re.IGNORECASE,
        )

    if "?" not in adapted:
        return adapted

    # Simple tokenizer preserving single and double quoted strings
    out = []
    in_quote = None
    i = 0
    n = len(adapted)

    while i < n:
        c = adapted[i]
        if in_quote:
            out.append(c)
            if c == in_quote:
                # Check for escaped quotes
                if i + 1 < n and adapted[i + 1] == in_quote:
                    out.append(adapted[i + 1])
                    i += 1
                else:
                    in_quote = None
        else:
            if c in ("'", '"'):
                in_quote = c
                out.append(c)
            elif c == "?":
                out.append("%s")
            else:
                out.append(c)
        i += 1

    return "".join(out)


class PostgresCursorWrapper:
    """
    Wrapper around psycopg2 cursor providing SQLite-compatible behavior:
    - Automatically translates '?' to '%s' via adapt_sql.
    - Captures generated IDs for INSERT statements via 'RETURNING id' into cursor.lastrowid.
    - Emulates 'PRAGMA table_info(<table>)' for compatibility with existing schema checks.
    - Supports row access by both column name and integer index via DictCursor.
    """

    def __init__(self, raw_cursor, conn_wrapper=None):
        self._cursor = raw_cursor
        self._conn_wrapper = conn_wrapper
        self.lastrowid = None

    def execute(self, query: str, params: Optional[Any] = None):
        # 1. Emulate PRAGMA table_info(table)
        pragma_match = re.match(r"^\s*PRAGMA\s+table_info\s*\(\s*([a-zA-Z0-9_]+)\s*\)\s*;?\s*$", query, re.IGNORECASE)
        if pragma_match:
            table_name = pragma_match.group(1).lower()
            pragma_sql = """
                SELECT ordinal_position - 1 AS cid,
                       column_name AS name,
                       data_type AS type,
                       CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull,
                       column_default AS dflt_value,
                       0 AS pk
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
            """
            self._cursor.execute(pragma_sql, (table_name,))
            self.lastrowid = None
            return self

        # 2. Adapt SQL placeholders (? -> %s)
        adapted = adapt_sql(query, "postgres")

        # 3. Check for INSERT without RETURNING
        is_insert = bool(re.match(r"^\s*INSERT\s+INTO\s+", adapted, re.IGNORECASE))
        has_returning = bool(re.search(r"\bRETURNING\b", adapted, re.IGNORECASE))

        if is_insert and not has_returning:
            stripped = adapted.rstrip().rstrip(";")
            adapted_returning = f"{stripped} RETURNING id;"
            try:
                if params is not None:
                    self._cursor.execute(adapted_returning, params)
                else:
                    self._cursor.execute(adapted_returning)
                row = self._cursor.fetchone()
                if row:
                    self.lastrowid = row[0]
                return self
            except Exception:
                # If table does not have an 'id' column or RETURNING failed, fallback to standard execute
                self._cursor.execute(adapted, params if params is not None else ())
                self.lastrowid = None
                return self
        else:
            if params is not None:
                self._cursor.execute(adapted, params)
            else:
                self._cursor.execute(adapted)
            self.lastrowid = None
            return self

    def executemany(self, query: str, seq_of_params: Any):
        adapted = adapt_sql(query, "postgres")
        self._cursor.executemany(adapted, seq_of_params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size: Optional[int] = None):
        if size is None:
            return self._cursor.fetchmany()
        return self._cursor.fetchmany(size)

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        try:
            self._cursor.close()
        except Exception:
            pass

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class PostgresConnectionWrapper:
    """
    Wrapper around pooled PostgreSQL connection providing SQLite-like API:
    - conn.cursor() returns a PostgresCursorWrapper with DictCursor.
    - conn.commit() / conn.rollback().
    - conn.close() safely returns the connection to the connection pool.
    - Context manager support for transactions.
    """

    def __init__(self, raw_conn, pool_manager=None):
        self._raw_conn = raw_conn
        self._pool_manager = pool_manager
        self._closed = False
        self.row_factory = None  # Compatible attribute placeholder

    def cursor(self):
        from psycopg2.extras import DictCursor
        raw_cur = self._raw_conn.cursor(cursor_factory=DictCursor)
        return PostgresCursorWrapper(raw_cur, self)

    def commit(self):
        self._raw_conn.commit()

    def rollback(self):
        self._raw_conn.rollback()

    def close(self):
        if not self._closed:
            self._closed = True
            if self._pool_manager:
                self._pool_manager.put_connection(self._raw_conn)
            else:
                self._raw_conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


class PostgresConnectionManager:
    """Manages connection pooling and lifecycle for Neon PostgreSQL."""

    def __init__(self, database_url: str, minconn: int = 1, maxconn: int = 10, pool_override: Optional[Any] = None):
        self.raw_url = database_url
        self.database_url = normalize_postgres_url(database_url)
        self.minconn = minconn
        self.maxconn = maxconn

        if pool_override is not None:
            self._pool = pool_override
        else:
            try:
                import psycopg2
                from psycopg2.pool import ThreadedConnectionPool
            except ImportError:
                raise RuntimeError(
                    "PostgreSQL driver 'psycopg2' is not installed. Run 'pip install psycopg2-binary' to enable PostgreSQL support."
                )

            try:
                self._pool = ThreadedConnectionPool(
                    minconn=self.minconn,
                    maxconn=self.maxconn,
                    dsn=self.database_url,
                )
                logger.info(f"Initialized PostgreSQL connection pool (dsn={sanitize_db_url(self.database_url)})")
            except Exception as exc:
                sanitized = sanitize_db_url(self.database_url)
                logger.error(f"Failed to connect to PostgreSQL ({sanitized}): {exc}")
                raise RuntimeError(f"Database connection error: Could not connect to PostgreSQL ({sanitized})") from exc

    def get_connection(self):
        """Acquires a connection from the pool."""
        conn = self._pool.getconn()
        return conn

    def put_connection(self, conn, close: bool = False):
        """Returns a connection to the pool."""
        if self._pool is not None and conn is not None:
            self._pool.putconn(conn, close=close)

    def close_all(self):
        """Closes all connections in the pool."""
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None


def is_postgres_url(url: Optional[str]) -> bool:
    """Checks whether a database URL or path is for PostgreSQL."""
    if not url:
        return False
    u = url.strip().lower()
    return u.startswith("postgres://") or u.startswith("postgresql://")


def get_postgres_pool(database_url: Optional[str] = None) -> PostgresConnectionManager:
    """Singleton getter for the global PostgreSQL connection manager."""
    global _PG_POOL
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL must be specified to initialize PostgreSQL connection pool.")

    if _PG_POOL is None or _PG_POOL.raw_url != url:
        if _PG_POOL is not None:
            try:
                _PG_POOL.close_all()
            except Exception:
                pass
        _PG_POOL = PostgresConnectionManager(url)
    return _PG_POOL


def get_wrapped_postgres_connection(database_url: Optional[str] = None) -> PostgresConnectionWrapper:
    """Acquires a pooled PostgreSQL connection and wraps it in a PostgresConnectionWrapper."""
    manager = get_postgres_pool(database_url)
    raw_conn = manager.get_connection()
    return PostgresConnectionWrapper(raw_conn, manager)


@contextmanager
def get_postgres_connection(database_url: Optional[str] = None):
    """
    Context manager that yields a PostgreSQL connection and guarantees
    it is returned to the pool after the block completes.
    """
    manager = get_postgres_pool(database_url)
    conn = manager.get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        manager.put_connection(conn)


POSTGRES_SCHEMA_SQL = """
-- VisionGuard AI PostgreSQL Schema (Neon Compatible)

CREATE TABLE IF NOT EXISTS defect_inspections (
    id SERIAL PRIMARY KEY,
    image_name TEXT NOT NULL,
    file_path TEXT,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'uploaded',
    defect_type TEXT,
    confidence REAL,
    severity TEXT,
    notes TEXT,
    original_image_path TEXT,
    annotated_image_path TEXT,
    road_name TEXT,
    location_notes TEXT,
    inspection_mode TEXT DEFAULT 'standard',
    confidence_threshold REAL DEFAULT 0.25,
    defect_count INTEGER DEFAULT 0,
    detections_json TEXT DEFAULT '[]',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    area TEXT,
    city TEXT,
    latitude REAL,
    longitude REAL,
    target_repair_date TEXT,
    created_by_user_id INTEGER,
    created_by_username TEXT,
    assigned_to_user_id INTEGER,
    assigned_to_username TEXT,
    assigned_by_user_id INTEGER,
    assigned_by_username TEXT,
    assigned_at TIMESTAMP WITH TIME ZONE,
    assignment_instructions TEXT,
    assignment_status TEXT DEFAULT 'unassigned',
    assignment_updated_at TIMESTAMP WITH TIME ZONE,
    inspection_type TEXT DEFAULT 'road'
);

CREATE INDEX IF NOT EXISTS idx_inspections_assigned ON defect_inspections (assigned_to_user_id, assignment_status);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'inspector',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS complaint_drafts (
    id SERIAL PRIMARY KEY,
    inspection_id INTEGER NOT NULL UNIQUE,
    complaint_type TEXT NOT NULL DEFAULT 'road_distress',
    recipient_agency TEXT NOT NULL,
    subject TEXT NOT NULL,
    complaint_body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_by_user_id INTEGER,
    created_by_username TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    complainant_name TEXT,
    complainant_contact TEXT,
    submission_channel TEXT,
    submission_reference TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (inspection_id) REFERENCES defect_inspections(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_complaint_drafts_insp ON complaint_drafts (inspection_id);

CREATE TABLE IF NOT EXISTS maintenance_assignments (
    id SERIAL PRIMARY KEY,
    inspection_id INTEGER NOT NULL,
    assigned_to_user_id INTEGER NOT NULL,
    assigned_to_username TEXT NOT NULL,
    assigned_by_user_id INTEGER NOT NULL,
    assigned_by_username TEXT NOT NULL,
    instructions TEXT,
    status TEXT NOT NULL DEFAULT 'assigned',
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    cancelled_at TIMESTAMP WITH TIME ZONE,
    cancellation_reason TEXT,
    FOREIGN KEY (inspection_id) REFERENCES defect_inspections(id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_to_user_id) REFERENCES users(id),
    FOREIGN KEY (assigned_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_assignments_insp ON maintenance_assignments (inspection_id);
CREATE INDEX IF NOT EXISTS idx_assignments_user_st ON maintenance_assignments (assigned_to_user_id, status);

CREATE TABLE IF NOT EXISTS maintenance_activity_log (
    id SERIAL PRIMARY KEY,
    inspection_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT,
    previous_target_date TEXT,
    new_target_date TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER,
    username TEXT,
    FOREIGN KEY (inspection_id) REFERENCES defect_inspections(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS system_metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""


def init_postgres_db(conn) -> None:
    """Executes non-destructive schema initialization on PostgreSQL."""
    try:
        from psycopg2.extras import DictCursor
    except ImportError:
        DictCursor = None

    cursor = conn.cursor()
    cursor.execute(POSTGRES_SCHEMA_SQL)

    # Ensure schema_version metadata is recorded
    cursor.execute("""
        INSERT INTO system_metadata (key, value, updated_at)
        VALUES ('schema_version', '1.0', CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO NOTHING;
    """)
    conn.commit()
    cursor.close()
    logger.info("Verified PostgreSQL schema tables and indexes.")
