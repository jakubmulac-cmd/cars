CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (sha256 TEXT PRIMARY KEY, as_of TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, payload TEXT NOT NULL, report TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'staged', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vehicles (asset_id TEXT PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, name TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources (source_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records (
 collection TEXT NOT NULL, record_id TEXT NOT NULL,
 asset_id TEXT REFERENCES vehicles(asset_id), source_id TEXT REFERENCES sources(source_id),
 payload TEXT NOT NULL, PRIMARY KEY (collection, record_id)
);
CREATE INDEX IF NOT EXISTS records_by_asset ON records(asset_id, collection);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY CHECK(id = 1), password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (client TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS issue_updates (
 issue_id TEXT PRIMARY KEY, assigned_to TEXT, state TEXT NOT NULL DEFAULT 'Otevřeno',
 evidence_type TEXT, evidence_title TEXT, evidence_url TEXT, evidence_date TEXT,
 closure_note TEXT, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS manual_readings (
 id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES vehicles(asset_id), km TEXT NOT NULL,
 date TEXT NOT NULL, evidence TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, action TEXT NOT NULL, target TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
