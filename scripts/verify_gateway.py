#!/usr/bin/env python
"""M0-6 Java 网关联调断言：外部 API → Java → Python 内部契约。

由 `scripts/verify-gateway.sh` 分阶段调用（`--phase`）——Java 与 Python 的起停、以及
故障注入用的 Python 重启都在 shell 侧，本脚本只做 HTTP 断言，不碰进程。

三个阶段：

- `main`：六组 GET 的 Java/Python 一致性、插图字节与 Content-Type、目录穿越被拒、
  同步与流式问答透传、`request_id` 生成与透传、SSE 逐帧到达（不被缓冲）、
  进度由 Java 本地读写（Python 侧无该路由）。
- `fault-provider` / `fault-timeout`：假 provider 注入故障，断言 Java 把上游 502 / 504
  原样映射成 `RAG_PROVIDER_ERROR` / `RAG_TIMEOUT`，不降级成拒答。
- `offline`：Python 不可达时 Java 返回 503 `RAG_UNAVAILABLE`；进度端点仍从本地读写，
  证明它没有转发 Python。

全程只走 HTTP，不 import 服务端代码；凭据只由 shell 通过环境变量给 Python 进程。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{32}$")
SECRET_MARKER = "omniread-e2e-secret-should-never-be-served"

QUESTION_BODY = {
    "book_id": 1,
    "question": "艾莉 俄语",
    "level": "past",
    "progress": 45,
}

# 目录穿越候选：反斜杠、百分号转义、归一化后越界三类，任何一条被服务端读取都算失败。
TRAVERSAL_PATHS = (
    "../secret.txt",
    "a/../../secret.txt",
    "..%2Fsecret.txt",
    "%2e%2e/secret.txt",
)

# 语料内相对路径：HTTP 客户端会按 UTF-8 百分号编码，服务端解码后按同一份 key 取图。
IMAGE_PATH = "01_第1卷/007.jpg"


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def ok(self, message: str) -> None:
        print(f"  OK   {message}")
        self.passed += 1

    def bad(self, message: str, detail: str) -> None:
        print(f"  FAIL {message}\n       {detail}")
        self.failed += 1

    def check(self, condition: bool, message: str, detail: str = "") -> None:
        if condition:
            self.ok(message)
        else:
            self.bad(message, detail)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def parse_sse(raw: str) -> list[tuple[str | None, str]]:
    frames: list[tuple[str | None, str]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event: str | None = None
        data = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        frames.append((event, data))
    return frames


def get_json(client: httpx.Client, url: str) -> tuple[int, object]:
    response = client.get(url)
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, response.text


def internal_url(python_base: str, suffix: str) -> str:
    return f"{python_base}/internal/v1{suffix}"


def external_url(java_base: str, suffix: str) -> str:
    return f"{java_base}/api/v1{suffix}"


def check_catalog_parity(client: httpx.Client, checker: Checker, java_base: str, python_base: str) -> None:
    section("1 六组 GET：Java 与 Python 直连一致")
    for suffix in ("/books", "/books/1/chapters", "/books/1/chapters/17"):
        java_status, java_body = get_json(client, external_url(java_base, suffix))
        py_status, py_body = get_json(client, internal_url(python_base, suffix))
        checker.check(
            java_status == py_status == 200,
            f"GET {suffix}：Java 与 Python 都 200（Java={java_status} Python={py_status}）",
        )
        checker.check(
            java_body == py_body,
            f"GET {suffix}：响应 JSON 与 Python 直连一致",
            f"Java={json.dumps(java_body, ensure_ascii=False)[:200]}\n"
            f"Python={json.dumps(py_body, ensure_ascii=False)[:200]}",
        )

    java_status, java_body = get_json(client, external_url(java_base, "/health"))
    py_status, py_body = get_json(client, internal_url(python_base, "/health"))
    checker.check(java_status == 200 and py_status == 200, "GET /health：两侧都 200")
    checker.check(
        java_body == {"status": "ok", "service": "omniread-backend"}
        and py_body == {"status": "ok", "service": "omniread-rag"},
        "GET /health：各自报自己的 service（Java 不探 Python）",
        f"Java={java_body} Python={py_body}",
    )


def check_image(client: httpx.Client, checker: Checker, java_base: str, python_base: str) -> None:
    section("2 插图端点：字节级一致、Content-Type 正确、目录穿越被拒")
    java = client.get(external_url(java_base, f"/books/1/images/{IMAGE_PATH}"))
    py = client.get(internal_url(python_base, f"/books/1/images/{IMAGE_PATH}"))
    checker.check(java.status_code == 200 and py.status_code == 200, "GET 插图：两侧都 200")
    checker.check(java.content == py.content, "插图字节与 Python 直连一致")
    checker.check(
        java.headers.get("content-type", "").startswith("image/jpeg")
        and py.headers.get("content-type", "").startswith("image/jpeg"),
        "Content-Type 是 image/jpeg",
        f"Java={java.headers.get('content-type')} Python={py.headers.get('content-type')}",
    )
    print(f"  图片={IMAGE_PATH} bytes={len(java.content)}")

    for path in TRAVERSAL_PATHS:
        # 直接拼字符串交给 httpx：默认不做 dot-segment 归一化，等价于 curl --path-as-is。
        response = client.get(external_url(java_base, f"/books/1/images/{path}"))
        leaked = SECRET_MARKER.encode() in response.content
        checker.check(
            response.status_code in (400, 404) and not leaked,
            f"目录穿越被拒：{path} → {response.status_code}",
            f"状态 {response.status_code}，正文泄漏={leaked}",
        )


def check_query(client: httpx.Client, checker: Checker, java_base: str, python_base: str) -> None:
    section("3 同步问答：Java 透传 Python")
    java = client.post(external_url(java_base, "/query"), json=QUESTION_BODY)
    py = client.post(internal_url(python_base, "/rag/query"), json=QUESTION_BODY)

    checker.check(java.status_code == 200 and py.status_code == 200, "POST /query：两侧都 200")
    java_body = java.json()
    py_body = py.json()
    checker.check(
        java_body["status"] == py_body["status"]
        and java_body["answer"] == py_body["answer"]
        and java_body["context_chapters"] == py_body["context_chapters"],
        "同步问答：status / answer / context_chapters 与 Python 直连一致",
        f"Java={java_body.get('status')} Python={py_body.get('status')}",
    )
    checker.check(
        java_body["status"] in ("answered", "insufficient_evidence"),
        "同步问答：200 是 answered / insufficient_evidence 的正常业务结果",
        str(java_body.get("status")),
    )
    print(f"  status={java_body['status']} answer={java_body['answer']!r}")


def check_request_id(client: httpx.Client, checker: Checker, java_base: str, python_log: Path) -> str:
    section("4 request_id：Java 生成、透传、响应头与响应体一致")
    response = client.post(
        external_url(java_base, "/query"),
        json=QUESTION_BODY,
        headers={"X-Request-Id": "req_ffffffffffffffffffffffffffffffff"},
    )
    header_id = response.headers.get("x-request-id", "")
    body_id = response.json().get("request_id", "")
    checker.check(bool(REQUEST_ID_PATTERN.fullmatch(header_id)), f"响应头是 req_+32 位十六进制：{header_id}")
    checker.check(header_id == body_id, "响应头与响应体 request_id 一致", f"header={header_id} body={body_id}")
    checker.check(
        header_id != "req_ffffffffffffffffffffffffffffffff",
        "客户端伪造的 X-Request-Id 被忽略（id 由 Java 生成）",
    )
    if python_log.is_file():
        forwarded = header_id in python_log.read_text(encoding="utf-8", errors="replace")
        checker.check(forwarded, "Python 日志里出现同一个 request_id（Java 向下透传）", str(python_log))
    else:
        checker.bad("读取 Python 日志", f"找不到 {python_log}")
    return header_id


def check_stream(client: httpx.Client, checker: Checker, java_base: str, delay_ms: int) -> None:
    section("5 SSE：经 Java 透传、逐帧到达不被缓冲")
    # 先预热：首次查询要建 BM25 索引，会把时间花在检索而不是流式上。
    client.post(external_url(java_base, "/query"), json=QUESTION_BODY, timeout=60)

    start = time.perf_counter()
    first_frame_at: float | None = None
    lines: list[str] = []
    with client.stream(
        "POST", external_url(java_base, "/query/stream"), json=QUESTION_BODY, timeout=60
    ) as response:
        checker.check(response.status_code == 200, f"流式响应状态 200（实际 {response.status_code}）")
        checker.check(
            response.headers.get("content-type", "").startswith("text/event-stream"),
            "Content-Type 是 text/event-stream",
            response.headers.get("content-type", ""),
        )
        for line in response.iter_lines():
            if first_frame_at is None and line.strip():
                first_frame_at = time.perf_counter() - start
            lines.append(line)
    total = time.perf_counter() - start
    raw = "\n".join(lines)
    frames = parse_sse(raw)
    names = [event for event, _ in frames]
    deltas = [name for name in names if name == "answer_delta"]

    checker.check("query_started" in names, "事件流含 query_started")
    checker.check(bool(deltas), "事件流含 answer_delta（模型逐段产出）")
    checker.check("citation_ready" in names and "query_done" in names, "事件流以 citation_ready + query_done 收尾")
    checker.check(frames[-1][1] == "[DONE]", "SSE 以 data: [DONE] 终止", repr(frames[-1]))
    checker.check(
        frames[-1][0] is None and names.count("query_done") == 1,
        "query_done 之后只跟 [DONE]",
    )
    first = first_frame_at if first_frame_at is not None else -1
    print(f"  首帧={first * 1000:.0f}ms 总时长={total * 1000:.0f}ms 帧数={len(frames)} delta={len(deltas)}")
    checker.check(
        total >= (delay_ms / 1000) * len(deltas) * 0.5,
        f"流式总时长受逐块延迟影响（≈{delay_ms}ms×{len(deltas)}，说明确实在逐块产出）",
        f"total={total:.3f}s",
    )
    checker.check(
        0 <= first < total / 2,
        "首帧远早于流结束（未被缓冲到整条流跑完）",
        f"first={first:.3f}s total={total:.3f}s",
    )


def check_progress(
    client: httpx.Client,
    checker: Checker,
    java_base: str,
    python_base: str,
    progress_file: Path,
    python_log: Path,
) -> None:
    section("6 进度：Java 本地读写，不经过 Python")
    py_status = client.get(internal_url(python_base, "/books/1/progress")).status_code
    checker.check(py_status == 404, "Python 内部契约没有 progress 路由（404）", str(py_status))

    # 上面那条 404 探测本身就是一次进度路径的请求，日志里当然会有；基准点取在它之后，
    # 只检查「Java 的读写有没有在 Python 侧留下新请求」。
    baseline = python_log.stat().st_size if python_log.is_file() else 0
    put = client.put(external_url(java_base, "/books/1/progress"), json={"max_seq": 42})
    get = client.get(external_url(java_base, "/books/1/progress"))
    checker.check(put.status_code == 200 and get.status_code == 200, "PUT / GET progress 都 200")
    checker.check(get.json() == {"book_id": 1, "max_seq": 42}, "进度写入后能读回", str(get.json()))
    checker.check(
        progress_file.is_file() and json.loads(progress_file.read_text(encoding="utf-8")) == get.json(),
        "进度落在 Java 本地文件",
        str(progress_file),
    )
    checker.check(
        client.put(external_url(java_base, "/books/1/progress"), json={"max_seq": 999}).status_code == 400,
        "progress 越界 → 400（Java 边界校验）",
    )

    if python_log.is_file():
        appended = python_log.read_bytes()[baseline:].decode("utf-8", errors="replace")
        checker.check(
            "progress" not in appended,
            "Java 读写进度期间 Python 日志无新增请求（进度没被转发）",
            appended[-200:],
        )


def check_invalid_input(client: httpx.Client, checker: Checker, java_base: str) -> None:
    section("7 入参非法：Java 边界校验 400 RAG_INVALID_REALM")
    cases = (
        ("level=past 缺 progress", {"book_id": 1, "question": "x", "level": "past"}),
        ("progress 越界", {"book_id": 1, "question": "x", "level": "past", "progress": 999}),
        ("level 非法", {"book_id": 1, "question": "x", "level": "nowhere"}),
        ("book_id 不存在", {"book_id": 999, "question": "x", "level": "full"}),
    )
    for label, body in cases:
        response = client.post(external_url(java_base, "/query"), json=body)
        payload = response.json() if response.status_code != 200 else {}
        checker.check(
            response.status_code == 400 and payload.get("code") == "RAG_INVALID_REALM",
            f"{label} → 400 RAG_INVALID_REALM",
            f"{response.status_code} {payload}",
        )


def check_fault(client: httpx.Client, checker: Checker, java_base: str, fault: str) -> None:
    expected_code = "RAG_PROVIDER_ERROR" if fault == "provider_error" else "RAG_TIMEOUT"
    expected_status = 502 if fault == "provider_error" else 504
    section(f"8 上游 provider 故障（注入 {fault}）→ {expected_status} {expected_code}")

    response = client.post(external_url(java_base, "/query"), json=QUESTION_BODY)
    payload = response.json() if response.status_code != 200 else {}
    checker.check(
        response.status_code == expected_status and payload.get("code") == expected_code,
        f"同步问答映射成 {expected_status} {expected_code}",
        f"{response.status_code} {payload}",
    )
    checker.check(
        bool(REQUEST_ID_PATTERN.fullmatch(response.headers.get("x-request-id", ""))),
        "故障响应仍带 Java 生成的 X-Request-Id",
    )
    stream = client.post(external_url(java_base, "/query/stream"), json=QUESTION_BODY)
    frames = parse_sse(stream.text)
    names = [event for event, _ in frames]
    # 生成阶段才抛故障：前面几条检索事件已经发出，失败只能用末尾的 error 帧表达。
    checker.check(
        stream.status_code == 200
        and bool(frames)
        and frames[-1][0] == "error"
        and json.loads(frames[-1][1])["code"] == expected_code,
        f"SSE 末尾以 event: error 携带 {expected_code}",
        stream.text[-200:],
    )
    checker.check(
        "query_done" not in names and "[DONE]" not in stream.text,
        "故障流没有 query_done / [DONE]（与正常结束互斥）",
        str(names),
    )


def check_offline(client: httpx.Client, checker: Checker, java_base: str, progress_file: Path) -> None:
    section("9 Python 不可达：503 RAG_UNAVAILABLE；进度仍本地可用")
    response = client.post(external_url(java_base, "/query"), json=QUESTION_BODY)
    payload = response.json() if response.status_code != 200 else {}
    checker.check(
        response.status_code == 503 and payload.get("code") == "RAG_UNAVAILABLE",
        "POST /query → 503 RAG_UNAVAILABLE",
        f"{response.status_code} {payload}",
    )
    books = client.get(external_url(java_base, "/books"))
    checker.check(books.status_code == 503, "GET /books → 503 RAG_UNAVAILABLE", str(books.status_code))

    progress = client.get(external_url(java_base, "/books/1/progress"))
    checker.check(
        progress.status_code == 200 and progress.json() == {"book_id": 1, "max_seq": 42},
        "Python 停止后 GET progress 仍 200（证明进度完全落在 Java 本地）",
        f"{progress.status_code} {progress.text[:120]}",
    )
    checker.check(progress_file.is_file(), "进度文件仍在本地", str(progress_file))


def main() -> int:
    parser = argparse.ArgumentParser(description="M0-6 Java 网关联调断言")
    parser.add_argument("--java-base", default="http://127.0.0.1:8080")
    parser.add_argument("--python-base", default="http://127.0.0.1:8000")
    parser.add_argument("--phase", required=True, choices=("main", "fault-provider", "fault-timeout", "offline"))
    parser.add_argument("--progress-file", type=Path, required=True)
    parser.add_argument("--python-log", type=Path, required=True)
    parser.add_argument("--stream-delay-ms", type=int, default=200)
    args = parser.parse_args()

    checker = Checker()
    with httpx.Client(timeout=30.0, follow_redirects=False) as client:
        if args.phase == "main":
            check_catalog_parity(client, checker, args.java_base, args.python_base)
            check_image(client, checker, args.java_base, args.python_base)
            check_query(client, checker, args.java_base, args.python_base)
            check_request_id(client, checker, args.java_base, args.python_log)
            check_stream(client, checker, args.java_base, args.stream_delay_ms)
            check_progress(
                client,
                checker,
                args.java_base,
                args.python_base,
                args.progress_file,
                args.python_log,
            )
            check_invalid_input(client, checker, args.java_base)
        elif args.phase == "fault-provider":
            check_fault(client, checker, args.java_base, "provider_error")
        elif args.phase == "fault-timeout":
            check_fault(client, checker, args.java_base, "timeout")
        else:
            check_offline(client, checker, args.java_base, args.progress_file)

    print(f"\n=== 汇总：{checker.passed} 项通过，{checker.failed} 项失败 ===")
    return 1 if checker.failed else 0


if __name__ == "__main__":
    sys.exit(main())
