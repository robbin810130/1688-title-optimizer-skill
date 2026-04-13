#!/bin/bash
# =============================================================================
# 1688 批量同步「服务与承诺 → 发货服务」脚本
# 功能：遍历商品管理列表所有商品（含翻页），逐个检查发货服务表格，
#       将不符合目标值的商品修改为目标值并保存提交。
# 用法：
#   1. 编辑 shipping_target_config.json 设置目标发货时间和数量区间
#   2. chmod +x batch_shipping_sync.sh && ./batch_shipping_sync.sh
# =============================================================================

set -uo pipefail

# ── 配置 ─────────────────────────────────────────────────────────────────────
BW_PORT="${BW_PORT:-8080}"
BW_BASE="http://localhost:${BW_PORT}/api/v1/executor"
CONFIG_FILE="$(cd "$(dirname "$0")" && pwd)/shipping_target_config.json"
LOG_DIR="$(cd "$(dirname "$0")" && pwd)/logs"
SCREENSHOT_DIR="$(cd "$(dirname "$0")" && pwd)/screenshots/batch_shipping"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/batch_shipping_${TIMESTAMP}.log"

# 1688 URL
LIST_URL="https://offer.1688.com/offer/manage.htm?show_type=valid"

# 统计计数
TOTAL=0
MODIFIED=0
SKIPPED=0
FAILED=0
CURRENT_PAGE=1

# ── 从配置文件读取目标值 ────────────────────────────────────────────────────

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "❌ 配置文件不存在：${CONFIG_FILE}"
    echo "   请创建 shipping_target_config.json 并填写目标值"
    exit 1
fi

read_config() {
    local key="$1"
    python3 -c "import sys,json; d=json.load(open('${CONFIG_FILE}')); print(d${key})" 2>/dev/null
}

ROW1_MIN=$(read_config "['target']['row1']['min_qty']")
ROW1_MAX=$(read_config "['target']['row1']['max_qty']")
ROW1_SHIP=$(read_config "['target']['row1']['ship_time']")
ROW2_MIN=$(read_config "['target']['row2']['min_qty']")
ROW2_MAX=$(read_config "['target']['row2']['max_qty']")
ROW2_SHIP=$(read_config "['target']['row2']['ship_time']")

# 校验必填字段
if [[ -z "$ROW1_SHIP" || -z "$ROW2_SHIP" ]]; then
    echo "❌ 配置文件缺少必填字段：row1.ship_time 或 row2.ship_time"
    exit 1
fi

log_config() {
    echo ""
    echo "══════════════════════════════════════════════════"
    echo "  📋 当前发货服务目标配置"
    echo "     配置文件：${CONFIG_FILE}"
    echo "──────────────────────────────────────────────────"
    echo "  第1行：${ROW1_MIN}~${ROW1_MAX}件 → ${ROW1_SHIP}"
    echo "  第2行：${ROW2_MIN}件+ → ${ROW2_SHIP}"
    echo "══════════════════════════════════════════════════"
}

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

# JS 字符串安全转义（用于嵌在 JSON 中）
js_escape() {
    echo "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\n/\\n/g'
}

# ── 验证码检测 ───────────────────────────────────────────────────────────────

check_captcha() {
    local result
    result=$(bw_evaluate '() => { const sels = [".nc_wrapper","#nc_1__wrapper","[id*=nocaptcha]","[class*=nocaptcha]","[class*=slider-captcha]","[class*=captcha]","[class*=verify]","[class*=slider-track]","[class*=aliyun-captcha]",".no-captcha","#nc_1_wrapper","[class*=risk]","[class*=security-check]"]; let found = []; sels.forEach(sel => { try { document.querySelectorAll(sel).forEach(el => { if (el.offsetParent !== null) found.push(sel); }); } catch(e) {} }); return found.length > 0 ? "CAPTCHA:" + found.join(",") : "CLEAN"; }')
    echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','CLEAN'))" 2>/dev/null
}

wait_for_captcha_clear() {
    log WARN "⚠️  检测到验证码！请在 BrowserWing 浏览器窗口中手动完成验证..."
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  🛡️  验证码已触发，请在浏览器窗口中手动处理"
    echo "  处理完成后按 [Enter] 继续..."
    echo "═══════════════════════════════════════════════════"
    read -r
    # 二次确认
    local status
    status=$(check_captcha)
    if [[ "$status" == "CLEAN" ]]; then
        log OK "✅ 验证码已清除，继续执行"
    else
        log WARN "仍然检测到验证码元素：${status}，继续尝试..."
    fi
}

