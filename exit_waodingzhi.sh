#!/bin/bash
# =============================================================================
# 1688 批量退出哇噢定制脚本（BrowserWing REST API 版）
# 功能：直接导航到 sale.1688.com 已加入商品列表，逐个：
#       React Fiber hover 问号图标 → 点击退出 → 确认退出
# 用法：
#   chmod +x exit_waodingzhi.sh && ./exit_waodingzhi.sh
# 前置：BrowserWing 服务已启动（browserwing --port 8080）
# =============================================================================

set -uo pipefail

# ── 配置 ─────────────────────────────────────────────────────────────────────
BW_PORT="${BW_PORT:-8080}"
BW_BASE="http://localhost:${BW_PORT}/api/v1/executor"
LOG_DIR="$(cd "$(dirname "$0")" && pwd)/logs"
SCREENSHOT_DIR="$(cd "$(dirname "$0")" && pwd)/screenshots/exit_waodingzhi"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/exit_waodingzhi_${TIMESTAMP}.log"

# 1688 哇噢定制页面（直接导航，绕过 iframe）
TARGET_URL="https://sale.1688.com/factory/ossdql9d.html"

# 操作参数
ACTION_DELAY=2          # 每次退出后等待（秒）
HOVER_WAIT=1            # hover 后等待弹出菜单（秒）
CONFIRM_WAIT=1          # 点击退出后等待确认弹窗（秒）
REFRESH_WAIT=3          # 退出后等待列表刷新（秒）
PAGE_LOAD_WAIT=8        # 页面加载等待（秒）
MAX_EXIT_COUNT=500      # 最大退出数量限制
MAX_CONSECUTIVE_ERRORS=5  # 连续错误上限

# 统计
EXIT_COUNT=0
ERROR_COUNT=0

# ── 工具函数 ──────────────────────────────────────────────────────────────────

log() {
    local level="$1"; shift
    local msg="$*"
    local ts
    ts=$(date '+%H:%M:%S')
    local color=""
    case "$level" in
        INFO)  color="\033[0;34m" ;;
        OK)    color="\033[0;32m" ;;
        WARN)  color="\033[0;33m" ;;
        ERROR) color="\033[0;31m" ;;
        *)     color="\033[0m" ;;
    esac
    echo -e "${color}[${ts}] [${level}] ${msg}\033[0m"
    echo "[${ts}] [${level}] ${msg}" >> "$LOG_FILE"
}

bw_evaluate() {
    local script="$1"
    curl -s -X POST "${BW_BASE}/evaluate" \
        -H 'Content-Type: application/json' \
        -d "{\"script\": \"${script}\"}"
}

bw_navigate() {
    local url="$1"
    curl -s -X POST "${BW_BASE}/navigate" \
        -H 'Content-Type: application/json' \
        -d "{\"url\": \"${url}\", \"wait_until\": \"load\", \"timeout\": 30}"
}

bw_screenshot() {
    local path="$1"
    curl -s -X POST "${BW_BASE}/screenshot" \
        -H 'Content-Type: application/json' \
        -d "{\"path\": \"${path}\"}"
}

# 解析 evaluate 返回值中的 result 字段
parse_result() {
    python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result',''))" 2>/dev/null
}

# ── 验证码检测 ───────────────────────────────────────────────────────────────

check_captcha() {
    local result
    result=$(bw_evaluate '() => { var sels = [".nc_wrapper","#nc_1__wrapper","[id*=nocaptcha]","[class*=nocaptcha]","[class*=slider-captcha]","[class*=captcha]","[class*=verify]","[class*=slider-track]","[class*=aliyun-captcha]",".no-captcha","#nc_1_wrapper","[class*=risk]","[class*=security-check]"]; var found = []; sels.forEach(function(sel) { try { document.querySelectorAll(sel).forEach(function(el) { if (el.offsetParent !== null) found.push(sel); }); } catch(e) {} }); return found.length > 0 ? "CAPTCHA:" + found.join(",") : "CLEAN"; }')
    echo "$result" | parse_result
}

wait_for_captcha_clear() {
    log WARN "⚠️  检测到验证码！请在 BrowserWing 浏览器窗口中手动完成验证..."
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  🛡️  验证码已触发，请在浏览器窗口中手动处理"
    echo "  处理完成后按 [Enter] 继续..."
    echo "═══════════════════════════════════════════════════"
    read -r
    local status
    status=$(check_captcha)
    if [[ "$status" == "CLEAN" ]]; then
        log OK "✅ 验证码已清除，继续执行"
    else
        log WARN "仍然检测到验证码元素：${status}，继续尝试..."
    fi
}

# ── 核心操作函数 ─────────────────────────────────────────────────────────────

# 检查列表是否为空
check_list_empty() {
    local result
    result=$(bw_evaluate '() => { var rows = document.querySelectorAll("tbody tr"); if (rows.length === 0) return "EMPTY"; var firstText = rows[0].innerText; if (firstText.indexOf("暂无") >= 0 || firstText.indexOf("没有") >= 0) return "EMPTY"; return "HAS_ITEMS:" + rows.length; }')
    echo "$result" | parse_result
}

