#!/usr/bin/env python3
"""
1688 批量退出哇噢定制（BrowserWing REST API + Python 版）
功能：导航到 sale.1688.com 已加入哇噢定制商品列表，逐个：
      切换标签 → React Fiber hover 问号图标 → 点击退出 → 确认退出

用法：
  python3 exit_waodingzhi.py                  # 默认退出 500 件
  python3 exit_waodingzhi.py --count 20       # 退出 20 件
  python3 exit_waodingzhi.py --count 0        # 退出全部

前置条件：
  1. BrowserWing 已启动（cd /tmp && browserwing --port 8080）
  2. 已在 BrowserWing 控制的浏览器中登录 1688
  3. Python requests 库已安装（pip install requests）

跨平台：
  - macOS / Linux: python3 exit_waodingzhi.py
  - Windows:       python exit_waodingzhi.py
"""
import json, time, sys, os, argparse, requests

# ── 配置 ──────────────────────────────────────────────────────────────────
BW_PORT = int(os.environ.get("BW_PORT", "8080"))
BW_BASE = f"http://localhost:{BW_PORT}/api/v1/executor"
TARGET_URL = os.environ.get("TARGET_URL", "https://sale.1688.com/factory/ossdql9d.html")

ACTION_DELAY = 2       # 每次退出后等待（秒）
HOVER_WAIT = 1         # hover 后等待弹出菜单（秒）
CONFIRM_WAIT = 2       # 点击退出后等待确认弹窗（秒）
REFRESH_WAIT = 4       # 退出后等待列表刷新（秒）
PAGE_LOAD_WAIT = 8     # 页面加载等待（秒）
MAX_CONSECUTIVE_ERRORS = 5
WAIT_TIMEOUT = int(os.environ.get("WAIT_TIMEOUT", "900"))


# ── 工具函数 ──────────────────────────────────────────────────────────────
def log(level, msg):
    colors = {"INFO": "\033[0;34m", "OK": "\033[0;32m", "WARN": "\033[0;33m", "ERROR": "\033[0;31m"}
    color = colors.get(level, "\033[0m")
    ts = time.strftime("%H:%M:%S")
    print(f"{color}[{ts}] [{level}] {msg}\033[0m", flush=True)


def evaluate(script):
    """执行 JS 并返回 result 字符串"""
    try:
        r = requests.post(f"{BW_BASE}/evaluate", json={"script": script}, timeout=15)
        d = r.json()
        if d.get("success"):
            return d.get("data", {}).get("result", "")
        return f"ERROR: {d.get('error', '')}"
    except Exception as e:
        return f"ERROR: {e}"


def navigate(url):
    try:
        r = requests.post(f"{BW_BASE}/navigate",
                         json={"url": url, "wait_until": "load", "timeout": 30},
                         timeout=40)
        return r.json().get("success", False)
    except:
        return False


def screenshot(path):
    try:
        requests.post(f"{BW_BASE}/screenshot", json={"path": path}, timeout=10)
    except:
        pass


def wait_until(desc, cond, timeout=WAIT_TIMEOUT, interval=5):
    start = time.time()
    while True:
        if cond():
            return True
        if time.time() - start > timeout:
            log("ERROR", f"⏱️ 等待超时：{desc}")
            return False
        time.sleep(interval)


# ── JS 代码片段 ──────────────────────────────────────────────────────────

JS_CHECK_BW = "() => { return 'BW_OK'; }"

JS_CHECK_LOGIN = """() => {
  return document.body ? document.body.innerText.substring(0, 200) : 'NO_BODY';
}"""

