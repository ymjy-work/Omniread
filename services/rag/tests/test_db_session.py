"""数据库连接的装配：连接超时（离线，不连库）。

真库上的连通性由 `scripts/verify-data-layer.sh` 核对；这里只钉「超时怎么取值」——
它的意义是**连不上时尽快失败**：不给超时等的是 TCP 超时（几分钟），
界面上表现为无限转圈、零提示，而这一层本该以 503 说出来。
"""

from __future__ import annotations

import pytest

from omniread.infrastructure.db.session import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    connect_timeout_seconds,
    database_url,
)


class TestConnectTimeout:
    def test_defaults_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POSTGRES_CONNECT_TIMEOUT", raising=False)
        assert connect_timeout_seconds() == DEFAULT_CONNECT_TIMEOUT_SECONDS

    def test_blank_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_CONNECT_TIMEOUT", "   ")
        assert connect_timeout_seconds() == DEFAULT_CONNECT_TIMEOUT_SECONDS

    def test_reads_seconds_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_CONNECT_TIMEOUT", "12")
        assert connect_timeout_seconds() == 12

    @pytest.mark.parametrize("raw", ["abc", "0", "-3", "1.5", ""])
    def test_rejects_nonsense(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        # 空串走默认值，其余一律显式失败——静默用一个别的秒数比报错更难查。
        monkeypatch.setenv("POSTGRES_CONNECT_TIMEOUT", raw)
        if raw == "":
            assert connect_timeout_seconds() == DEFAULT_CONNECT_TIMEOUT_SECONDS
            return
        with pytest.raises(RuntimeError):
            connect_timeout_seconds()


class TestSslParams:
    """`sslmode` 与 `sslrootcert` 怎么拼进连接串。

    这两个必须成对出现才叫「校验」：只给 `verify-full` 不给 CA，psycopg 会退到系统
    信任库去找 RDS 的签发者——那里没有，症状是连不上而不是降级。
    """

    @pytest.fixture(autouse=True)
    def _password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
        monkeypatch.delenv("POSTGRES_SSLMODE", raising=False)
        monkeypatch.delenv("POSTGRES_SSLROOTCERT", raising=False)

    def test_no_ssl_params_by_default(self) -> None:
        # 本地 Docker 的 PG 不走 TLS，连接串保持原样。
        assert "?" not in database_url()

    def test_sslmode_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_SSLMODE", "verify-full")
        assert database_url().endswith("?sslmode=verify-full")

    def test_root_cert_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_SSLROOTCERT", "/app/certs/global-bundle.pem")
        assert database_url().endswith("?sslrootcert=%2Fapp%2Fcerts%2Fglobal-bundle.pem")

    def test_both_joined_with_ampersand(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_SSLMODE", "verify-full")
        monkeypatch.setenv("POSTGRES_SSLROOTCERT", "/app/certs/global-bundle.pem")
        url = database_url()
        assert "?sslmode=verify-full&sslrootcert=" in url
        assert url.count("?") == 1
