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
TARGET_URL="${TARGET_URL:-https://sale.1688.com/factory/ossdql9d.html}"

# 操作参数
ACTION_DELAY=2          # 每次退出后等待（秒）
HOVER_WAIT=1            # hover 后等待弹出菜单（秒）
CONFIRM_WAIT=1          # 点击退出后等待确认弹窗（秒）
REFRESH_WAIT=3          # 退出后等待列表刷新（秒）
PAGE_LOAD_WAIT=8        # 页面加载等待（秒）
MAX_EXIT_COUNT=500      # 最大退出数量限制
MAX_CONSECUTIVE_ERRORS=5  # 连续错误上限
NON_INTERACTIVE="${NON_INTERACTIVE:-0}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-900}"
EXPECTED_SHOP="${EXPECTED_SHOP:-}"

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
        page_text=$(bw_evaluate '() => { return document.body ? document.body.innerText.substring(0, 200) : "NO_BODY"; }' | parse_result)
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

get_context_json() {
    bw_evaluate '() => {
      function t(el){ return ((el && (el.innerText || el.textContent || "")) || "").replace(/\s+/g," ").trim(); }
      function maybeShop(s){ if(!s) return false; if(s.length < 3 || s.length > 40) return false; if(/去加入|创建|立刻|查看|规则|示例|开单|登录|退出|帮助/.test(s)) return false; if(/公司|店|商贸|贸易|科技|供应链|工贸|工厂|生物|化工/.test(s)) return true; return false; }
      var url = location.href || "";
      var body = document.body ? t(document.body).slice(0, 3000) : "";
      var hints = ["请登录","登录后","登录查看","登录"];
      var isLogin = true;
      if (!document.body || body === "NO_BODY") isLogin = false;
      if (/login|passport|signin/i.test(url)) isLogin = false;
      for (var i = 0; i < hints.length; i++) {
        if (body.indexOf(hints[i]) >= 0 && body.indexOf("退出登录") < 0) { isLogin = false; break; }
      }
      var sels = [".company-name",".member-company-name",".shop-name",".seller-name",".site-nav-user .user-nick",'a[href*="member.1688.com"]','a[href*="work.1688.com"]'];
      var shops = [];
      sels.forEach(function(sel){
        try { document.querySelectorAll(sel).forEach(function(el){ var s=t(el); if(!maybeShop(s)) return; shops.push(s); }); } catch(e) {}
      });
      var dedup = [];
      shops.forEach(function(s){ if (dedup.indexOf(s) < 0) dedup.push(s); });
      return JSON.stringify({url:url,isLogin:isLogin,shops:dedup.slice(0,8)});
    }' | parse_result
}

parse_list_count() {
    local status="${1:-}"
    case "$status" in
        HAS_ITEMS:*) echo "${status#HAS_ITEMS:}" ;;
        HAS:*) echo "${status#HAS:}" ;;
        UNCERTAIN:*) echo "${status#UNCERTAIN:}" ;;
        EMPTY) echo "0" ;;
        *) echo "" ;;
    esac
}

ensure_login_and_shop() {
    local stage="${1:-}"
    local stage_text=""
    [[ -n "$stage" ]] && stage_text="[${stage}] "

    local ctx is_login shops
    ctx=$(get_context_json)
    is_login=$(echo "$ctx" | python3 -c "import sys,json; d=json.loads(sys.stdin.read() or '{}'); print('1' if d.get('isLogin') else '0')" 2>/dev/null || echo "0")
    shops=$(echo "$ctx" | python3 -c "import sys,json; d=json.loads(sys.stdin.read() or '{}'); print(' | '.join(d.get('shops',[])))" 2>/dev/null || true)

    if [[ "$is_login" != "1" ]]; then
        log WARN "${stage_text}检测到未登录"
        wait_for_login_ready || return 1
        ctx=$(get_context_json)
        shops=$(echo "$ctx" | python3 -c "import sys,json; d=json.loads(sys.stdin.read() or '{}'); print(' | '.join(d.get('shops',[])))" 2>/dev/null || true)
    fi

    if [[ -n "$shops" ]]; then
        log INFO "${stage_text}当前检测到店铺/账号信息：${shops}"
    else
        log WARN "${stage_text}未能识别店铺名称，请人工确认当前登录店铺是否正确"
    fi

    if [[ -n "$EXPECTED_SHOP" ]]; then
        local hit
        hit=$(echo "$ctx" | python3 - "$EXPECTED_SHOP" <<'PY'
import json,sys
d=json.loads(sys.stdin.read() or '{}')
exp=sys.argv[1]
shops=d.get('shops',[])
print('1' if any(exp in s for s in shops) else '0')
PY
)
        if [[ "$hit" != "1" ]]; then
            log ERROR "${stage_text}店铺校验失败：期望包含「${EXPECTED_SHOP}」，当前识别=${shops:-<空>}"
            return 1
        fi
        log OK "${stage_text}店铺校验通过：${EXPECTED_SHOP}"
    fi
    return 0
}