JS_GET_CONTEXT = """() => {
  function t(el) { return ((el && (el.innerText || el.textContent || '')) || '').replace(/\\s+/g, ' ').trim(); }
  function maybeShop(s) {
    if (!s) return false;
    if (s.length < 3 || s.length > 40) return false;
    if (/去加入|创建|立刻|查看|规则|示例|开单|登录|退出|帮助/.test(s)) return false;
    if (/公司|店|商贸|贸易|科技|供应链|工贸|工厂|生物|化工/.test(s)) return true;
    return false;
  }
  var url = location.href || '';
  var body = document.body ? t(document.body).slice(0, 3000) : '';
  var loginHints = ['请登录', '登录后', '登录查看', '登录'];
  var isLogin = true;
  if (!document.body || body === 'NO_BODY') isLogin = false;
  if (/login|passport|signin/i.test(url)) isLogin = false;
  for (var i = 0; i < loginHints.length; i++) {
    if (body.indexOf(loginHints[i]) >= 0 && body.indexOf('退出登录') < 0) { isLogin = false; break; }
  }

  var sels = [
    '.company-name', '.member-company-name', '.shop-name', '.seller-name',
    '.site-nav-user .user-nick',
    'a[href*="member.1688.com"]', 'a[href*="work.1688.com"]'
  ];
  var shops = [];
  sels.forEach(function(sel) {
    try {
      document.querySelectorAll(sel).forEach(function(el) {
        var s = t(el);
        if (!maybeShop(s)) return;
        shops.push(s);
      });
    } catch (e) {}
  });
  var dedup = [];
  shops.forEach(function(s) {
    if (dedup.indexOf(s) < 0) dedup.push(s);
  });
  return JSON.stringify({url: url, isLogin: isLogin, shops: dedup.slice(0, 8)});
}"""

JS_CHECK_CAPTCHA = """() => {
  var sels = ['.nc_wrapper','#nc_1__wrapper','[id*=nocaptcha]','[class*=nocaptcha]',
    '[class*=slider-captcha]','[class*=captcha]','[class*=verify]',
    '[class*=slider-track]','[class*=aliyun-captcha]','.no-captcha',
    '#nc_1_wrapper','[class*=risk]','[class*=security-check]'];
  var found = [];
  sels.forEach(function(sel) {
    try { document.querySelectorAll(sel).forEach(function(el) {
      if (el.offsetParent !== null) found.push(sel);
    }); } catch(e) {}
  });
  return found.length > 0 ? 'CAPTCHA:' + found.join(',') : 'CLEAN';
}"""

JS_SWITCH_TAB = """() => {
  function txt(el) { return ((el && (el.innerText || el.textContent || '')) || '').replace(/\\s+/g, ' ').trim(); }
  function visible(el) {
    if (!el) return false;
    var st = window.getComputedStyle(el);
    if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function active(el) {
    if (!el) return false;
    var c = (el.className || '') + ' ' + ((el.parentElement && el.parentElement.className) || '');
    return /active|current|selected|is-active|next-tabs-tab-active|ant-tabs-tab-active/i.test(c) || el.getAttribute('aria-selected') === 'true';
  }
  function clickLike(el) {
    if (!el) return false;
    try { el.scrollIntoView({behavior:'auto', block:'center'}); } catch (e) {}
    try { el.click(); return true; } catch (e2) {}
    try {
      ['mouseover', 'mousedown', 'mouseup', 'click'].forEach(function(type) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window}));
      });
      return true;
    } catch (e3) {}
    return false;
  }
  var tabs = Array.from(document.querySelectorAll('[role=tab], .next-tabs-tab, .ant-tabs-tab, li, a, span, button')).filter(visible);
  var target = tabs.find(function(el) {
    var t = txt(el);
    return t.indexOf('已加入哇噢定制') >= 0;
  });
  if (!target) return 'TAB_NOT_FOUND';
  if (active(target)) return 'ALREADY';
  if (clickLike(target)) {
    var parent = target.closest('[role=tab], .next-tabs-tab, .ant-tabs-tab, li, a, button, span');
    if (parent && parent !== target) clickLike(parent);
    return 'SWITCHED';
  }
  return 'TAB_CLICK_FAILED';
}"""