# React Fiber hover 第一行的问号图标
hover_first_icon() {
    local result
    result=$(bw_evaluate '() => { var imgs = document.querySelectorAll("img[style*=\"cursor\"]"); var target = null; for (var i = 0; i < imgs.length; i++) { var r = imgs[i].getBoundingClientRect(); if (r.top > 300 && r.left > 1500) { target = imgs[i]; break; } } if (!target) return "ICON_NOT_FOUND"; var fiberKey = Object.keys(target).find(function(k) { return k.indexOf("__reactFiber$") === 0; }); if (!fiberKey) return "NO_FIBER"; var fiber = target[fiberKey]; var el = fiber; var depth = 0; while (el && depth < 10) { var p = el.memoizedProps || el.pendingProps || {}; if (p.onMouseEnter) { p.onMouseEnter({ currentTarget: target, target: target, type: "mouseenter", clientX: target.getBoundingClientRect().left + 8, clientY: target.getBoundingClientRect().top + 8 }); return "HOVER_OK:depth=" + depth; } el = el.return; depth++; } return "NO_ONMOUSEENTER"; }')
    echo "$result" | parse_result
}

# 点击"退出哇噢定制"按钮
click_exit_button() {
    local result
    result=$(bw_evaluate '() => { var btns = document.querySelectorAll(".my-ant-btn.my-ant-btn-primary"); for (var i = 0; i < btns.length; i++) { if (btns[i].offsetParent !== null && btns[i].innerText.indexOf("退出") >= 0) { btns[i].click(); return "EXIT_CLICKED"; } } return "EXIT_BTN_NOT_FOUND"; }')
    echo "$result" | parse_result
}

# 点击确认弹窗的"确定"按钮
click_confirm_button() {
    local result
    result=$(bw_evaluate '() => { var dialog = document.querySelector(".next-dialog"); if (!dialog) return "NO_DIALOG"; var btn = dialog.querySelector(".next-btn-primary"); if (!btn) return "NO_CONFIRM_BTN"; btn.click(); return "CONFIRMED"; }')
    echo "$result" | parse_result
}

# 关闭可能残留的弹出菜单（点击页面空白区域）
dismiss_popover() {
    bw_evaluate '() => { var balloon = document.querySelector(".next-balloon"); if (balloon) { balloon.style.display = "none"; } var dialog = document.querySelector(".next-dialog"); if (dialog) { dialog.style.display = "none"; } return "dismissed"; }' > /dev/null
}

# ── 主流程 ───────────────────────────────────────────────────────────────────