switch_joined_tab() {
    local attempt result
    for attempt in 1 2 3 4; do
        result=$(bw_evaluate '() => {
          function txt(el){ return ((el && (el.innerText || el.textContent || "")) || "").replace(/\s+/g," ").trim(); }
          function visible(el){ if(!el) return false; var st=window.getComputedStyle(el); if(!st || st.display==="none" || st.visibility==="hidden") return false; var r=el.getBoundingClientRect(); return r.width>0 && r.height>0; }
          function active(el){ if(!el) return false; var c=(el.className||"")+" "+((el.parentElement&&el.parentElement.className)||""); return /active|current|selected|is-active|next-tabs-tab-active|ant-tabs-tab-active/i.test(c) || el.getAttribute("aria-selected")==="true"; }
          function clickLike(el){ if(!el) return false; try{ el.scrollIntoView({behavior:"auto",block:"center"});}catch(e){} try{ el.click(); return true;}catch(e2){} try{["mouseover","mousedown","mouseup","click"].forEach(function(t){el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window}));}); return true;}catch(e3){} return false; }
          var tabs = Array.from(document.querySelectorAll("[role=tab],.next-tabs-tab,.ant-tabs-tab,li,a,span,button")).filter(visible);
          var target = tabs.find(function(el){ return txt(el).indexOf("已加入哇噢定制") >= 0; });
          if (!target) return "TAB_NOT_FOUND";
          if (active(target)) return "ALREADY";
          if (!clickLike(target)) return "TAB_CLICK_FAILED";
          var p = target.closest("[role=tab],.next-tabs-tab,.ant-tabs-tab,li,a,button,span");
          if (p && p !== target) clickLike(p);
          return "SWITCHED";
        }' | parse_result)
        if [[ "$result" == "SWITCHED" || "$result" == "ALREADY" ]]; then
            echo "$result"
            return 0
        fi
        log WARN "页签切换第${attempt}次失败：${result}"
        if [[ "$attempt" == "2" ]]; then
            bw_navigate "$TARGET_URL" > /dev/null
            sleep 4
        fi
        sleep 2
    done
    echo "${result:-TAB_SWITCH_FAILED}"
    return 1
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
    result=$(bw_evaluate '() => { function visible(el){ if(!el) return false; var st=window.getComputedStyle(el); if(!st || st.display==="none" || st.visibility==="hidden") return false; var r=el.getBoundingClientRect(); return r.width>0 && r.height>0; } function txt(el){ return ((el && (el.innerText || el.textContent || "")) || "").replace(/\s+/g," ").trim(); } function fire(el,t){ try{ el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window})); return true; }catch(e){} return false; } var rows = Array.from(document.querySelectorAll("tbody tr")).filter(function(row){ var t=txt(row); return visible(row) && t && t.indexOf("暂无")<0 && t.indexOf("没有数据")<0; }); if(rows.length===0) return "NO_ROWS"; var row = rows[0]; var targets = Array.from(row.querySelectorAll("img,svg,i,button,a,span,div,[role=button]")).filter(visible).slice(0,60); if(targets.length===0) return "NO_HOVER_TARGET"; targets.forEach(function(el){ fire(el,"mouseenter"); fire(el,"mouseover"); fire(el,"mousemove"); }); var pop=document.querySelector(".next-balloon,.ant-popover,[role=tooltip]"); if(pop && visible(pop) && txt(pop).indexOf("退出")>=0) return "HOVER_OK:POPOVER_READY"; return "HOVER_OK:SENT:"+targets.length; }')
    echo "$result" | parse_result
}