JS_CHECK_LIST = """() => {
  var rows = document.querySelectorAll('tbody tr');
  if (rows.length === 0) return 'EMPTY';
  var t = rows[0].innerText.trim();
  if ((t === '暂无数据' || t === '暂无' || t === '没有数据' || t === '没有找到' || t.indexOf('暂无') === 0) && t.length < 20) return 'EMPTY';
  if (t.indexOf('ID：') >= 0 || t.indexOf('ID:') >= 0) return 'HAS:' + rows.length;
  if (rows.length > 2) return 'HAS:' + rows.length;
  return 'UNCERTAIN:' + rows.length;
}"""

JS_DIRECT_EXIT = """() => {
  function visible(el) {
    if (!el) return false;
    var style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    var rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }
  function txt(el) {
    return (el && (el.innerText || el.textContent || '') || '').replace(/\\s+/g, ' ').trim();
  }
  function clickLike(el) {
    if (!el) return false;
    try { el.scrollIntoView({behavior:'auto', block:'center'}); } catch (e) {}
    try { el.click(); return true; } catch (e) {}
    try {
      ['mouseover','mousedown','mouseup','click'].forEach(function(type) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window}));
      });
      return true;
    } catch (e2) {}
    return false;
  }
  var rows = Array.from(document.querySelectorAll('tbody tr')).filter(function(row) {
    return visible(row) && txt(row) && txt(row).indexOf('暂无') < 0;
  });
  if (rows.length > 0) {
    var row = rows[0];
    var nodes = Array.from(row.querySelectorAll('button,a,span,div')).filter(visible);
    var strong = nodes.find(function(el) {
      var t = txt(el);
      return t.indexOf('退出哇噢定制') >= 0 || t.indexOf('退出定制') >= 0;
    });
    if (strong && clickLike(strong.closest('button,a,[role=button],.next-btn,.ant-btn') || strong)) return 'DIRECT_EXIT_CLICKED';
    var weak = nodes.find(function(el) {
      var t = txt(el);
      return t === '退出' || t.indexOf('退出') >= 0;
    });
    if (weak && clickLike(weak.closest('button,a,[role=button],.next-btn,.ant-btn') || weak)) return 'DIRECT_EXIT_CLICKED_FUZZY';
  }
  var balloon = document.querySelector('.next-balloon,.ant-popover,[role=tooltip]');
  if (balloon && visible(balloon)) {
    var btns = Array.from(balloon.querySelectorAll('button,a,span,div')).filter(visible);
    var b = btns.find(function(el) {
      var t = txt(el);
      return t.indexOf('退出') >= 0;
    });
    if (b && clickLike(b.closest('button,a,[role=button],.next-btn,.ant-btn') || b)) return 'EXIT_FROM_POPUP';
  }
  return 'DIRECT_EXIT_NOT_FOUND';
}"""

JS_HOVER = """() => {
  function visible(el) {
    if (!el) return false;
    var st = window.getComputedStyle(el);
    if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function txt(el) { return ((el && (el.innerText || el.textContent || '')) || '').replace(/\\s+/g, ' ').trim(); }
  function fire(el, type) {
    try { el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window})); return true; } catch (e) {}
    return false;
  }
  var rows = Array.from(document.querySelectorAll('tbody tr')).filter(function(row) {
    var t = txt(row);
    return visible(row) && t && t.indexOf('暂无') < 0 && t.indexOf('没有数据') < 0;
  });
  if (rows.length === 0) return 'NO_ROWS';
  var row = rows[0];
  var targets = Array.from(row.querySelectorAll('img,svg,i,button,a,span,div,[role=button]')).filter(visible).slice(0, 60);
  if (targets.length === 0) return 'NO_HOVER_TARGET';
  targets.forEach(function(el) {
    fire(el, 'mouseenter'); fire(el, 'mouseover'); fire(el, 'mousemove');
  });
  var pop = document.querySelector('.next-balloon,.ant-popover,[role=tooltip]');
  if (pop && visible(pop) && txt(pop).indexOf('退出') >= 0) return 'OK:POPOVER_READY';
  return 'OK:HOVER_SENT:' + targets.length;
}"""

