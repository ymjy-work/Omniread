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
