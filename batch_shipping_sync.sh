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
NON_INTERACTIVE="${NON_INTERACTIVE:-0}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-900}"
FILTER_KEYWORD="${FILTER_KEYWORD:-}"
SKU_LIST="${SKU_LIST:-}"
SKU_FILE="${SKU_FILE:-}"
SKU_TARGETS_JSON="[]"
PROCESSED_FILE=""
LAST_HANDLED_COUNT=0

usage() {
    cat <<'EOF'
用法：
  ./batch_shipping_sync.sh --sku-list SKU0001,SKU0002
  ./batch_shipping_sync.sh --sku-file ./sku.txt
  ./batch_shipping_sync.sh --keyword 防晒
  ./batch_shipping_sync.sh --sku-list SKU0001 --keyword 防晒

说明：
  - 必须提供 --sku-list / --sku-file / --keyword 之一，不允许全量处理所有商品。
  - SKU 清单支持 SKU 或 offerId，逗号分隔或文件逐行填写。
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sku-list)
            SKU_LIST="${2:-}"
            shift 2
            ;;
        --sku-file)
            SKU_FILE="${2:-}"
            shift 2
            ;;
        --keyword)
            FILTER_KEYWORD="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1"
            usage
            exit 1
            ;;
    esac
done

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

if [[ -z "$FILTER_KEYWORD" && -z "$SKU_LIST" && -z "$SKU_FILE" ]]; then
    echo "❌ 必须提供筛选条件：--sku-list / --sku-file / --keyword（至少一个）"
    usage
    exit 1
fi

if [[ -n "$SKU_FILE" && ! -f "$SKU_FILE" ]]; then
    echo "❌ SKU 文件不存在：$SKU_FILE"
    exit 1
fi

SKU_TARGETS_JSON=$(python3 - "$SKU_LIST" "$SKU_FILE" <<'PY'
import json
import re
import sys

sku_list = sys.argv[1] if len(sys.argv) > 1 else ""
sku_file = sys.argv[2] if len(sys.argv) > 2 else ""
tokens = []
if sku_list:
    tokens.extend([x.strip() for x in sku_list.split(",") if x.strip()])
if sku_file:
    with open(sku_file, "r", encoding="utf-8-sig") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                tokens.append(s)

def norm(v: str) -> str:
    return re.sub(r"\s+", "", v or "").strip().upper()

uniq = sorted({norm(x) for x in tokens if norm(x)})
print(json.dumps(uniq, ensure_ascii=False))
PY
)

log_config() {
    echo ""
    echo "══════════════════════════════════════════════════"
    echo "  📋 当前发货服务目标配置"
    echo "     配置文件：${CONFIG_FILE}"
    echo "──────────────────────────────────────────────────"
    echo "  第1行：${ROW1_MIN}~${ROW1_MAX}件 → ${ROW1_SHIP}"
    echo "  第2行：${ROW2_MIN}件+ → ${ROW2_SHIP}"
    echo "  关键词筛选：${FILTER_KEYWORD:-<未设置>}"
    echo "  SKU清单数量：$(echo "$SKU_TARGETS_JSON" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)"
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
    local payload
    payload=$(python3 - "$script" <<'PY'
import json, sys
print(json.dumps({"script": sys.argv[1]}, ensure_ascii=False))
PY
)
    curl -s -X POST "${BW_BASE}/evaluate" \
        -H 'Content-Type: application/json' \
        -d "$payload"
}

bw_navigate() {
    local url="$1"
    local payload
    payload=$(python3 - "$url" <<'PY'
import json, sys
print(json.dumps({"url": sys.argv[1], "wait_until": "load", "timeout": 30}, ensure_ascii=False))
PY
)
    curl -s -X POST "${BW_BASE}/navigate" \
        -H 'Content-Type: application/json' \
        -d "$payload"
}

