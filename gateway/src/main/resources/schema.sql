CREATE TABLE IF NOT EXISTS user (
    id            INTEGER PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS book (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    author     TEXT,
    cover_url  TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapter (
    id            INTEGER PRIMARY KEY,
    book_id       INTEGER NOT NULL,
    chapter_index INTEGER NOT NULL,
    title         TEXT NOT NULL,
    text          TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE (book_id, chapter_index)
);

CREATE TABLE IF NOT EXISTS reading_progress (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    book_id       INTEGER NOT NULL,
    chapter_index INTEGER NOT NULL,
    scroll_ratio  REAL NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    UNIQUE (user_id, book_id)
);

CREATE TABLE IF NOT EXISTS chat_session (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    book_id    INTEGER NOT NULL,
    title      TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_message (
    id             INTEGER PRIMARY KEY,
    session_id     INTEGER NOT NULL,
    role           TEXT NOT NULL,
    content        TEXT NOT NULL,
    citations_json TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempt (
    id         INTEGER PRIMARY KEY,
    username   TEXT,
    ip         TEXT,
    success    INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_message_session ON chat_message (session_id);
CREATE INDEX IF NOT EXISTS idx_chat_session_user ON chat_session (user_id, book_id);
CREATE INDEX IF NOT EXISTS idx_login_attempt_ip ON login_attempt (ip, created_at);
CREATE INDEX IF NOT EXISTS idx_reading_progress_user ON reading_progress (user_id, book_id);

CREATE TABLE IF NOT EXISTS plan_catalog (
    code          TEXT PRIMARY KEY,
    price         REAL NOT NULL,
    credits       INTEGER NOT NULL,
    duration_days INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS balance_ledger (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    type          TEXT NOT NULL,
    amount        REAL NOT NULL,
    balance_after REAL NOT NULL,
    ref           TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_ledger (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    type          TEXT NOT NULL,
    amount        INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    ref           TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_api_key (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    provider        TEXT NOT NULL,
    encrypted_key   TEXT NOT NULL,
    key_mask        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL,
    last_checked_at TEXT,
    UNIQUE (user_id, provider)
);

CREATE TABLE IF NOT EXISTS model_catalog (
    id             INTEGER PRIMARY KEY,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    display_name   TEXT,
    plans          TEXT NOT NULL,
    byok_supported INTEGER NOT NULL DEFAULT 1,
    status         TEXT NOT NULL DEFAULT 'active',
    UNIQUE (provider, model)
);

CREATE TABLE IF NOT EXISTS usage_record (
    id                INTEGER PRIMARY KEY,
    user_id           INTEGER NOT NULL,
    session_id        INTEGER NOT NULL,
    mode              TEXT NOT NULL,
    provider          TEXT,
    model             TEXT,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    credits           INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_record (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    plan          TEXT NOT NULL,
    amount        REAL NOT NULL,
    balance_after REAL NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_balance_ledger_user ON balance_ledger (user_id);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_user ON credit_ledger (user_id);
CREATE INDEX IF NOT EXISTS idx_usage_record_user ON usage_record (user_id);
CREATE INDEX IF NOT EXISTS idx_purchase_record_user ON purchase_record (user_id);