# ── 商品列表提取 ─────────────────────────────────────────────────────────────

extract_page_products() {
    bw_evaluate '() => { const items = []; document.querySelectorAll("a").forEach(a => { if (a.innerText.trim() === "修改详情" && a.href.includes("offerId=")) { const m = a.href.match(/offerId=(\d+)/); if (m) items.push(m[1]); } }); return JSON.stringify(items); }' \
        | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('data',{}).get('result','[]')))" 2>/dev/null
}

# ── 翻页 ─────────────────────────────────────────────────────────────────────

has_next_page() {
    local result
    result=$(bw_evaluate '() => { const nextBtn = document.querySelector("button.next-pagination-item.next"); if (!nextBtn) return "NO_NEXT"; return nextBtn.disabled ? "NO_NEXT" : "HAS_NEXT"; }' \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','NO_NEXT'))" 2>/dev/null)
    echo "$result"
}

click_next_page() {
    bw_evaluate '() => { const nextBtn = document.querySelector("button.next-pagination-item.next"); if (nextBtn && !nextBtn.disabled) { nextBtn.click(); return "CLICKED"; } return "NO_NEXT"; }' \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','FAILED'))" 2>/dev/null
}

get_page_info() {
    local result
    result=$(bw_evaluate '() => { const display = document.querySelector(".next-pagination-display"); return display ? display.innerText.trim() : "unknown"; }' \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','unknown'))" 2>/dev/null)
    echo "$result"
}

# ── 编辑页操作 ───────────────────────────────────────────────────────────────

scroll_to_shipping_section() {
    # 方式1：点击左侧导航"服务与承诺"
    bw_evaluate '() => { const links = document.querySelectorAll("a,span,div"); for (const el of links) { if (el.innerText.trim() === "服务与承诺" && el.offsetParent !== null) { el.scrollIntoView({behavior:"auto",block:"center"}); el.click(); return "clicked_nav"; } } return "nav_not_found"; }' > /dev/null
    sleep 1
    # 方式2：直接滚动到发货服务表格
    bw_evaluate '() => { const tables = document.querySelectorAll("table"); for (const t of tables) { if (t.innerText.includes("发货时间") && t.innerText.includes("购买数量")) { t.scrollIntoView({behavior:"auto",block:"center"}); return "scrolled"; } } return "table_not_found"; }' > /dev/null
    sleep 1
}

extract_shipping_values() {
    # 提取发货服务表格当前值
    # 返回 JSON: {"row0_select": "48小时发货", "row1_select": "72小时发货", "row0_inputs": [...], "row1_inputs": [...]}
    bw_evaluate '() => { const tables = document.querySelectorAll("table"); let st = null; for (const t of tables) { if (t.innerText.includes("发货时间") && t.innerText.includes("购买数量")) { st = t; break; } } if (!st) return JSON.stringify({error: "table_not_found"}); const rows = st.querySelectorAll("tbody tr"); const r = {row0: {}, row1: {}}; if (rows[0]) { const s = rows[0].querySelector(".ant-select"); r.row0.select = s ? s.innerText.trim().split("\\n")[0] : ""; const inps = rows[0].querySelectorAll("input.ant-input-number-input"); r.row0.inputs = Array.from(inps).map(i => ({value: i.value, disabled: i.disabled})); } if (rows[1]) { const s = rows[1].querySelector(".ant-select"); r.row1.select = s ? s.innerText.trim().split("\\n")[0] : ""; const inps = rows[1].querySelectorAll("input.ant-input-number-input"); r.row1.inputs = Array.from(inps).map(i => ({value: i.value, disabled: i.disabled})); } return JSON.stringify(r); }' \
        | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('data',{}).get('result','{}')))" 2>/dev/null
}

