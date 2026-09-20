-- pgvector 镜像只提供扩展文件，不会自动 CREATE EXTENSION。
-- Alembic 迁移会直接使用 vector 类型，所以扩展必须在建表之前就位。
-- 本文件由官方镜像的 docker-entrypoint-initdb.d 机制执行，
-- 只在数据卷首次初始化时跑一次；已有数据卷不会重跑。
CREATE EXTENSION IF NOT EXISTS vector;