main() {
    # 初始化目录
    mkdir -p "$LOG_DIR" "$SCREENSHOT_DIR"

    echo ""
    echo "══════════════════════════════════════════════════"
    echo "  🚀 1688 批量退出哇噢定制（BrowserWing 版）"
    echo "══════════════════════════════════════════════════"
    echo "  目标页面：${TARGET_URL}"
    echo "  最大退出：${MAX_EXIT_COUNT} 件"
    echo "  操作间隔：${ACTION_DELAY} 秒"
    echo "══════════════════════════════════════════════════"
    echo ""

    # 1. 检查 BrowserWing 连通性
    local health
    health=$(curl -s --connect-timeout 5 "http://localhost:${BW_PORT}/api/v1/executor/help" | head -1)
    if [[ -z "$health" ]]; then
        log ERROR "❌ BrowserWing 未在端口 ${BW_PORT} 运行，请先启动："
        log ERROR "   cd /tmp && browserwing --port ${BW_PORT}"
        exit 1
    fi
    log OK "✅ BrowserWing 连通（端口 ${BW_PORT}）"

    # 2. 导航到哇噢定制页面
    log INFO "导航到哇噢定制页面..."
    bw_navigate "$TARGET_URL" > /dev/null
    sleep $PAGE_LOAD_WAIT

    # 3. 检查登录状态
    local page_text
    page_text=$(bw_evaluate '() => { return document.body ? document.body.innerText.substring(0, 200) : "NO_BODY"; }' | parse_result)
    if [[ "$page_text" == *"登录"* || "$page_text" == *"请登录"* || "$page_text" == "NO_BODY" ]]; then
        log ERROR "❌ 未登录 1688！请先在 BrowserWing 浏览器中登录。"
        echo ""
        echo "═══════════════════════════════════════════════════"
        echo "  🔐 请在 BrowserWing 控制的浏览器中登录 1688"
        echo "  登录完成后按 [Enter] 继续..."
        echo "═══════════════════════════════════════════════════"
        read -r
    fi

    # 4. 验证码检测
    local captcha
    captcha=$(check_captcha)
    if [[ "$captcha" != "CLEAN" ]]; then
        wait_for_captcha_clear
    fi

    # 5. 检查列表状态
    local list_status
    list_status=$(check_list_empty)
    if [[ "$list_status" == "EMPTY" ]]; then
        log OK "🎉 列表为空，没有需要退出的商品！"
        exit 0
    fi
    log OK "✅ 检测到商品：${list_status}"

    # 6. 截图记录初始状态
    bw_screenshot "${SCREENSHOT_DIR}/before_exit.png" > /dev/null

    # 7. 开始批量退出循环
    echo ""
    log INFO "══════════════════════════════════════════════════"
    log INFO "  🔄 开始批量退出..."
    log INFO "══════════════════════════════════════════════════"
    echo ""

    while (( EXIT_COUNT < MAX_EXIT_COUNT )); do
        # 检查列表状态
        list_status=$(check_list_empty)
        if [[ "$list_status" == "EMPTY" ]]; then
            break
        fi

        # 当前剩余商品数
        local remaining
        remaining=$(echo "$list_status" | sed 's/HAS_ITEMS://')
        EXIT_COUNT=$((EXIT_COUNT + 1))

        echo ""
        log INFO "────────────────────────────────────────"
        log INFO "📦 第 ${EXIT_COUNT} 件（剩余 ${remaining:-?} 件）"

        # Step A: Hover 问号图标
        log INFO "  [a] 悬停问号图标..."
        local hover_result
        hover_result=$(hover_first_icon)
        if [[ "$hover_result" != HOVER_OK* ]]; then
            log ERROR "  ❌ 悬停失败：${hover_result}"
            ERROR_COUNT=$((ERROR_COUNT + 1))
            if (( ERROR_COUNT >= MAX_CONSECUTIVE_ERRORS )); then
                log ERROR "  ❌ 连续 ${MAX_CONSECUTIVE_ERRORS} 次错误，终止操作"
                break
            fi
            sleep $ACTION_DELAY
            continue
        fi
        log OK "  ✅ 悬停成功（${hover_result}）"
        sleep $HOVER_WAIT

        # Step B: 点击"退出哇噢定制"按钮
        log INFO "  [b] 点击退出按钮..."
        local exit_result
        exit_result=$(click_exit_button)
        if [[ "$exit_result" != "EXIT_CLICKED" ]]; then
            log ERROR "  ❌ 退出按钮未找到：${exit_result}"
            dismiss_popover
            ERROR_COUNT=$((ERROR_COUNT + 1))
            if (( ERROR_COUNT >= MAX_CONSECUTIVE_ERRORS )); then
                log ERROR "  ❌ 连续 ${MAX_CONSECUTIVE_ERRORS} 次错误，终止操作"
                break
            fi
            sleep $ACTION_DELAY
            continue
        fi
        log OK "  ✅ 已点击退出按钮"
        sleep $CONFIRM_WAIT

        # Step C: 点击确认弹窗的"确定"
        log INFO "  [c] 确认退出..."
        local confirm_result
        confirm_result=$(click_confirm_button)
        if [[ "$confirm_result" != "CONFIRMED" ]]; then
            log WARN "  ⚠️ 确认弹窗操作异常：${confirm_result}"
            # 可能弹窗还没出来，再等一下重试
            sleep 2
            confirm_result=$(click_confirm_button)
            if [[ "$confirm_result" != "CONFIRMED" ]]; then
                log ERROR "  ❌ 确认失败：${confirm_result}"
                ERROR_COUNT=$((ERROR_COUNT + 1))
                if (( ERROR_COUNT >= MAX_CONSECUTIVE_ERRORS )); then
                    log ERROR "  ❌ 连续 ${MAX_CONSECUTIVE_ERRORS} 次错误，终止操作"
                    break
                fi
                dismiss_popover
                sleep $ACTION_DELAY
                continue
            fi
        fi
        log OK "  ✅ 已确认退出第 ${EXIT_COUNT} 件商品"
        ERROR_COUNT=0  # 重置连续错误计数

        # 等待列表刷新
        log INFO "  [d] 等待列表刷新..."
        sleep $REFRESH_WAIT

        # 验证码检测
        captcha=$(check_captcha)
        if [[ "$captcha" != "CLEAN" ]]; then
            wait_for_captcha_clear
        fi

        # 操作间隔
        sleep $ACTION_DELAY
    done

    # 8. 最终结果
    echo ""
    log INFO "══════════════════════════════════════════════════"
    log INFO "  📊 批量退出完成！"
    log INFO "══════════════════════════════════════════════════"
    log OK "  ✅ 成功退出：${EXIT_COUNT} 件商品"
    log ERROR "  ❌ 错误次数：${ERROR_COUNT}"
    log INFO "══════════════════════════════════════════════════"

    # 最终截图
    bw_screenshot "${SCREENSHOT_DIR}/after_exit.png" > /dev/null
    log INFO "  截图目录：${SCREENSHOT_DIR}/"
    log INFO "  日志文件：${LOG_FILE}"
    echo ""

    # 最终确认列表状态
    list_status=$(check_list_empty)
    if [[ "$list_status" == "EMPTY" ]]; then
        log OK "🎉 所有商品已退出哇噢定制！"
    else
        log WARN "列表仍有商品：${list_status}"
        log WARN "如需继续退出，可再次运行本脚本"
    fi
    echo ""
}

main "$@"