needs_modification() {
    local values_json="$1"
    local row0_ship row1_ship row0_min row0_max row1_min

    row0_ship=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('select',''))" 2>/dev/null)
    row1_ship=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row1',{}).get('select',''))" 2>/dev/null)
    row0_min=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('inputs',[{},{}])[0].get('value',''))" 2>/dev/null)
    row0_max=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('inputs',[{},{}])[1].get('value',''))" 2>/dev/null)
    row1_min=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row1',{}).get('inputs',[{},{}])[0].get('value',''))" 2>/dev/null)

    log INFO "当前值 → 第1行: ${row0_min}~${row0_max}件 ${row0_ship} | 第2行: ${row1_min}件+ ${row1_ship}"

    if [[ "$row0_ship" == "$ROW1_SHIP" && "$row1_ship" == "$ROW2_SHIP" \
          && "$row0_min" == "$ROW1_MIN" && "$row0_max" == "$ROW1_MAX" \
          && "$row1_min" == "$ROW2_MIN" ]]; then
        echo "SKIP"
    else
        echo "MODIFY"
    fi
}

modify_shipping() {
    local target_ship="$1"  # 需要修改的行: "row1" 或 "row2"
    local target_value="$2" # 目标值: "7天发货" 等
    local row_index
    case "$target_ship" in
        row1) row_index=0 ;;
        row2) row_index=1 ;;
        *)    row_index=1 ;;
    esac

    # 第一步：用 BrowserWing click API 打开 Ant Design 下拉框
    # 关键：必须设置 wait_visible=false，因为 select 元素可能在滚动区域内不可见
    local css_selector="table tbody tr:nth-child($((row_index + 1))) .ant-select"
    curl -s -X POST "${BW_BASE}/click" \
        -H 'Content-Type: application/json' \
        -d "{\"identifier\": \"${css_selector}\", \"wait_visible\": false, \"timeout\": 5}" > /dev/null

    sleep 2

    # 第二步：检查下拉框是否打开
    local dropdown_check
    dropdown_check=$(bw_evaluate '() => { const opts = document.querySelectorAll(".ant-select-item-option"); if (opts.length === 0) return "NO_OPTIONS"; return "HAS_OPTIONS:" + opts.length; }' \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','NO_OPTIONS'))" 2>/dev/null)

    if [[ "$dropdown_check" == "NO_OPTIONS" ]]; then
        log ERROR "  ❌ 下拉框未打开"
        return 1
    fi

    log INFO "  下拉框已打开（${dropdown_check}）"

    # 第三步：用 JS evaluate 在下拉选项中点击目标值
    local target_esc
    target_esc=$(js_escape "$target_value")
    local select_result
    select_result=$(bw_evaluate "() => { const opts = document.querySelectorAll('.ant-select-item-option'); for (const opt of opts) { const content = opt.querySelector('.ant-select-item-option-content'); if (content && content.innerText.trim() === '${target_esc}') { opt.click(); return 'selected'; } } return 'NOT_FOUND'; }" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','FAILED'))" 2>/dev/null)

    sleep 1.5
    if [[ "$select_result" == "selected" ]]; then
        log OK "  ✅ 已选择「${target_value}」"
        return 0
    else
        log ERROR "  ❌ 选择「${target_value}」失败：${select_result}"
        return 1
    fi
}

submit_changes() {
    # 滚动到底部
    bw_evaluate '() => { window.scrollTo(0, document.body.scrollHeight); return "scrolled"; }' > /dev/null
    sleep 2

    # 检查提交按钮
    local btn_check
    btn_check=$(bw_evaluate '() => { const btn = document.querySelector("button.submit-buttom-action"); if (!btn) return "BTN_NOT_FOUND"; if (btn.disabled) return "BTN_DISABLED"; return "BTN_READY"; }' \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','BTN_NOT_FOUND'))" 2>/dev/null)

    if [[ "$btn_check" == "BTN_NOT_FOUND" ]]; then
        log ERROR "  ❌ 找不到提交按钮"
        return 1
    fi

    if [[ "$btn_check" == "BTN_DISABLED" ]]; then
        log WARN "  ⚠️  提交按钮已禁用，可能没有可提交的修改"
        return 1
    fi

    # 点击提交
    bw_evaluate '() => { const btn = document.querySelector("button.submit-buttom-action"); btn.click(); return "submitted"; }' > /dev/null
    sleep 4

    # 检查提交结果
    local result_text
    result_text=$(bw_evaluate '() => { return document.title; }' \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result',''))" 2>/dev/null)

    if [[ "$result_text" == *"成功"* || "$result_text" == *"提交"* ]]; then
        log OK "  ✅ 提交成功"
        return 0
    else
        log WARN "  ⚠️  提交结果待确认（标题：${result_text}）"
        return 0
    fi
}

# ── 单商品处理 ───────────────────────────────────────────────────────────────

process_product() {
    local offer_id="$1"
    local edit_url="https://offer-new.1688.com/popular/publish.htm?id=${offer_id}&operator=edit"

    log INFO "处理商品 ${offer_id}..."

    # 1. 导航到编辑页
    bw_navigate "$edit_url" > /dev/null
    sleep 6

    # 2. 验证码检测
    local captcha
    captcha=$(check_captcha)
    if [[ "$captcha" != "CLEAN" ]]; then
        wait_for_captcha_clear
    fi

    # 3. 滚动到发货服务区域
    scroll_to_shipping_section
    sleep 1

    # 4. 提取当前值
    local values
    values=$(extract_shipping_values)
    if [[ -z "$values" || "$values" == *"error"* || "$values" == *"not_found"* ]]; then
        log ERROR "  ❌ 无法提取发货服务值，跳过"
        FAILED=$((FAILED + 1))
        return
    fi

    # 5. 判断是否需要修改
    local action
    action=$(needs_modification "$values")

    if [[ "$action" == "SKIP" ]]; then
        log OK "  ⏭️  已匹配目标值，跳过"
        SKIPPED=$((SKIPPED + 1))
        # 截图
        bw_screenshot "${SCREENSHOT_DIR}/${offer_id}_skip.png" > /dev/null
        return
    fi

    # 6. 需要修改 — 先截图修改前
    bw_screenshot "${SCREENSHOT_DIR}/${offer_id}_before.png" > /dev/null

    # 7. 修改发货服务
    local modify_failed=0

    # 检查第1行是否需要修改
    local row0_ship
    row0_ship=$(echo "$values" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('select',''))" 2>/dev/null)
    if [[ "$row0_ship" != "$ROW1_SHIP" ]]; then
        log INFO "  修改第1行发货时间：${row0_ship} → ${ROW1_SHIP}"
        modify_shipping "row1" "$ROW1_SHIP" || modify_failed=1
        sleep 1
    fi

    # 检查第2行是否需要修改
    local row1_ship
    row1_ship=$(echo "$values" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row1',{}).get('select',''))" 2>/dev/null)
    if [[ "$row1_ship" != "$ROW2_SHIP" ]]; then
        log INFO "  修改第2行发货时间：${row1_ship} → ${ROW2_SHIP}"
        modify_shipping "row2" "$ROW2_SHIP" || modify_failed=1
        sleep 1
    fi

    if [[ $modify_failed -eq 1 ]]; then
        log ERROR "  ❌ 修改失败"
        bw_screenshot "${SCREENSHOT_DIR}/${offer_id}_error.png" > /dev/null
        FAILED=$((FAILED + 1))
        return
    fi

    # 8. 提交保存
    log INFO "  提交修改..."
    submit_changes
    bw_screenshot "${SCREENSHOT_DIR}/${offer_id}_after.png" > /dev/null
    MODIFIED=$((MODIFIED + 1))
    log OK "  ✅ 商品 ${offer_id} 修改完成"
}

# ── 主流程 ───────────────────────────────────────────────────────────────────

main() {
    # 初始化目录
    mkdir -p "$LOG_DIR" "$SCREENSHOT_DIR"

    # 显示配置信息
    log_config

    log INFO "══════════════════════════════════════════════════"
    log INFO "  1688 批量同步「发货服务」"
    log INFO "  第1行：${ROW1_MIN}~${ROW1_MAX}件 → ${ROW1_SHIP}"
    log INFO "  第2行：${ROW2_MIN}件+ → ${ROW2_SHIP}"
    log INFO "══════════════════════════════════════════════════"
    echo ""

    # 检查 BrowserWing 连通性
    local health
    health=$(curl -s --connect-timeout 5 "http://localhost:${BW_PORT}/api/v1/executor/help" | head -1)
    if [[ -z "$health" ]]; then
        log ERROR "❌ BrowserWing 未在端口 ${BW_PORT} 运行，请先启动："
        log ERROR "   browserwing --port ${BW_PORT}"
        exit 1
    fi
    log OK "✅ BrowserWing 连通（端口 ${BW_PORT}）"

    # 导航到商品列表
    log INFO "导航到商品管理列表..."
    bw_navigate "$LIST_URL" > /dev/null
    sleep 4

    # 验证码检测
    local captcha
    captcha=$(check_captcha)
    if [[ "$captcha" != "CLEAN" ]]; then
        wait_for_captcha_clear
    fi

    # 登录状态检查
    local page_text
    page_text=$(bw_evaluate '() => { return document.body.innerText.substring(0, 200); }' \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result',''))" 2>/dev/null)
    if [[ "$page_text" == *"登录"* || "$page_text" == *"请登录"* ]]; then
        log ERROR "❌ 未登录 1688！请先在 BrowserWing 浏览器中登录。"
        echo ""
        echo "═══════════════════════════════════════════════════"
        echo "  🔐 请在 BrowserWing 控制的浏览器中登录 1688"
        echo "  登录完成后按 [Enter] 继续..."
        echo "═══════════════════════════════════════════════════"
        read -r
    fi

    # 主循环：逐页遍历
    while true; do
        local page_display
        page_display=$(get_page_info)
        log INFO "────────────────────────────────────────"
        log INFO "📄 当前页：${page_display}"

        # 提取当前页商品
        local products_json
        products_json=$(extract_page_products)
        local product_count
        product_count=$(echo "$products_json" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)

        if [[ -z "$product_count" || "$product_count" == "0" ]]; then
            log WARN "当前页未提取到商品，尝试等待..."
            sleep 3
            products_json=$(extract_page_products)
            product_count=$(echo "$products_json" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
            if [[ -z "$product_count" || "$product_count" == "0" ]]; then
                log ERROR "仍然无法提取商品，跳过此页"
                break
            fi
        fi

        log INFO "📋 本页 ${product_count} 个商品"
        TOTAL=$((TOTAL + product_count))

        # 逐个处理商品（用临时文件 + 进程替换避免 subshell 变量丢失问题）
        local tmp_products
        tmp_products=$(mktemp)
        echo "$products_json" | python3 -c "import sys,json; [print(x) for x in json.load(sys.stdin)]" 2>/dev/null > "$tmp_products"

        local idx=0
        while IFS= read -r offer_id; do
            if [[ -z "$offer_id" ]]; then continue; fi
            idx=$((idx + 1))
            log INFO "[$(printf '%02d' $idx)/$product_count] 处理 ${offer_id}"

            process_product "$offer_id"

            # 验证码检测（每个商品处理后）
            captcha=$(check_captcha)
            if [[ "$captcha" != "CLEAN" ]]; then
                wait_for_captcha_clear
            fi

            # 返回列表页（如果不在列表页）
            local current_url
            current_url=$(bw_evaluate '() => return location.href;' \
                | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result',''))" 2>/dev/null)
            if [[ "$current_url" != *"/offer/manage.htm"* ]]; then
                log INFO "返回商品列表..."
                bw_navigate "$LIST_URL" > /dev/null
                sleep 4
            fi

            # 操作间隔，避免触发风控
            sleep 2
        done < "$tmp_products"
        rm -f "$tmp_products"

        # 检查是否有下一页
        local next_status
        next_status=$(has_next_page)
        if [[ "$next_status" == "NO_NEXT" ]]; then
            log OK "已到达最后一页"
            break
        fi

        # 点击下一页
        log INFO "翻到下一页..."
        click_next_page > /dev/null
        sleep 4

        # 翻页后验证码检测
        captcha=$(check_captcha)
        if [[ "$captcha" != "CLEAN" ]]; then
            wait_for_captcha_clear
        fi

        CURRENT_PAGE=$((CURRENT_PAGE + 1))
    done

    # 输出汇总
    echo ""
    log INFO "══════════════════════════════════════════════════"
    log INFO "  📊 批量同步完成！"
    log INFO "══════════════════════════════════════════════════"
    log INFO "  总商品数：${TOTAL}"
    log OK "  ✅ 已修改：${MODIFIED}"
    log INFO "  ⏭️  已跳过：${SKIPPED}"
    log ERROR "  ❌ 失败：${FAILED}"
    log INFO "══════════════════════════════════════════════════"
    log INFO "  日志文件：${LOG_FILE}"
    log INFO "  截图目录：${SCREENSHOT_DIR}/"
    echo ""
}

main "$@"