bw_screenshot() {
    local path="$1"
    local payload
    payload=$(python3 - "$path" <<'PY'
import json, sys
print(json.dumps({"path": sys.argv[1]}, ensure_ascii=False))
PY
)
    curl -s -X POST "${BW_BASE}/screenshot" \
        -H 'Content-Type: application/json' \
        -d "$payload"
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
    local start_ts now status
    start_ts=$(date +%s)
    if [[ "$NON_INTERACTIVE" != "1" && -t 0 ]]; then
        echo ""
        echo "═══════════════════════════════════════════════════"
        echo "  🛡️  验证码已触发，请在浏览器窗口中手动处理"
        echo "  处理完成后按 [Enter] 继续..."
        echo "═══════════════════════════════════════════════════"
        read -r
    else
        log WARN "当前为非交互模式：自动轮询验证码状态"
    fi
    while true; do
        status=$(check_captcha)
        if [[ "$status" == "CLEAN" ]]; then
            log OK "✅ 验证码已清除，继续执行"
            return 0
        fi
        now=$(date +%s)
        if (( now - start_ts > WAIT_TIMEOUT )); then
            log ERROR "⏱️ 验证码等待超时（${WAIT_TIMEOUT}s）：${status}"
            return 1
        fi
        sleep 5
    done
}