JS_CLICK_EXIT = """() => {
  function visible(el) {
    if (!el) return false;
    var st = window.getComputedStyle(el);
    if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function txt(el) { return ((el && (el.innerText || el.textContent || '')) || '').replace(/\\s+/g, ' ').trim(); }
  function clickLike(el) {
    if (!el) return false;
    try { el.scrollIntoView({behavior:'auto', block:'center'}); } catch (e) {}
    try { el.click(); return true; } catch (e2) {}
    try {
      ['mouseover','mousedown','mouseup','click'].forEach(function(type) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window}));
      });
      return true;
    } catch (e3) {}
    return false;
  }
  var roots = Array.from(document.querySelectorAll('.next-balloon,.ant-popover,[role=tooltip],body')).filter(visible);
  for (var i = 0; i < roots.length; i++) {
    var nodes = Array.from(roots[i].querySelectorAll('button,a,span,div,[role=button]')).filter(visible);
    var strong = nodes.find(function(el) {
      var t = txt(el);
      return t.indexOf('退出哇噢定制') >= 0 || t.indexOf('退出定制') >= 0;
    });
    if (strong && clickLike(strong.closest('button,a,[role=button],.next-btn,.ant-btn') || strong)) return 'CLICKED';
    var weak = nodes.find(function(el) { return txt(el).indexOf('退出') >= 0; });
    if (weak && clickLike(weak.closest('button,a,[role=button],.next-btn,.ant-btn') || weak)) return 'CLICKED';
  }
  return 'EXIT_BTN_NOT_FOUND';
}"""

JS_CONFIRM = """() => {
  function visible(el) {
    if (!el) return false;
    var st = window.getComputedStyle(el);
    if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function txt(el) { return ((el && (el.innerText || el.textContent || '')) || '').replace(/\\s+/g, ' ').trim(); }
  function clickLike(el) {
    if (!el) return false;
    try { el.click(); return true; } catch(e) {}
    try {
      ['mousedown','mouseup','click'].forEach(function(type) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window}));
      });
      return true;
    } catch(e2) {}
    return false;
  }
  var roots = Array.from(document.querySelectorAll('.next-dialog,.ant-modal,[role=dialog],body')).filter(visible);
  for (var i = 0; i < roots.length; i++) {
    var nodes = Array.from(roots[i].querySelectorAll('button,a,span,div,[role=button]')).filter(visible);
    var btn = nodes.find(function(el) {
      var t = txt(el);
      return t === '确定' || t === '确认' || t.indexOf('确认退出') >= 0 || t.indexOf('退出') >= 0;
    });
    if (btn && clickLike(btn.closest('button,a,[role=button],.next-btn,.ant-btn') || btn)) return 'CONFIRMED';
  }
  return 'NO_DIALOG';
}"""

JS_DISMISS = """() => {
  var b = document.querySelector('.next-balloon');
  if (b) b.style.display = 'none';
  var d = document.querySelector('.next-dialog');
  if (d) d.style.display = 'none';
  return 'dismissed';
}"""


# ── 验证码处理 ──────────────────────────────────────────────────────────
def wait_for_captcha_clear(non_interactive=False):
    log("WARN", "⚠️  检测到验证码！请在 BrowserWing 浏览器窗口中手动完成验证...")
    interactive = sys.stdin is not None and sys.stdin.isatty() and not non_interactive
    if interactive:
        print("\n" + "═" * 55)
        print("  🛡️  验证码已触发，请在浏览器窗口中手动处理")
        print("  处理完成后按 [Enter] 继续...")
        print("═" * 55)
        input()
    else:
        log("WARN", "当前为非交互模式：自动轮询验证码状态")

    if wait_until("验证码清除", lambda: evaluate(JS_CHECK_CAPTCHA) == "CLEAN"):
        log("OK", "✅ 验证码已清除，继续执行")
        return True
    else:
        log("ERROR", "验证码等待超时")
        return False