# 语义优先：直接在第一行/浮层中定位“退出”入口
click_exit_entry() {
    local script result
    script=$(cat <<'EOF'
() => {
  function visible(el) {
    if (!el) return false;
    var style = window.getComputedStyle(el);
    if (!style || style.display === "none" || style.visibility === "hidden") return false;
    var rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }
  function txt(el) {
    return ((el && (el.innerText || el.textContent || "")) || "").replace(/\s+/g, " ").trim();
  }
  function clickLike(el) {
    if (!el) return false;
    try { el.scrollIntoView({behavior:"auto", block:"center"}); } catch (e) {}
    try { el.click(); return true; } catch (e) {}
    try {
      ["mouseover","mousedown","mouseup","click"].forEach(function(type) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window}));
      });
      return true;
    } catch (e2) {}
    return false;
  }
  var rows = Array.from(document.querySelectorAll("tbody tr")).filter(function(row) {
    return visible(row) && txt(row) && txt(row).indexOf("暂无") < 0;
  });
  if (rows.length > 0) {
    var row = rows[0];
    var nodes = Array.from(row.querySelectorAll("button,a,span,div")).filter(visible);
    var strong = nodes.find(function(el) {
      var t = txt(el);
      return t.indexOf("退出哇噢定制") >= 0 || t.indexOf("退出定制") >= 0;
    });
    if (strong && clickLike(strong.closest("button,a,[role=button],.next-btn,.ant-btn") || strong)) return "DIRECT_EXIT_CLICKED";
    var weak = nodes.find(function(el) {
      var t = txt(el);
      return t === "退出" || t.indexOf("退出") >= 0;
    });
    if (weak && clickLike(weak.closest("button,a,[role=button],.next-btn,.ant-btn") || weak)) return "DIRECT_EXIT_CLICKED_FUZZY";
  }
  var balloon = document.querySelector(".next-balloon,.ant-popover,[role=tooltip]");
  if (balloon && visible(balloon)) {
    var btns = Array.from(balloon.querySelectorAll("button,a,span,div")).filter(visible);
    var b = btns.find(function(el) { return txt(el).indexOf("退出") >= 0; });
    if (b && clickLike(b.closest("button,a,[role=button],.next-btn,.ant-btn") || b)) return "EXIT_FROM_POPUP";
  }
  return "DIRECT_EXIT_NOT_FOUND";
}
EOF
)
    result=$(bw_evaluate "$script")
    echo "$result" | parse_result
}

# 点击"退出哇噢定制"按钮
click_exit_button() {
    local result
    result=$(bw_evaluate '() => { function visible(el){ if(!el) return false; var st=window.getComputedStyle(el); if(!st || st.display==="none" || st.visibility==="hidden") return false; var r=el.getBoundingClientRect(); return r.width>0 && r.height>0; } function txt(el){ return ((el && (el.innerText || el.textContent || "")) || "").replace(/\s+/g," ").trim(); } function clickLike(el){ if(!el) return false; try{ el.scrollIntoView({behavior:"auto", block:"center"}); }catch(e){} try{ el.click(); return true; }catch(e2){} try{ ["mouseover","mousedown","mouseup","click"].forEach(function(t){ el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window})); }); return true; }catch(e3){} return false; } var roots = Array.from(document.querySelectorAll(".next-balloon,.ant-popover,[role=tooltip],body")).filter(visible); for(var i=0;i<roots.length;i++){ var nodes = Array.from(roots[i].querySelectorAll("button,a,span,div,[role=button]")).filter(visible); var strong = nodes.find(function(el){ var t=txt(el); return t.indexOf("退出哇噢定制")>=0 || t.indexOf("退出定制")>=0; }); if(strong && clickLike(strong.closest("button,a,[role=button],.next-btn,.ant-btn") || strong)) return "EXIT_CLICKED"; var weak = nodes.find(function(el){ return txt(el).indexOf("退出")>=0; }); if(weak && clickLike(weak.closest("button,a,[role=button],.next-btn,.ant-btn") || weak)) return "EXIT_CLICKED"; } return "EXIT_BTN_NOT_FOUND"; }')
    echo "$result" | parse_result
}