wait_for_login_ready() {
    log WARN "🔐 检测到未登录，请在 BrowserWing 浏览器中完成登录"
    local start_ts now page_text
    start_ts=$(date +%s)
    if [[ "$NON_INTERACTIVE" != "1" && -t 0 ]]; then
        echo ""
        echo "═══════════════════════════════════════════════════"
        echo "  🔐 请在 BrowserWing 控制的浏览器中登录 1688"
        echo "  登录完成后按 [Enter] 继续..."
        echo "═══════════════════════════════════════════════════"
        read -r
    else
        log WARN "当前为非交互模式：自动轮询登录状态"
    fi
    while true; do
        page_text=$(bw_evaluate '() => { return document.body ? document.body.innerText.substring(0, 200) : "NO_BODY"; }' \
            | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result',''))" 2>/dev/null)
        if [[ "$page_text" != *"登录"* && "$page_text" != *"请登录"* && "$page_text" != "NO_BODY" ]]; then
            log OK "✅ 登录状态已恢复"
            return 0
        fi
        now=$(date +%s)
        if (( now - start_ts > WAIT_TIMEOUT )); then
            log ERROR "⏱️ 登录等待超时（${WAIT_TIMEOUT}s）"
            return 1
        fi
        sleep 5
    done
}

# ── 商品列表提取 ─────────────────────────────────────────────────────────────

extract_page_products() {
    local keyword_override="${1:-$FILTER_KEYWORD}"
    local raw
    local keyword_esc
    keyword_esc=$(js_escape "$keyword_override")
    raw=$(bw_evaluate "() => { const targets = ${SKU_TARGETS_JSON}; const keyword = '${keyword_esc}'.trim(); const norm = (s) => (s || '').replace(/\\s+/g, '').toUpperCase(); const seen = {}; const items = []; const rows = Array.from(document.querySelectorAll('tbody tr')).filter(r => (r.innerText || '').trim() && (r.innerText || '').indexOf('暂无') < 0); rows.forEach(row => { const text = (row.innerText || '').replace(/\\s+/g, ' ').trim(); let offerId = ''; let sku = ''; const links = row.querySelectorAll('a'); for (const a of links) { const href = a.href || ''; let m = href.match(/offerId=(\\d+)/) || href.match(/[?&]id=(\\d+)/) || href.match(/offer\\/(\\d+)/); if (m && m[1]) { offerId = m[1]; break; } } const idMatch = text.match(/\\[ID\\]\\s*(\\d+)/) || text.match(/ID[：:]\\s*(\\d+)/); if (!offerId && idMatch) offerId = idMatch[1]; const skuMatch = text.match(/\\[货号\\]\\s*([^\\s]+)/) || text.match(/货号[：:]\\s*([^\\s]+)/) || text.match(/(SKU[0-9A-Za-z_-]+)/i); if (skuMatch && skuMatch[1]) sku = skuMatch[1]; const lines = (row.innerText || '').split('\\n').map(x => x.trim()).filter(Boolean); const title = lines.length ? lines[0] : text.substring(0, 80); if (!offerId) return; const offerKey = norm(offerId); const skuKey = norm(sku); if (targets.length > 0 && targets.indexOf(offerKey) < 0 && targets.indexOf(skuKey) < 0) return; if (keyword && text.indexOf(keyword) < 0 && title.indexOf(keyword) < 0 && sku.indexOf(keyword) < 0) return; if (seen[offerId]) return; seen[offerId] = true; items.push({offerId: offerId, sku: sku, title: title.substring(0, 80)}); }); return JSON.stringify(items); }")
    python3 - "$raw" <<'PY' 2>/dev/null
import json
import sys

raw = sys.argv[1] if len(sys.argv) > 1 else ""
try:
    d = json.loads(raw)
except Exception:
    print("[]")
    raise SystemExit

r = d.get("data", {}).get("result", "[]")
if isinstance(r, str):
    try:
        arr = json.loads(r)
    except Exception:
        arr = []
elif isinstance(r, list):
    arr = r
else:
    arr = []

print(json.dumps(arr, ensure_ascii=False))
PY
}

search_list_by_keyword() {
    local keyword="$1"
    local keyword_esc
    keyword_esc=$(js_escape "$keyword")
    bw_evaluate "() => { const kw='${keyword_esc}'; const input=document.querySelector('#keyword'); if(!input) return 'INPUT_NOT_FOUND'; const nativeSetter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set; nativeSetter.call(input, kw); input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); input.dispatchEvent(new Event('compositionend',{bubbles:true})); const btn=document.querySelector('button.simple-search__submit-btn'); if(btn){ btn.click(); return 'SEARCH_DONE'; } return 'BTN_NOT_FOUND'; }" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','FAILED'))" 2>/dev/null
}

build_search_terms() {
    python3 - "$FILTER_KEYWORD" "$SKU_TARGETS_JSON" <<'PY'
import json, sys
keyword = (sys.argv[1] or "").strip()
targets_json = sys.argv[2] if len(sys.argv) > 2 else "[]"
try:
    targets = json.loads(targets_json)
except Exception:
    targets = []
terms = []
if keyword:
    terms.append(keyword)
for t in targets:
    s = str(t).strip()
    if s:
        terms.append(s)
seen = set()
for t in terms:
    if t not in seen:
        seen.add(t)
        print(t)
PY
}

already_processed_offer() {
    local offer_id="$1"
    [[ -n "$PROCESSED_FILE" && -f "$PROCESSED_FILE" ]] || return 1
    grep -Fxq "$offer_id" "$PROCESSED_FILE"
}

mark_offer_processed() {
    local offer_id="$1"
    [[ -n "$PROCESSED_FILE" ]] || return 0
    echo "$offer_id" >> "$PROCESSED_FILE"
}

process_products_json() {
    local products_json="$1"
    local matched_count
    local handled_in_batch=0
    LAST_HANDLED_COUNT=0
    matched_count=$(echo "$products_json" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
    if [[ -z "$matched_count" || "$matched_count" == "0" ]]; then
        LAST_HANDLED_COUNT=0
        return 0
    fi

    log INFO "📋 本次命中 ${matched_count} 个商品"
    local tmp_products
    tmp_products=$(mktemp)
    echo "$products_json" | python3 -c "import sys,json; [print(x.get('offerId','')) for x in json.load(sys.stdin) if isinstance(x,dict)]" 2>/dev/null > "$tmp_products"

    local idx=0
    while IFS= read -r offer_id; do
        if [[ -z "$offer_id" ]]; then continue; fi
        if already_processed_offer "$offer_id"; then
            log INFO "⏭️  跳过重复商品 ${offer_id}"
            continue
        fi
        idx=$((idx + 1))
        TOTAL=$((TOTAL + 1))
        handled_in_batch=$((handled_in_batch + 1))
        log INFO "[$(printf '%02d' $idx)/$matched_count] 处理 ${offer_id}"
        process_product "$offer_id"
        mark_offer_processed "$offer_id"

        local captcha
        captcha=$(check_captcha)
        if [[ "$captcha" != "CLEAN" ]]; then
            wait_for_captcha_clear || true
        fi
        sleep 2
    done < "$tmp_products"
    rm -f "$tmp_products"
    LAST_HANDLED_COUNT=$handled_in_batch
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
    # 提取发货服务表格当前值（兼容 ant-select / next-select）
    bw_evaluate '() => { const tables = document.querySelectorAll("table"); let st = null; for (const t of tables) { const tx=(t.innerText||""); if (tx.includes("发货时间") && tx.includes("购买数量")) { st = t; break; } } if (!st) return JSON.stringify({error: "table_not_found"}); const rows = st.querySelectorAll("tbody tr"); const pickShip = (row) => { const text=(row.innerText||"").replace(/\\s+/g," "); const m=text.match(/(\\d+小时发货|\\d+天发货|当日发货|次日发货|\\d+日发货)/); if (m) return m[1]; const ant=row.querySelector(".ant-select .ant-select-selection-item, .ant-select-selector"); if (ant) return (ant.innerText||"").trim(); const nxt=row.querySelector(".next-select .next-select-inner, .next-select-value"); if (nxt) return (nxt.innerText||"").trim(); return ""; }; const pickInputs=(row)=>{ const inps=Array.from(row.querySelectorAll("input.ant-input-number-input,input")).filter(i=>{ if (!i || i.type==="hidden" || i.type==="search") return false; const cls=(i.className||""); const v=(i.value||"").trim(); const ph=(i.placeholder||"").trim(); if (cls.indexOf("ant-input-number-input")>=0) return true; return !!v || !!ph; }); return inps.map(i=>({value:(i.value||"").trim(), placeholder:(i.placeholder||"").trim(), disabled:!!i.disabled})); }; const r={row0:{select:"",inputs:[]},row1:{select:"",inputs:[]}}; if (rows[0]) { r.row0.select=pickShip(rows[0]); r.row0.inputs=pickInputs(rows[0]); } if (rows[1]) { r.row1.select=pickShip(rows[1]); r.row1.inputs=pickInputs(rows[1]); } return JSON.stringify(r); }' \
        | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('data',{}).get('result',{}); print(r if isinstance(r,str) else json.dumps(r,ensure_ascii=False))" 2>/dev/null
}

extract_shipping_ranges_by_text() {
    bw_evaluate '() => { const tables = document.querySelectorAll("table"); let st = null; for (const t of tables) { const tx=(t.innerText||""); if (tx.includes("发货时间") && tx.includes("购买数量")) { st = t; break; } } if (!st) return JSON.stringify({error: "table_not_found"}); const rows = st.querySelectorAll("tbody tr"); const parse=(txt)=>{ const t=(txt||"").replace(/\\s+/g," "); let min="",max=""; let m=t.match(/(\\d+)\\s*[~\\-]\\s*(\\d+)\\s*[件个]?/); if (m){ min=m[1]; max=m[2]; } let m2=t.match(/(\\d+)\\s*[件个]\\s*以上/); if (m2){ if(!min) min=m2[1]; } if (!m2) { const m3=t.match(/>=\\s*(\\d+)/); if (m3 && !min) min=m3[1]; } return {min:min,max:max,text:t}; }; const r0=rows[0]?parse(rows[0].innerText):{min:"",max:"",text:""}; const r1=rows[1]?parse(rows[1].innerText):{min:"",max:"",text:""}; return JSON.stringify({row0:r0,row1:r1}); }' \
        | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('data',{}).get('result',{}); print(r if isinstance(r,str) else json.dumps(r,ensure_ascii=False))" 2>/dev/null
}

needs_modification() {
    local values_json="$1"
    local row0_ship row1_ship row0_min row0_max row1_min

    row0_ship=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('select',''))" 2>/dev/null)
    row1_ship=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row1',{}).get('select',''))" 2>/dev/null)
    row0_min=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('inputs',[{},{}])[0].get('value',''))" 2>/dev/null)
    row0_max=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('inputs',[{},{}])[1].get('value',''))" 2>/dev/null)
    row1_min=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row1',{}).get('inputs',[{},{}])[0].get('value',''))" 2>/dev/null)
    if [[ -z "$row0_min" || -z "$row0_max" || -z "$row1_min" ]]; then
        local ranges_json
        ranges_json=$(extract_shipping_ranges_by_text)
        [[ -z "$row0_min" ]] && row0_min=$(echo "$ranges_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('min',''))" 2>/dev/null)
        [[ -z "$row0_max" ]] && row0_max=$(echo "$ranges_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('max',''))" 2>/dev/null)
        [[ -z "$row1_min" ]] && row1_min=$(echo "$ranges_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row1',{}).get('min',''))" 2>/dev/null)
    fi

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

    # 先打开当前行发货时间下拉，再点击目标值（兼容 ant / next）
    local target_esc
    target_esc=$(js_escape "$target_value")
    local select_result
    select_result=$(bw_evaluate "() => { const target='${target_esc}'; const norm=(s)=>(s||'').replace(/\\s+/g,'').trim().toLowerCase(); const targetNorm=norm(target); const alias=(t)=>{ const arr=[targetNorm]; if (targetNorm.includes('72小时')) arr.push('3天发货','72小时发货','72h发货','三天发货'); if (targetNorm.includes('48小时')) arr.push('2天发货','48小时发货','48h发货','两天发货'); return arr; }; const candidates=alias(target); const matches=(txt)=>{ const t=norm(txt); if(!t) return false; return candidates.some(c=>t===norm(c) || t.includes(norm(c)) || norm(c).includes(t)); }; const tables=Array.from(document.querySelectorAll('table')); const st=tables.find(t=>{const tx=(t.innerText||''); return tx.includes('发货时间')&&tx.includes('购买数量');}); if(!st) return 'TABLE_NOT_FOUND'; const rows=st.querySelectorAll('tbody tr'); const row=rows[${row_index}]; if(!row) return 'ROW_NOT_FOUND'; if (matches(row.innerText||'')) return 'already'; const primary=row.querySelector('td:nth-child(3) .ant-select') || row.querySelector('td:nth-child(3) .next-select') || row.querySelector('.ant-select') || row.querySelector('.next-select'); if(!primary) return 'SELECT_NOT_FOUND'; const selector=primary.querySelector('.ant-select-selector,.next-select-inner') || primary; selector.scrollIntoView({behavior:'auto',block:'center'}); ['mousedown','mouseup','click'].forEach(ev=>selector.dispatchEvent(new MouseEvent(ev,{bubbles:true,cancelable:true,view:window}))); const arrow=primary.querySelector('.ant-select-arrow,.next-icon,.next-select-trigger'); if(arrow){ ['mousedown','mouseup','click'].forEach(ev=>arrow.dispatchEvent(new MouseEvent(ev,{bubbles:true,cancelable:true,view:window}))); } const allOpts=()=>Array.from(document.querySelectorAll('.ant-select-item-option,.ant-select-dropdown .ant-select-item-option-content,.next-menu-item,.next-select-menu .next-menu-item,.next-select-menu li,.next-overlay-inner li')); const tryClick=()=>{ const opts=allOpts(); for(const el of opts){ const tx=(el.innerText||'').trim(); if(matches(tx)){ el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,view:window})); el.click(); return true; } } return false; }; if (tryClick()) return 'selected'; const scrollers=Array.from(document.querySelectorAll('.ant-select-dropdown .rc-virtual-list-holder,.ant-select-dropdown .rc-virtual-list,.ant-select-dropdown,.next-overlay-wrapper .next-menu,.next-overlay-wrapper,[class*=dropdown],[class*=menu]')); for(const box of scrollers){ for(let i=0;i<8;i++){ try{ box.scrollTop = (box.scrollTop||0) + 180; }catch(e){} if(tryClick()) return 'selected'; } } return 'NOT_FOUND'; }" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','FAILED'))" 2>/dev/null)

    sleep 1.2
    if [[ "$select_result" == "selected" || "$select_result" == "already" ]]; then
        log OK "  ✅ 已选择「${target_value}」"
        return 0
    else
        log ERROR "  ❌ 选择「${target_value}」失败：${select_result}"
        return 1
    fi
}