def wait_for_login_ready(non_interactive=False):
    log("WARN", "🔐 检测到未登录，请在 BrowserWing 浏览器中完成登录")
    interactive = sys.stdin is not None and sys.stdin.isatty() and not non_interactive
    if interactive:
        print("\n" + "═" * 55)
        print("  🔐 请在 BrowserWing 控制的浏览器中登录 1688")
        print("  登录完成后按 [Enter] 继续...")
        print("═" * 55)
        input()
    else:
        log("WARN", "当前为非交互模式：自动轮询登录状态")

    return wait_until(
        "登录恢复",
        lambda: (lambda t: t not in ("NO_BODY", "") and "登录" not in t and "请登录" not in t)(evaluate(JS_CHECK_LOGIN)),
    )


def get_context():
    raw = evaluate(JS_GET_CONTEXT)
    try:
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return {"raw": raw}


def ensure_login_and_shop(expected_shop="", non_interactive=False, stage=""):
    ctx = get_context()
    is_login = bool(ctx.get("isLogin", False))
    shops = ctx.get("shops", []) if isinstance(ctx.get("shops", []), list) else []
    stage_text = f"[{stage}] " if stage else ""
    if not is_login:
        log("WARN", f"{stage_text}检测到未登录")
        if not wait_for_login_ready(non_interactive=non_interactive):
            return False
        ctx = get_context()
        shops = ctx.get("shops", []) if isinstance(ctx.get("shops", []), list) else []
    if shops:
        log("INFO", f"{stage_text}当前检测到店铺/账号信息：{shops}")
    else:
        log("WARN", f"{stage_text}未能识别店铺名称，请人工确认当前登录店铺是否正确")
    if expected_shop:
        hit = any(expected_shop in s for s in shops)
        if not hit:
            log("ERROR", f"{stage_text}店铺校验失败：期望包含「{expected_shop}」，当前识别={shops}")
            return False
        log("OK", f"{stage_text}店铺校验通过：{expected_shop}")
    return True


def switch_joined_tab(target_url):
    for i in range(1, 5):
        tab = evaluate(JS_SWITCH_TAB)
        if tab in ("SWITCHED", "ALREADY"):
            time.sleep(2)
            return True, tab
        log("WARN", f"页签切换第{i}次失败：{tab}")
        if i == 2:
            navigate(target_url)
            time.sleep(4)
        time.sleep(1.5)
    return False, tab


def parse_list_count(status):
    if not isinstance(status, str):
        return None
    for prefix in ("HAS:", "HAS_ITEMS:", "UNCERTAIN:"):
        if status.startswith(prefix):
            try:
                return int(status.split(":", 1)[1].strip())
            except Exception:
                return None
    if status == "EMPTY":
        return 0
    return None


