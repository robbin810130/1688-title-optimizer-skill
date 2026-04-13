#!/bin/bash
# =============================================================================
# 1688 批量开启官方定制项（BrowserWing Bash 入口）
# 说明：此脚本作为 macOS / Linux 入口，内部调用同目录 Python 主实现，
#      以避免 Bash / Python 两套流程漂移。浏览器自动化仍全部通过
#      BrowserWing REST API 执行。
# 用法：
#   chmod +x batch_official_customize_enable.sh && ./batch_official_customize_enable.sh
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/batch_official_customize_enable.py"

if [[ ! -f "$PY_SCRIPT" ]]; then
    echo "❌ Python 主脚本不存在：${PY_SCRIPT}"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ 未找到 python3，无法启动 BrowserWing Python 主实现"
    exit 1
fi

echo ""
echo "══════════════════════════════════════════════════"
echo "  1688 批量开启官方定制项（BrowserWing Bash 入口）"
echo "══════════════════════════════════════════════════"
echo "  Python 主实现：${PY_SCRIPT}"
echo "  BW_PORT=${BW_PORT:-8080}"
echo "  ACTION_DELAY=${ACTION_DELAY:-2}"
echo "  PAGE_LOAD_WAIT=${PAGE_LOAD_WAIT:-8}"
echo "  MAX_ROUNDS=${MAX_ROUNDS:-200}"
echo "  MAX_CONSECUTIVE_ERRORS=${MAX_CONSECUTIVE_ERRORS:-5}"
echo "══════════════════════════════════════════════════"
echo ""

exec python3 "$PY_SCRIPT" "$@"