set_input_value_js() {
    local row_index="$1"
    local input_index="$2"
    local value="$3"
    local value_esc
    value_esc=$(js_escape "$value")
    cat <<EOF
() => {
  const table = Array.from(document.querySelectorAll("table")).find(t => t.innerText.includes("发货时间") && t.innerText.includes("购买数量"));
  if (!table) return "TABLE_NOT_FOUND";
  const rows = table.querySelectorAll("tbody tr");
  const row = rows[${row_index}];
  if (!row) return "ROW_NOT_FOUND";
  const inputs = Array.from(row.querySelectorAll("input.ant-input-number-input,input")).filter(i => {
    if (!i || i.type === "hidden" || i.type === "search") return false;
    const cls = i.className || "";
    if (cls.indexOf("ant-input-number-input") >= 0) return true;
    return (i.value || "").trim() !== "" || (i.placeholder || "").trim() !== "";
  });
  const inp = inputs[${input_index}] || null;
  if (!inp) return "INPUT_NOT_FOUND";
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  try { inp.removeAttribute("readonly"); } catch(e) {}
  inp.focus();
  nativeSetter.call(inp, "${value_esc}");
  inp.dispatchEvent(new Event("input", {bubbles: true}));
  inp.dispatchEvent(new Event("change", {bubbles: true}));
  inp.dispatchEvent(new Event("blur", {bubbles: true}));
  return "INPUT_SET:${row_index}:${input_index}:${value_esc}";
}
EOF
}