# ── 主流程 ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="1688 批量退出哇噢定制")
    parser.add_argument("--count", type=int, default=500, help="最大退出数量（0=全部）")
    parser.add_argument("--target-url", type=str, default=TARGET_URL, help="目标页面 URL")
    parser.add_argument("--expected-shop", type=str, default=os.environ.get("EXPECTED_SHOP", ""), help="期望店铺名（可选，用于防串店）")
    parser.add_argument("--non-interactive", action="store_true", help="非交互模式，不等待 stdin")
    args = parser.parse_args()
    max_exit = 999999 if args.count == 0 else args.count
    target_url = args.target_url
    expected_shop = (args.expected_shop or "").strip()

    success = 0
    errors = 0

    print("\n" + "=" * 60)
    print("  🚀 1688 批量退出哇噢定制（BrowserWing Python 版）")
    print("=" * 60)
    print(f"  目标页面：{target_url}")
    print(f"  最大退出：{args.count if args.count > 0 else '全部'}")
    print(f"  操作间隔：{ACTION_DELAY} 秒")
    if expected_shop:
        print(f"  店铺校验：{expected_shop}")
    print("=" * 60 + "\n")

    # 1. 检查 BrowserWing 连通性
    result = evaluate(JS_CHECK_BW)
    if result != "BW_OK":
        log("ERROR", f"❌ BrowserWing 未在端口 {BW_PORT} 运行！")
        log("ERROR", f"   请先启动：cd /tmp && browserwing --port {BW_PORT}")
        return

    log("OK", f"✅ BrowserWing 连通（端口 {BW_PORT}）")

    # 2. 导航前登录与店铺检查（防串店）
    if not ensure_login_and_shop(expected_shop=expected_shop, non_interactive=args.non_interactive, stage="导航前"):
        log("ERROR", "❌ 登录/店铺校验失败，终止")
        return

    # 3. 导航到哇噢定制页面
    log("INFO", "导航到哇噢定制页面...")
    if not navigate(target_url):
        log("ERROR", "❌ 页面导航失败！")
        return
    time.sleep(PAGE_LOAD_WAIT)

    # 4. 导航后登录与店铺复核
    if not ensure_login_and_shop(expected_shop=expected_shop, non_interactive=args.non_interactive, stage="导航后"):
        log("ERROR", "❌ 登录/店铺校验失败，终止")
        return

    # 5. 验证码检测
    captcha = evaluate(JS_CHECK_CAPTCHA)
    if captcha != "CLEAN":
        if not wait_for_captcha_clear(non_interactive=args.non_interactive):
            log("ERROR", "❌ 验证码未清除，终止")
            return

    # 6. 切换到"已加入哇噢定制"标签（增强重试）
    log("INFO", "切换到「已加入哇噢定制」标签...")
    switched, tab = switch_joined_tab(target_url)
    if not switched:
        log("ERROR", f"❌ 标签切换失败：{tab}")
        log("ERROR", "   页面结构可能已变更，请联系开发者")
        return
    log("OK", f"✅ 已切换到「已加入哇噢定制」（{tab}）")
    time.sleep(3)

    # 7. 检查列表状态
    lst = evaluate(JS_CHECK_LIST)
    if lst == "EMPTY":
        log("OK", "🎉 列表为空，没有需要退出的商品！")
        return
    log("OK", f"✅ 检测到商品：{lst}")

    # 8. 开始批量退出
    print()
    log("INFO", "=" * 50)
    log("INFO", "  🔄 开始批量退出...")
    log("INFO", "=" * 50)

    while success < max_exit:
        current = success + 1

        # 检查列表
        lst = evaluate(JS_CHECK_LIST)
        log("INFO", f"列表状态: {lst}")

        # 每轮执行前先校验登录与店铺，避免会话过期或串店
        if not ensure_login_and_shop(expected_shop=expected_shop, non_interactive=args.non_interactive, stage=f"轮次{current}"):
            log("ERROR", "❌ 登录/店铺校验失败，终止")
            break

        if lst == "EMPTY" or lst.startswith("UNCERTAIN:0"):
            log("OK", "🎉 列表已空，所有商品已退出！")
            break

        remaining = lst.split(":")[1] if ":" in lst else "?"

        print()
        log("INFO", f"{'─' * 50}")
        log("INFO", f"📦 第 {current} 件（剩余 {remaining} 件）")

        before_count = parse_list_count(lst)

        # Step A: 语义直点（优先）→ Fiber hover（兜底）
        log("INFO", "  [a] 尝试语义定位退出入口...")
        direct = evaluate(JS_DIRECT_EXIT)
        if direct.startswith("DIRECT_EXIT_CLICKED") or direct == "EXIT_FROM_POPUP":
            log("OK", f"  ✅ 语义直点成功（{direct}）")
            ex = "CLICKED"
        else:
            log("WARN", f"  ⚠️ 语义直点未命中（{direct}），回退 hover 方案")
            hover = evaluate(JS_HOVER)
            if not hover.startswith("OK"):
                errors += 1
                log("ERROR", f"  ❌ 悬停失败：{hover}")
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    log("ERROR", f"❌ 连续 {MAX_CONSECUTIVE_ERRORS} 次错误，终止操作")
                    break
                time.sleep(ACTION_DELAY)
                continue
            log("OK", f"  ✅ 悬停成功（{hover}）")
            time.sleep(HOVER_WAIT)
            log("INFO", "  [b] 点击退出按钮...")
            ex = evaluate(JS_CLICK_EXIT)

        # Step B: 点击退出结果确认
        if ex != "CLICKED":
            errors += 1
            log("ERROR", f"  ❌ 退出按钮未找到：{ex}")
            evaluate(JS_DISMISS)
            if errors >= MAX_CONSECUTIVE_ERRORS:
                log("ERROR", f"❌ 连续 {MAX_CONSECUTIVE_ERRORS} 次错误，终止操作")
                break
            time.sleep(ACTION_DELAY)
            continue
        log("OK", "  ✅ 已点击退出按钮")
        time.sleep(CONFIRM_WAIT)

        # Step C: 确认
        log("INFO", "  [c] 确认退出...")
        cf = evaluate(JS_CONFIRM)
        confirmed = False
        if cf == "CONFIRMED":
            confirmed = True
            success += 1
            errors = 0
            log("OK", f"  ✅ 已确认退出第 {success} 件商品")
        else:
            log("WARN", f"  ⚠️ 确认弹窗操作异常：{cf}，重试中...")
            time.sleep(2)
            cf2 = evaluate(JS_CONFIRM)
            if cf2 == "CONFIRMED":
                confirmed = True
                success += 1
                errors = 0
                log("OK", f"  ✅ 重试确认成功！第 {success} 件")
            else:
                log("WARN", f"  ⚠️ 未发现确认弹窗：{cf2}，将按列表变化判断是否已退出")
                evaluate(JS_DISMISS)

        # 等待刷新
        log("INFO", "  [d] 等待列表刷新...")
        time.sleep(REFRESH_WAIT)

        # 兜底判定：即使无确认弹窗，只要列表减少也判成功
        after_status = evaluate(JS_CHECK_LIST)
        after_count = parse_list_count(after_status)
        if not confirmed and before_count is not None and after_count is not None and after_count < before_count:
            success += 1
            errors = 0
            log("OK", f"  ✅ 列表数量已下降（{before_count} -> {after_count}），判定退出成功，第 {success} 件")
        elif not confirmed:
            errors += 1
            log("ERROR", f"  ❌ 确认失败且列表未下降：before={before_count} after={after_count} status={after_status}")
            if errors >= MAX_CONSECUTIVE_ERRORS:
                log("ERROR", f"❌ 连续 {MAX_CONSECUTIVE_ERRORS} 次错误，终止操作")
                break

        # 验证码检测
        captcha = evaluate(JS_CHECK_CAPTCHA)
        if captcha != "CLEAN":
            if not wait_for_captcha_clear(non_interactive=args.non_interactive):
                log("ERROR", "❌ 验证码未清除，终止")
                break

        time.sleep(ACTION_DELAY)

    # 8. 最终结果
    print()
    log("INFO", "=" * 50)
    log("INFO", "  📊 批量退出完成！")
    log("INFO", "=" * 50)
    log("OK", f"  ✅ 成功退出：{success} 件商品")
    log("ERROR", f"  ❌ 错误次数：{errors}")
    log("INFO", "=" * 50)
    print()

    # 最终检查
    lst = evaluate(JS_CHECK_LIST)
    if lst == "EMPTY" or lst.startswith("UNCERTAIN:0"):
        log("OK", "🎉 所有商品已退出哇噢定制！")
    else:
        log("WARN", f"列表仍有商品：{lst}")
        log("WARN", "如需继续退出，可再次运行本脚本")
    print()


if __name__ == "__main__":
    main()
