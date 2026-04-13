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
TARGET_URL = "https://sale.1688.com/factory/ossdql9d.html"

ACTION_DELAY = 2       # 每次退出后等待（秒）
HOVER_WAIT = 1         # hover 后等待弹出菜单（秒）
CONFIRM_WAIT = 2       # 点击退出后等待确认弹窗（秒）
REFRESH_WAIT = 4       # 退出后等待列表刷新（秒）
PAGE_LOAD_WAIT = 8     # 页面加载等待（秒）
MAX_CONSECUTIVE_ERRORS = 5


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


# ── JS 代码片段 ──────────────────────────────────────────────────────────

JS_CHECK_BW = "() => { return 'BW_OK'; }"

JS_CHECK_LOGIN = """() => {
  return document.body ? document.body.innerText.substring(0, 200) : 'NO_BODY';
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
  var tabs = document.querySelectorAll('[role=tab], .next-tabs-tab, .ant-tabs-tab');
  for (var i = 0; i < tabs.length; i++) {
    if (tabs[i].innerText.trim() === '已加入哇噢定制' && tabs[i].offsetParent !== null) {
      tabs[i].click();
      return 'SWITCHED';
    }
  }
  return 'TAB_NOT_FOUND';
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

JS_HOVER = """() => {
  var imgs = document.querySelectorAll('img[style*="cursor"]');
  var target = null;
  for (var i = 0; i < imgs.length; i++) {
    var r = imgs[i].getBoundingClientRect();
    if (r.top > 500 && r.left > 1900 && r.left < 2100) {
      target = imgs[i];
      break;
    }
  }
  if (!target) return 'ICON_NOT_FOUND';
  var fk = Object.keys(target).find(function(k) { return k.indexOf('__reactFiber$') === 0; });
  if (!fk) return 'NO_FIBER';
  var el = target[fk];
  var depth = 0;
  while (el && depth < 10) {
    var p = el.memoizedProps || el.pendingProps || {};
    if (p.onMouseEnter) {
      p.onMouseEnter({
        currentTarget: target, target: target, type: 'mouseenter',
        clientX: target.getBoundingClientRect().left + 8,
        clientY: target.getBoundingClientRect().top + 8
      });
      return 'OK:depth=' + depth + ':top=' + Math.round(target.getBoundingClientRect().top);
    }
    el = el.return;
    depth++;
  }
  return 'NO_ENTER';
}"""

JS_CLICK_EXIT = """() => {
  var balloon = document.querySelector('.next-balloon');
  if (!balloon) return 'NO_BALLOON';
  var btn = balloon.querySelector('.my-ant-btn-primary');
  if (!btn) return 'NO_BTN';
  btn.click();
  return 'CLICKED';
}"""

JS_CONFIRM = """() => {
  var dialog = document.querySelector('.next-dialog');
  if (!dialog) return 'NO_DIALOG';
  var btn = dialog.querySelector('.next-btn-primary');
  if (!btn) return 'NO_BTN';
  btn.click();
  return 'CONFIRMED';
}"""

JS_DISMISS = """() => {
  var b = document.querySelector('.next-balloon');
  if (b) b.style.display = 'none';
  var d = document.querySelector('.next-dialog');
  if (d) d.style.display = 'none';
  return 'dismissed';
}"""


# ── 验证码处理 ──────────────────────────────────────────────────────────
def wait_for_captcha_clear():
    log("WARN", "⚠️  检测到验证码！请在 BrowserWing 浏览器窗口中手动完成验证...")
    print("\n" + "═" * 55)
    print("  🛡️  验证码已触发，请在浏览器窗口中手动处理")
    print("  处理完成后按 [Enter] 继续...")
    print("═" * 55)
    input()
    status = evaluate(JS_CHECK_CAPTCHA)
    if status == "CLEAN":
        log("OK", "✅ 验证码已清除，继续执行")
    else:
        log("WARN", f"仍然检测到验证码元素：{status}，继续尝试...")


# ── 主流程 ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="1688 批量退出哇噢定制")
    parser.add_argument("--count", type=int, default=500, help="最大退出数量（0=全部）")
    args = parser.parse_args()
    max_exit = 999999 if args.count == 0 else args.count

    success = 0
    errors = 0

    print("\n" + "=" * 60)
    print("  🚀 1688 批量退出哇噢定制（BrowserWing Python 版）")
    print("=" * 60)
    print(f"  目标页面：{TARGET_URL}")
    print(f"  最大退出：{args.count if args.count > 0 else '全部'}")
    print(f"  操作间隔：{ACTION_DELAY} 秒")
    print("=" * 60 + "\n")

    # 1. 检查 BrowserWing 连通性
    result = evaluate(JS_CHECK_BW)
    if result != "BW_OK":
        log("ERROR", f"❌ BrowserWing 未在端口 {BW_PORT} 运行！")
        log("ERROR", f"   请先启动：cd /tmp && browserwing --port {BW_PORT}")
        return

    log("OK", f"✅ BrowserWing 连通（端口 {BW_PORT}）")

    # 2. 导航到哇噢定制页面
    log("INFO", "导航到哇噢定制页面...")
    if not navigate(TARGET_URL):
        log("ERROR", "❌ 页面导航失败！")
        return
    time.sleep(PAGE_LOAD_WAIT)

    # 3. 检查登录状态
    page_text = evaluate(JS_CHECK_LOGIN)
    if "登录" in page_text or "请登录" in page_text or page_text == "NO_BODY":
        log("ERROR", "❌ 未登录 1688！请先在 BrowserWing 浏览器中登录。")
        print("\n" + "═" * 55)
        print("  🔐 请在 BrowserWing 控制的浏览器中登录 1688")
        print("  登录完成后按 [Enter] 继续...")
        print("═" * 55)
        input()

    # 4. 验证码检测
    captcha = evaluate(JS_CHECK_CAPTCHA)
    if captcha != "CLEAN":
        wait_for_captcha_clear()

    # 5. 切换到"已加入哇噢定制"标签
    log("INFO", "切换到「已加入哇噢定制」标签...")
    tab = evaluate(JS_SWITCH_TAB)
    if tab != "SWITCHED":
        log("ERROR", f"❌ 标签切换失败：{tab}")
        log("ERROR", "   页面结构可能已变更，请联系开发者")
        return
    log("OK", "✅ 已切换到「已加入哇噢定制」")
    time.sleep(5)

    # 6. 检查列表状态
    lst = evaluate(JS_CHECK_LIST)
    if lst == "EMPTY":
        log("OK", "🎉 列表为空，没有需要退出的商品！")
        return
    log("OK", f"✅ 检测到商品：{lst}")

    # 7. 开始批量退出
    print()
    log("INFO", "=" * 50)
    log("INFO", "  🔄 开始批量退出...")
    log("INFO", "=" * 50)

    while success < max_exit:
        # 检查列表
        lst = evaluate(JS_CHECK_LIST)
        log("INFO", f"列表状态: {lst}")

        if lst == "EMPTY" or lst.startswith("UNCERTAIN:0"):
            log("OK", "🎉 列表已空，所有商品已退出！")
            break

        remaining = lst.split(":")[1] if ":" in lst else "?"
        current = success + 1

        print()
        log("INFO", f"{'─' * 50}")
        log("INFO", f"📦 第 {current} 件（剩余 {remaining} 件）")

        # Step A: Hover
        log("INFO", "  [a] 悬停问号图标...")
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

        # Step B: 点击退出
        log("INFO", "  [b] 点击退出按钮...")
        ex = evaluate(JS_CLICK_EXIT)
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
        if cf == "CONFIRMED":
            success += 1
            errors = 0
            log("OK", f"  ✅ 已确认退出第 {success} 件商品")
        else:
            log("WARN", f"  ⚠️ 确认弹窗操作异常：{cf}，重试中...")
            time.sleep(2)
            cf2 = evaluate(JS_CONFIRM)
            if cf2 == "CONFIRMED":
                success += 1
                errors = 0
                log("OK", f"  ✅ 重试确认成功！第 {success} 件")
            else:
                errors += 1
                evaluate(JS_DISMISS)
                log("ERROR", f"  ❌ 确认失败：{cf2}")
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    log("ERROR", f"❌ 连续 {MAX_CONSECUTIVE_ERRORS} 次错误，终止操作")
                    break

        # 等待刷新
        log("INFO", "  [d] 等待列表刷新...")
        time.sleep(REFRESH_WAIT)

        # 验证码检测
        captcha = evaluate(JS_CHECK_CAPTCHA)
        if captcha != "CLEAN":
            wait_for_captcha_clear()

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