set_quantity_values() {
    local write_failed=0
    local r

    # row0: min / max
    r=$(bw_evaluate "$(set_input_value_js 0 0 "$ROW1_MIN")" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','FAILED'))" 2>/dev/null)
    [[ "$r" == INPUT_SET* ]] || write_failed=1
    sleep 0.6
    r=$(bw_evaluate "$(set_input_value_js 0 1 "$ROW1_MAX")" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','FAILED'))" 2>/dev/null)
    [[ "$r" == INPUT_SET* ]] || write_failed=1
    sleep 0.6

    # row1: min
    r=$(bw_evaluate "$(set_input_value_js 1 0 "$ROW2_MIN")" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result','FAILED'))" 2>/dev/null)
    [[ "$r" == INPUT_SET* ]] || write_failed=1
    sleep 0.6

    if [[ $write_failed -eq 1 ]]; then
        log WARN "  ⚠️ 部分数量区间输入框未成功写入，进入结果校验"
    fi

    # 回读校验
    local values_json row0_min row0_max row1_min
    values_json=$(extract_shipping_values)
    row0_min=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('inputs',[{},{}])[0].get('value',''))" 2>/dev/null)
    row0_max=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('inputs',[{},{}])[1].get('value',''))" 2>/dev/null)
    row1_min=$(echo "$values_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row1',{}).get('inputs',[{},{}])[0].get('value',''))" 2>/dev/null)

    if [[ "$row0_min" != "$ROW1_MIN" || "$row0_max" != "$ROW1_MAX" || "$row1_min" != "$ROW2_MIN" ]]; then
        local ranges_json t_row0_min t_row0_max t_row1_min
        ranges_json=$(extract_shipping_ranges_by_text)
        t_row0_min=$(echo "$ranges_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('min',''))" 2>/dev/null)
        t_row0_max=$(echo "$ranges_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row0',{}).get('max',''))" 2>/dev/null)
        t_row1_min=$(echo "$ranges_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('row1',{}).get('min',''))" 2>/dev/null)
        if [[ "$t_row0_min" == "$ROW1_MIN" && "$t_row0_max" == "$ROW1_MAX" && "$t_row1_min" == "$ROW2_MIN" ]]; then
            log WARN "  ⚠️ 输入框读值为空，按规则文本校验数量区间已匹配：${ROW1_MIN}~${ROW1_MAX} / ${ROW2_MIN}+"
            return 0
        fi
        log ERROR "  ❌ 数量区间校验失败：期望(${ROW1_MIN},${ROW1_MAX},${ROW2_MIN}) 实际(${row0_min},${row0_max},${row1_min}) / 文本(${t_row0_min},${t_row0_max},${t_row1_min})"
        return 1
    fi

    log OK "  ✅ 数量区间已对齐：${ROW1_MIN}~${ROW1_MAX} / ${ROW2_MIN}+"
    return 0
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

    # 2. 登录态校验（进入编辑页后、执行自动化前）
    local page_text
    page_text=$(bw_evaluate '() => { return document.body ? document.body.innerText.substring(0, 200) : "NO_BODY"; }' \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result',''))" 2>/dev/null)
    if [[ "$page_text" == *"登录"* || "$page_text" == *"请登录"* || "$page_text" == "NO_BODY" ]]; then
        wait_for_login_ready || { FAILED=$((FAILED + 1)); return; }
    fi

    # 3. 验证码检测
    local captcha
    captcha=$(check_captcha)
    if [[ "$captcha" != "CLEAN" ]]; then
        wait_for_captcha_clear
    fi

    # 4. 滚动到发货服务区域
    scroll_to_shipping_section
    sleep 1

    # 5. 提取当前值
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

    # 7.0 先确保数量区间与配置一致
    set_quantity_values || modify_failed=1
    sleep 0.8

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
        wait_for_login_ready || exit 1
    fi

    PROCESSED_FILE=$(mktemp)
    trap 'rm -f "$PROCESSED_FILE"' EXIT

    local terms_file
    terms_file=$(mktemp)
    build_search_terms > "$terms_file"
    local term_count
    term_count=$(wc -l < "$terms_file" | tr -d ' ')
    log INFO "将按 ${term_count} 个检索词逐个执行（先搜索再自动化）"

    while IFS= read -r search_term; do
        [[ -n "$search_term" ]] || continue
        log INFO "────────────────────────────────────────"
        log INFO "🔎 检索词：${search_term}"

        bw_navigate "$LIST_URL" > /dev/null
        sleep 4

        captcha=$(check_captcha)
        if [[ "$captcha" != "CLEAN" ]]; then
            wait_for_captcha_clear || true
        fi
        page_text=$(bw_evaluate '() => { return document.body ? document.body.innerText.substring(0, 200) : "NO_BODY"; }' \
            | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('result',''))" 2>/dev/null)
        if [[ "$page_text" == *"登录"* || "$page_text" == *"请登录"* || "$page_text" == "NO_BODY" ]]; then
            wait_for_login_ready || exit 1
        fi

        local search_status
        search_status=$(search_list_by_keyword "$search_term")
        if [[ "$search_status" != "SEARCH_DONE" ]]; then
            log ERROR "检索失败（${search_term}）：${search_status}"
            FAILED=$((FAILED + 1))
            continue
        fi
        sleep 4

        captcha=$(check_captcha)
        if [[ "$captcha" != "CLEAN" ]]; then
            wait_for_captcha_clear || true
        fi

        local products_json
        products_json=$(extract_page_products "$search_term")
        process_products_json "$products_json"
        if [[ "$LAST_HANDLED_COUNT" == "0" ]]; then
            log WARN "检索词未命中商品：${search_term}"
        else
            log OK "检索词处理完成：${search_term}（处理 ${LAST_HANDLED_COUNT} 条）"
        fi
    done < "$terms_file"
    rm -f "$terms_file"

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