# 点击确认弹窗的"确定"按钮
click_confirm_button() {
    local result
    result=$(bw_evaluate '() => { function visible(el){ if(!el) return false; var st=window.getComputedStyle(el); if(!st || st.display==="none" || st.visibility==="hidden") return false; var r=el.getBoundingClientRect(); return r.width>0 && r.height>0; } function txt(el){ return ((el && (el.innerText || el.textContent || "")) || "").replace(/\s+/g," ").trim(); } function clickLike(el){ if(!el) return false; try{ el.click(); return true; }catch(e){} try{ ["mousedown","mouseup","click"].forEach(function(t){ el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window})); }); return true; }catch(e2){} return false; } var roots = Array.from(document.querySelectorAll(".next-dialog,.ant-modal,[role=dialog],body")).filter(visible); for(var i=0;i<roots.length;i++){ var nodes = Array.from(roots[i].querySelectorAll("button,a,span,div,[role=button]")).filter(visible); var btn = nodes.find(function(el){ var t=txt(el); return t==="确定" || t==="确认" || t.indexOf("确认退出")>=0 || t.indexOf("退出")>=0; }); if(btn && clickLike(btn.closest("button,a,[role=button],.next-btn,.ant-btn") || btn)) return "CONFIRMED"; } return "NO_DIALOG"; }')
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
    if [[ -n "$EXPECTED_SHOP" ]]; then
        echo "  店铺校验：${EXPECTED_SHOP}"
    fi
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

    # 2. 导航前登录与店铺检查（防串店）
    ensure_login_and_shop "导航前" || exit 1

    # 3. 导航到哇噢定制页面
    log INFO "导航到哇噢定制页面..."
    bw_navigate "$TARGET_URL" > /dev/null
    sleep $PAGE_LOAD_WAIT

    # 4. 导航后登录与店铺复核
    ensure_login_and_shop "导航后" || exit 1

    # 5. 验证码检测
    local captcha
    captcha=$(check_captcha)
    if [[ "$captcha" != "CLEAN" ]]; then
        wait_for_captcha_clear
    fi

    # 6. 切换到“已加入哇噢定制”页签（增强重试）
    log INFO "切换到「已加入哇噢定制」标签..."
    local tab_result
    if ! tab_result=$(switch_joined_tab); then
        log ERROR "❌ 标签切换失败：${tab_result}"
        exit 1
    fi
    log OK "✅ 已切换到「已加入哇噢定制」（${tab_result}）"
    sleep 3

    # 7. 检查列表状态
    local list_status
    list_status=$(check_list_empty)
    if [[ "$list_status" == "EMPTY" ]]; then
        log OK "🎉 列表为空，没有需要退出的商品！"
        exit 0
    fi
    log OK "✅ 检测到商品：${list_status}"

    # 8. 截图记录初始状态
    bw_screenshot "${SCREENSHOT_DIR}/before_exit.png" > /dev/null

    # 9. 开始批量退出循环
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

        # 每轮执行前先校验登录态与店铺，避免会话过期或串店
        ensure_login_and_shop "轮次${EXIT_COUNT}" || break

        # 当前剩余商品数
        local remaining
        remaining=$(echo "$list_status" | sed 's/HAS_ITEMS://')
        EXIT_COUNT=$((EXIT_COUNT + 1))

        echo ""
        log INFO "────────────────────────────────────────"
        log INFO "📦 第 ${EXIT_COUNT} 件（剩余 ${remaining:-?} 件）"

        # Step A: 语义优先直点；未命中再回退 hover
        log INFO "  [a] 尝试语义定位退出入口..."
        local direct_result
        direct_result=$(click_exit_entry)
        local exit_result
        if [[ "$direct_result" == DIRECT_EXIT_CLICKED* || "$direct_result" == "EXIT_FROM_POPUP" ]]; then
            log OK "  ✅ 语义直点成功（${direct_result}）"
            exit_result="EXIT_CLICKED"
        else
            log WARN "  ⚠️ 语义直点未命中（${direct_result}），回退 hover 方案"
            log INFO "  [a2] 悬停问号图标..."
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
            log INFO "  [b] 点击退出按钮..."
            exit_result=$(click_exit_button)
        fi

        # Step B: 点击退出结果确认
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
        local before_count
        before_count=$(parse_list_count "$list_status")

        local confirm_result
        confirm_result=$(click_confirm_button)
        local confirmed="0"
        if [[ "$confirm_result" != "CONFIRMED" ]]; then
            log WARN "  ⚠️ 确认弹窗操作异常：${confirm_result}"
            # 可能弹窗还没出来，再等一下重试
            sleep 2
            confirm_result=$(click_confirm_button)
            if [[ "$confirm_result" != "CONFIRMED" ]]; then
                log WARN "  ⚠️ 未发现确认弹窗：${confirm_result}，将按列表变化判定"
                dismiss_popover
            else
                confirmed="1"
            fi
        else
            confirmed="1"
        fi
        if [[ "$confirmed" == "1" ]]; then
            log OK "  ✅ 已确认退出第 ${EXIT_COUNT} 件商品"
            ERROR_COUNT=0  # 重置连续错误计数
        fi

        # 等待列表刷新
        log INFO "  [d] 等待列表刷新..."
        sleep $REFRESH_WAIT

        if [[ "$confirmed" != "1" ]]; then
            local after_status after_count
            after_status=$(check_list_empty)
            after_count=$(parse_list_count "$after_status")
            if [[ -n "$before_count" && -n "$after_count" && "$after_count" =~ ^[0-9]+$ && "$before_count" =~ ^[0-9]+$ ]] && (( after_count < before_count )); then
                ERROR_COUNT=0
                log OK "  ✅ 列表数量已下降（${before_count} -> ${after_count}），判定退出成功"
            else
                log ERROR "  ❌ 确认失败且列表未下降：before=${before_count} after=${after_count} status=${after_status}"
                ERROR_COUNT=$((ERROR_COUNT + 1))
                if (( ERROR_COUNT >= MAX_CONSECUTIVE_ERRORS )); then
                    log ERROR "  ❌ 连续 ${MAX_CONSECUTIVE_ERRORS} 次错误，终止操作"
                    break
                fi
                sleep $ACTION_DELAY
                continue
            fi
        fi

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
