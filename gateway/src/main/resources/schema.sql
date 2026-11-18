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
