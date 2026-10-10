-- 用户 / 会话 / 进度 五张表（docs/m1/多轮会话落地方案.md §二）。
--
-- 全部 CREATE ... IF NOT EXISTS：SQLite 没有独立的迁移工具，一期就是启动时幂等建表
-- （选型理由见 docs/m1/java-依赖与选型.md §三：四张表、单实例，引 Flyway / Liquibase
-- 要多一个依赖与一套配置）。变更记 schema_version，由 SchemaInitializer 写。
--
-- 时间一律存 ISO-8601 字符串而不是 SQLite 的日期类型：避开时区与 typeHandler 依赖。

CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,                    -- 只存 BCrypt 哈希，明文永不落库
  status        TEXT NOT NULL DEFAULT 'active',   -- active / disabled
  created_at    TEXT NOT NULL,
  last_login_at TEXT
);

-- 登录会话：不透明 token，**库里只存哈希**，原文只在 cookie 里。
-- 不用 JWT 也不用容器 HttpSession 的理由见 java-依赖与选型.md §十——
-- D15 的「停用即失效」要求按用户批量吊销，这里一条 DELETE 就能做到。
CREATE TABLE IF NOT EXISTS auth_sessions (
  token_hash   TEXT PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at   TEXT NOT NULL,
  expires_at   TEXT NOT NULL,
  last_seen_at TEXT
);

-- 按账户的阅读进度：一个账户一本书一行。不带 user_id 的话所有人共享一份「读到哪」，
-- 一个人翻页另一个人跟着变，而两边都不会报错。
CREATE TABLE IF NOT EXISTS user_progress (
  user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book_id  INTEGER NOT NULL,
  progress INTEGER NOT NULL,
  PRIMARY KEY (user_id, book_id)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
  id             TEXT PRIMARY KEY,                 -- uuid
  user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book_id        INTEGER NOT NULL,
  title          TEXT NOT NULL,                    -- 首轮生成
  level          TEXT NOT NULL DEFAULT 'past',     -- **会话内固定**：切档位走分叉，不就地改
  forked_from    TEXT REFERENCES chat_sessions(id) ON DELETE SET NULL,
  -- 从父会话复制到哪条消息为止：存的是**消息 seq，不是轮号**。
  -- 外部契约的 ForkRequest.at_seq 就是这个口径（「复制到哪条消息为止（含）」）。
  -- 写成轮号也能自洽，但两者只差一个数，拿错了不会报错——只会让分叉少带一段上下文。
  forked_at_seq  INTEGER,
  summary        TEXT,
  summary_upto   INTEGER,                          -- 摘要覆盖到哪条 message.id；与 summary 同一次更新
  -- 这份摘要出自哪一版摘要模板。摘要会长期留在会话里，模板改了之后，
  -- 库里的老摘要得能分辨出来自哪一版——同 rag_runs.prompt_version 的口径。
  -- 与 summary / summary_upto 同一次更新，三者的「版本」应当一致。
  summary_prompt_version TEXT,
  created_at     TEXT NOT NULL,
  last_active_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions (user_id, last_active_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  seq         INTEGER NOT NULL,                    -- 会话内序号
  role        TEXT NOT NULL,                       -- user / assistant
  content     TEXT NOT NULL,
  token_count INTEGER,                             -- Java 侧字符估算，不是权威值
  created_at  TEXT NOT NULL,
  meta        TEXT,                                -- JSON：引用编号、context_chapters、改写前后、模型与 prompt 版本
  UNIQUE (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages (session_id, seq);

-- 表结构自身的版本。启动时记一次；**库里比代码新就拒绝启动**——
-- 与 run 产物那条「产物比代码新先更新代码」的口径一致。
CREATE TABLE IF NOT EXISTS schema_version (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);
