#!/usr/bin/env bash
# 账户管理：发放 / 停用 / 列出。唯一入口——账户由开发者发放、不开放注册，
# 且明确不做管理后台 UI。
#
#   OMNIREAD_ADMIN_PASSWORD=... bash scripts/account.sh create <账户名>
#   bash scripts/account.sh disable <账户名>
#   bash scripts/account.sh list
#
# 口令**只从环境变量读**，没有对应的命令行参数：argv 会进 shell 历史、会出现在进程列表里，
# 在同一个终端里按一次上箭头就能原样捞回来。正式环境按红线走 keymgr 注入：
#
#   keymgr run <profile> -- bash scripts/account.sh create <账户名>
#
# 工作目录与 dev-up.sh 一致（都是仓库根），所以 `var/omniread.db` 指向同一个文件；
# 命令自己会把「动的是哪个库」打在输出里。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$ROOT/services/backend/target/omniread-backend-0.1.0-SNAPSHOT.jar"

usage() {
  cat <<'USAGE'
用法：
  OMNIREAD_ADMIN_PASSWORD=... bash scripts/account.sh create <账户名>
  bash scripts/account.sh disable <账户名>
  bash scripts/account.sh list
USAGE
}

action="${1:-}"
username=""
case "$action" in
  # `--help` 是正常输出（stdout、退出码 0），与「参数给错了」（stderr、退出码 2）分开
  -h|--help) usage; exit 0 ;;
  create|disable)
    username="${2:-}"
    if [ -z "$username" ]; then
      echo "缺少账户名。" >&2
      usage >&2
      exit 2
    fi
    ;;
  list) ;;
  *)
    usage >&2
    exit 2
    ;;
esac

if [ ! -f "$JAR" ]; then
  echo "找不到 $JAR" >&2
  echo "先构建：mvn -f services/backend/pom.xml -DskipTests package" >&2
  exit 2
fi

cd "$ROOT"
# web-application-type=none：这是命令行工具，不该顺手起一个 Tomcat 占住 8080。
args=(--spring.main.web-application-type=none --spring.main.banner-mode=off
      --omniread.admin.command="$action")
if [ -n "$username" ]; then
  args+=(--omniread.admin.username="$username")
fi
exec java -jar "$JAR" "${args[@]}"
