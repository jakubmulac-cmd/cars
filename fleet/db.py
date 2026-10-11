import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def now():
    return datetime.now(timezone.utc).isoformat()


def data_dir():
    return Path(os.environ.get("FLEET_DATA_DIR", str(ROOT / ".local"))).resolve()


@contextmanager
def connect():
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    con = sqlite3.connect(directory / "fleet.sqlite3", timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
    finally:
        con.close()


def migrate():
    with connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for path in sorted((ROOT / "fleet/migrations").glob("*.sql")):
            version = int(path.name.split("_", 1)[0])
            if not con.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone():
                con.executescript("BEGIN IMMEDIATE;\n" + path.read_text() + f"\nINSERT INTO schema_migrations VALUES ({version}, '{now()}');\nCOMMIT;")
        os.chmod(data_dir() / "fleet.sqlite3", 0o600)


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def audit(con, action, target, details):
    con.execute("INSERT INTO audit_log(action,target,details,created_at) VALUES (?,?,?,?)", (action, target, encode(details), now()))


def collection(con, name):
    if name == "vehicles":
        rows = con.execute("SELECT payload FROM vehicles ORDER BY asset_id")
    elif name == "sources":
        rows = con.execute("SELECT payload FROM sources ORDER BY source_id")
    else:
        rows = con.execute("SELECT payload FROM records WHERE collection=? ORDER BY record_id", (name,))
    return [json.loads(row[0]) for row in rows]


def metadata(con):
    return {r[0]: json.loads(r[1]) for r in con.execute("SELECT key,value FROM metadata")}
