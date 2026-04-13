#!/usr/bin/env python3
"""
1688 批量 AI 标题优化（BrowserWing REST API + Qwen AI）

三阶段工作流：
  Phase 1 扫描：遍历商品列表，提取所有商品的 offerId 和标题
  Phase 2 优化：调用 Qwen AI 批量生成优化标题
  Phase 3 执行：展示优化对照表，用户确认后逐个进入编辑页修改并提交

用法：
  python3 batch_title_optimizer.py                    # 完整三阶段流程
  python3 batch_title_optimizer.py --scan-only        # 只扫描导出 CSV，不优化不执行
  python3 batch_title_optimizer.py --count 20         # 只处理前 20 个商品
  python3 batch_title_optimizer.py --keyword 解压球   # 先搜索关键词再扫描
  python3 batch_title_optimizer.py --import titles.csv  # 导入已有优化结果，直接执行

前置条件：
  1. BrowserWing 已启动（cd /tmp && browserwing --port 8080）
  2. 已在 BrowserWing 控制的浏览器中登录 1688
  3. Python requests 库已安装

跨平台：
  - macOS / Linux: python3 batch_title_optimizer.py
  - Windows:       python batch_title_optimizer.py
"""
import json, time, sys, os, argparse, csv, re
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────────────────────────
BW_PORT = int(os.environ.get("BW_PORT", "8080"))
BW_BASE = f"http://localhost:{BW_PORT}/api/v1/executor"
LIST_URL = "https://offer.1688.com/offer/manage.htm?show_type=valid"

# Qwen AI 配置
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "sk-37d3c9f6420e4318824c586d0befb132")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-plus")
QWEN_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 时间配置
PAGE_LOAD_WAIT = 5
EDIT_LOAD_WAIT = 5
SUBMIT_WAIT = 4
ACTION_DELAY = 3
PAGE_CHANGE_WAIT = 3
API_DELAY = 0.5        # Qwen API 调用间隔（秒）
MAX_CONSECUTIVE_ERRORS = 5

# CSV 文件名
SCAN_CSV = "title_scan_{ts}.csv"
RESULT_CSV = "title_optimized_{ts}.csv"
LOG_FILE = "title_optimizer_{ts}.log"


# ── 工具函数 ──────────────────────────────────────────────────────────────
def log(level, msg):
    colors = {"INFO": "\033[0;34m", "OK": "\033[0;32m", "WARN": "\033[0;33m",
              "ERROR": "\033[0;31m", "AI": "\033[0;35m"}
    color = colors.get(level, "\033[0m")
    ts = time.strftime("%H:%M:%S")
    print(f"{color}[{ts}] [{level}] {msg}\033[0m", flush=True)


def log_to_file(log_path, msg):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


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


def navigate(url, wait="load"):
    try:
        r = requests.post(f"{BW_BASE}/navigate",
                         json={"url": url, "wait_until": wait, "timeout": 30},
                         timeout=40)
        return r.json().get("success", False)
    except Exception as e:
        log("ERROR", f"导航失败: {e}")
        return False


def screenshot(path):
    try:
        requests.post(f"{BW_BASE}/screenshot", json={"path": path}, timeout=10)
    except:
        pass


def check_captcha():
    """返回 True 表示检测到验证码"""
    r = evaluate(JS_CHECK_CAPTCHA)
    return r != "CLEAN"


def wait_for_captcha(log_path):
    log("WARN", "⚠️  检测到验证码！请在 BrowserWing 浏览器窗口中手动完成验证...")
    print("\n" + "═" * 55)
    print("  🛡️  验证码已触发，请在浏览器窗口中手动处理")
    print("  处理完成后按 [Enter] 继续...")
    print("═" * 55)
    input()
    if not check_captcha():
        log("OK", "✅ 验证码已清除，继续执行")
    else:
        log("WARN", "仍有验证码元素，继续尝试...")


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

JS_SEARCH = """() => {
  var input = document.querySelector('#keyword');
  if (!input) return 'INPUT_NOT_FOUND';
  var nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value').set;
  nativeSetter.call(input, 'SEARCH_KEYWORD');
  input.dispatchEvent(new Event('input', {bubbles: true}));
  input.dispatchEvent(new Event('change', {bubbles: true}));
  input.dispatchEvent(new Event('compositionend', {bubbles: true}));
  var btn = document.querySelector('button.simple-search__submit-btn');
  if (btn) btn.click();
  return 'SEARCH_DONE';
}"""

JS_EXTRACT_PRODUCTS = """() => {
  var links = document.querySelectorAll('a');
  var items = [];
  var seen = {};
  for (var i = 0; i < links.length; i++) {
    var href = links[i].href || '';
    if (href.indexOf('detail.1688.com/offer/') >= 0) {
      var match = href.match(/offer\\/(\\d+)/);
      var offerId = match ? match[1] : '';
      var title = links[i].innerText.trim();
      if (offerId && title.length > 5 && !seen[offerId]) {
        seen[offerId] = true;
        items.push({offerId: offerId, title: title.substring(0, 80)});
      }
    }
  }
  return JSON.stringify(items);
}"""

JS_GET_PAGE_INFO = """() => {
  var info = document.querySelector('.next-pagination-display');
  return info ? info.innerText.trim() : 'NO_PAGINATION';
}"""

JS_CLICK_NEXT_PAGE = """() => {
  var btn = document.querySelector('button.next-pagination-item.next');
  if (!btn) return 'NO_PAGINATION';
  if (btn.disabled) return 'LAST_PAGE';
  btn.click();
  return 'NEXT_CLICKED';
}"""

JS_EXTRACT_EDIT_TITLE = """() => {
  var inputs = document.querySelectorAll('input');
  for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    if (inp.value && inp.value.length > 8 && inp.type === 'text') {
      if (inp.placeholder && inp.placeholder.indexOf('建议使用') >= 0) {
        return inp.value;
      }
    }
  }
  return 'TITLE_NOT_FOUND';
}"""

JS_FILL_TITLE = """() => {
  var inputs = document.querySelectorAll('input');
  for (var i = 0; i < inputs.length; i++) {
    var inp = inputs[i];
    if (inp.value === 'ORIGINAL_TITLE' && inp.type === 'text') {
      var nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value').set;
      nativeSetter.call(inp, 'NEW_TITLE');
      inp.dispatchEvent(new Event('input', {bubbles: true}));
      inp.dispatchEvent(new Event('change', {bubbles: true}));
      inp.dispatchEvent(new Event('compositionend', {bubbles: true}));
      return 'FILLED';
    }
  }
  return 'INPUT_NOT_FOUND';
}"""

JS_SUBMIT = """() => {
  window.scrollTo(0, document.body.scrollHeight);
  var btn = document.querySelector('button.submit-buttom-action');
  if (!btn) return 'BTN_NOT_FOUND';
  btn.click();
  return 'SUBMITTED';
}"""

JS_CHECK_SUBMIT_RESULT = """() => {
  var text = document.body ? document.body.innerText.substring(0, 500) : '';
  if (text.indexOf('发布成功') >= 0) return 'SUCCESS';
  if (text.indexOf('审核') >= 0) return 'REVIEWING';
  if (text.indexOf('失败') >= 0 || text.indexOf('错误') >= 0) return 'FAILED:' + text.substring(0, 200);
  return 'UNKNOWN:' + text.substring(0, 100);
}"""


# ── Phase 1: 扫描商品 ───────────────────────────────────────────────────
def scan_products(keyword=None, max_count=0):
    """扫描商品列表，返回 [{offerId, title}, ...]"""
    products = []
    page = 0
    consecutive_empty = 0

    log("INFO", "导航到商品管理列表...")
    if not navigate(LIST_URL):
        log("ERROR", "❌ 商品列表页导航失败！")
        return []

    time.sleep(PAGE_LOAD_WAIT)

    # 登录检测
    page_text = evaluate(JS_CHECK_LOGIN)
    if "登录" in page_text or "请登录" in page_text:
        log("ERROR", "❌ 未登录 1688！请先在 BrowserWing 浏览器中登录。")
        print("\n  🔐 请在浏览器中登录 1688 后按 [Enter] 继续...")
        input()

    # 验证码检测
    if check_captcha():
        wait_for_captcha("")

    # 搜索关键词（可选）
    if keyword:
        log("INFO", f"搜索关键词: {keyword}")
        search_js = JS_SEARCH.replace("SEARCH_KEYWORD", keyword)
        r = evaluate(search_js)
        if "NOT_FOUND" in r:
            log("ERROR", f"❌ 搜索框未找到: {r}")
            return []
        log("OK", "搜索已执行")
        time.sleep(PAGE_CHANGE_WAIT)
        if check_captcha():
            wait_for_captcha("")

    # 遍历所有页面
    while True:
        page += 1
        log("INFO", f"扫描第 {page} 页...")

        # 提取当前页商品
        r = evaluate(JS_EXTRACT_PRODUCTS)
        try:
            items = json.loads(r)
        except:
            log("WARN", f"页面数据解析异常: {r[:100]}")
            items = []

        if not items:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                log("WARN", "连续 2 页无数据，停止扫描")
                break
        else:
            consecutive_empty = 0

        products.extend(items)
        log("OK", f"  第 {page} 页找到 {len(items)} 个商品（累计 {len(products)} 个）")

        # 检查数量限制
        if max_count > 0 and len(products) >= max_count:
            products = products[:max_count]
            log("OK", f"已达到数量上限 {max_count}，停止扫描")
            break

        # 翻页
        page_info = evaluate(JS_GET_PAGE_INFO)
        next_r = evaluate(JS_CLICK_NEXT_PAGE)
        if next_r == "LAST_PAGE" or next_r == "NO_PAGINATION":
            log("OK", f"已到最后一页（{page_info}）")
            break
        if "CLICKED" not in next_r:
            log("WARN", f"翻页失败: {next_r}")
            break

        time.sleep(PAGE_CHANGE_WAIT)

        # 翻页后验证码检测
        if check_captcha():
            wait_for_captcha("")

    # 去重
    seen = set()
    unique = []
    for p in products:
        if p["offerId"] not in seen:
            seen.add(p["offerId"])
            unique.append(p)

    log("OK", f"✅ 扫描完成：共 {len(unique)} 个商品（去重后）")
    return unique


# ── Phase 2: AI 优化标题 ───────────────────────────────────────────────
def optimize_titles(products, log_path):
    """调用 Qwen AI 批量生成优化标题"""
    results = []
    total = len(products)

    log("AI", f"开始 AI 标题优化（共 {total} 个商品，模型: {QWEN_MODEL}）...")
    print()

    for i, p in enumerate(products):
        idx = i + 1
        original = p["title"]

        # 进度显示
        log("AI", f"[{idx}/{total}] 优化: {original[:30]}...")

        # 调用 Qwen API
        prompt = f"""你是1688商品标题SEO优化专家。请基于以下原标题生成优化标题。

原标题：{original}

优化要求：
1. 关键词前置，核心搜索词放最前
2. 用空格分隔关键词组
3. 覆盖买家可能的搜索词和关联词
4. 去除冗余修饰
5. 增加使用场景词
6. 避免极限词（最、第一等）
7. 标题不超过60字符
8. 保留原标题中的核心商品属性和材质信息

只输出优化后的标题，不要输出任何解释或说明。"""

        try:
            r = requests.post(
                QWEN_URL,
                headers={
                    "Authorization": f"Bearer {QWEN_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": QWEN_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 100
                },
                timeout=30
            )
            d = r.json()
            optimized = d["choices"][0]["message"]["content"].strip()

            # 清理可能的前缀
            for prefix in ["优化标题：", "优化标题:", "标题：", "标题:"]:
                if optimized.startswith(prefix):
                    optimized = optimized[len(prefix):].strip()

            # 长度检查
            if len(optimized) > 60:
                optimized = optimized[:60]
                log("WARN", f"  ⚠️ 标题超长，已截断至 60 字符")

            log("OK", f"  ✅ {optimized[:40]}...")

        except Exception as e:
            log("ERROR", f"  ❌ AI 调用失败: {e}")
            optimized = ""

        result = {
            "offerId": p["offerId"],
            "originalTitle": original,
            "optimizedTitle": optimized,
            "status": ""
        }
        results.append(result)
        log_to_file(log_path, f"AI [{idx}/{total}] {original[:30]} -> {optimized[:40]}")

        time.sleep(API_DELAY)

    # 统计有效优化数量
    valid = sum(1 for r in results if r["optimizedTitle"])
    log("OK", f"\n✅ AI 优化完成：{valid}/{total} 个标题生成成功")
    return results


# ── Phase 3: 预览确认 ──────────────────────────────────────────────────
def preview_and_confirm(results):
    """展示优化对照表，返回用户确认的结果列表"""
    print("\n" + "=" * 80)
    print("  📊 标题优化对照表")
    print("=" * 80)

    valid = [r for r in results if r["optimizedTitle"]]
    invalid = [r for r in results if not r["optimizedTitle"]]

    if not valid:
        log("WARN", "没有可用的优化标题！")
        return []

    for i, r in enumerate(valid):
        idx = i + 1
        orig = r["originalTitle"]
        opt = r["optimizedTitle"]
        mark = "✅" if orig != opt else "➡️"

        # 判断是否需要修改
        r["status"] = "pending"

        print(f"\n{mark} #{idx} [{r['offerId']}]")
        print(f"  原: {orig}")
        print(f"  新: {opt}")
        if orig == opt:
            print(f"  （无变化，将跳过）")
            r["status"] = "skip"

    # 跳过的不计入
    to_apply = [r for r in valid if r["status"] == "pending"]

    if invalid:
        print(f"\n⚠️  {len(invalid)} 个商品 AI 优化失败，已跳过")

    print(f"\n{'─' * 80}")
    print(f"  总计: {len(results)} 个商品")
    print(f"  将修改: {len(to_apply)} 个")
    print(f"  无变化: {len(valid) - len(to_apply)} 个")
    print(f"  失败: {len(invalid)} 个")
    print(f"{'─' * 80}")

    if not to_apply:
        log("OK", "🎉 没有需要修改的商品")
        return []

    print(f"\n⚠️  即将修改 {len(to_apply)} 个商品标题，是否继续？")
    print("  输入 y 确认 / n 取消 / 数字 跳过对应编号的商品")
    choice = input("\n  请选择 [y/n/编号]: ").strip().lower()

    if choice == "n":
        log("INFO", "已取消操作")
        return []

    if choice == "y":
        return to_apply

    # 处理跳过编号
    try:
        skip_num = int(choice)
        to_apply = [r for i, r in enumerate(to_apply) if i + 1 != skip_num]
        log("INFO", f"已跳过第 {skip_num} 个商品，剩余 {len(to_apply)} 个")
        if to_apply:
            print("  继续执行？[y/n]: ", end="")
            if input().strip().lower() == "y":
                return to_apply
        return []
    except ValueError:
        log("WARN", "无效输入，已取消")
        return []


# ── Phase 4: 执行修改 ──────────────────────────────────────────────────
def apply_changes(results, log_path):
    """逐个进入编辑页修改标题"""
    success = 0
    failed = 0
    errors = 0

    for i, r in enumerate(results):
        idx = i + 1
        offer_id = r["offerId"]
        original = r["originalTitle"]
        optimized = r["optimizedTitle"]
        edit_url = f"https://offer-new.1688.com/popular/publish.htm?id={offer_id}&operator=edit"

        print()
        log("INFO", f"{'─' * 50}")
        log("INFO", f"📦 [{idx}/{len(results)}] 商品 {offer_id}")

        # Step A: 导航到编辑页
        log("INFO", "  [a] 进入编辑页...")
        if not navigate(edit_url):
            failed += 1
            errors += 1
            log("ERROR", "  ❌ 编辑页导航失败")
            if errors >= MAX_CONSECUTIVE_ERRORS:
                log("ERROR", f"连续 {MAX_CONSECUTIVE_ERRORS} 次错误，终止")
                break
            continue
        time.sleep(EDIT_LOAD_WAIT)

        # 验证码检测
        if check_captcha():
            wait_for_captcha(log_path)

        # Step B: 提取当前标题
        log("INFO", "  [b] 提取当前标题...")
        current = evaluate(JS_EXTRACT_EDIT_TITLE)
        if current == "TITLE_NOT_FOUND":
            log("WARN", "  ⚠️ 未找到标题输入框，可能页面未加载完成")
            time.sleep(3)
            current = evaluate(JS_EXTRACT_EDIT_TITLE)
            if current == "TITLE_NOT_FOUND":
                failed += 1
                errors += 1
                log("ERROR", "  ❌ 标题输入框仍然未找到")
                continue

        # 检查标题是否匹配
        if current != original:
            log("WARN", f"  ⚠️ 标题已变更！")
            log("INFO", f"     扫描时: {original[:40]}...")
            log("INFO", f"     当前值: {current[:40]}...")
            log("WARN", "  ⚠️ 使用当前值作为基准继续修改")

        log("OK", f"  ✅ 当前标题: {current[:40]}...")

        # Step C: 填入新标题
        log("INFO", "  [c] 填入优化标题...")
        fill_js = JS_FILL_TITLE.replace("ORIGINAL_TITLE", current).replace("NEW_TITLE", optimized)
        fill_r = evaluate(fill_js)
        if fill_r != "FILLED":
            failed += 1
            errors += 1
            log("ERROR", f"  ❌ 填入失败: {fill_r}")
            continue
        log("OK", f"  ✅ 已填入: {optimized[:40]}...")

        # Step D: 提交
        log("INFO", "  [d] 提交保存...")
        sub_r = evaluate(JS_SUBMIT)
        if sub_r != "SUBMITTED":
            failed += 1
            errors += 1
            log("ERROR", f"  ❌ 提交按钮点击失败: {sub_r}")
            continue
        log("OK", "  ✅ 已点击提交")
        time.sleep(SUBMIT_WAIT)

        # Step E: 检查结果
        result = evaluate(JS_CHECK_SUBMIT_RESULT)
        if "SUCCESS" in result or "REVIEW" in result:
            success += 1
            errors = 0
            label = "发布成功" if "SUCCESS" in result else "进入审核"
            log("OK", f"  ✅ {label}！第 {success} 个商品修改完成")
        else:
            failed += 1
            errors += 1
            log("ERROR", f"  ❌ 提交结果异常: {result[:100]}")

        log_to_file(log_path, f"APPLY [{idx}/{len(results)}] {offer_id}: "
                            f"{'OK' if 'SUCCESS' in result or 'REVIEW' in result else 'FAIL'} "
                            f"| {optimized[:30]}")

        time.sleep(ACTION_DELAY)

        # 验证码检测
        if check_captcha():
            wait_for_captcha(log_path)

    return success, failed


# ── CSV 导入导出 ───────────────────────────────────────────────────────
def save_csv(results, filepath, mode="scan"):
    """保存结果到 CSV"""
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if mode == "scan":
            writer.writerow(["offerId", "title"])
            for r in results:
                writer.writerow([r["offerId"], r["title"]])
        else:
            writer.writerow(["offerId", "originalTitle", "optimizedTitle", "status"])
            for r in results:
                writer.writerow([r["offerId"], r["originalTitle"],
                               r.get("optimizedTitle", ""), r.get("status", "")])
    log("OK", f"💾 CSV 已保存: {filepath}")


def import_csv(filepath):
    """从 CSV 导入优化结果"""
    results = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append({
                "offerId": row.get("offerId", ""),
                "originalTitle": row.get("originalTitle", row.get("title", "")),
                "optimizedTitle": row.get("optimizedTitle", ""),
                "status": row.get("status", "pending")
            })
    # 过滤有效行
    valid = [r for r in results if r["offerId"] and r["optimizedTitle"]]
    log("OK", f"📂 导入 {len(results)} 条记录，其中 {len(valid)} 条有效")
    return valid


# ── 主函数 ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="1688 批量 AI 标题优化")
    parser.add_argument("--count", type=int, default=0, help="最大处理数量（0=全部）")
    parser.add_argument("--keyword", type=str, default="", help="搜索关键词（可选）")
    parser.add_argument("--scan-only", action="store_true", help="只扫描导出，不优化不执行")
    parser.add_argument("--import", dest="import_csv", type=str, default="",
                       help="导入已有优化结果 CSV，直接执行修改")
    parser.add_argument("--apply-only", action="store_true",
                       help="与 --import 配合，只执行不重新优化")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", LOG_FILE.format(ts=ts))
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    print("\n" + "=" * 65)
    print("  🚀 1688 批量 AI 标题优化（BrowserWing + Qwen）")
    print("=" * 65)
    print(f"  BrowserWing: localhost:{BW_PORT}")
    print(f"  AI 模型: {QWEN_MODEL}")
    print(f"  最大数量: {args.count if args.count > 0 else '全部'}")
    if args.keyword:
        print(f"  搜索关键词: {args.keyword}")
    print("=" * 65 + "\n")

    # 0. 检查 BrowserWing
    r = evaluate(JS_CHECK_BW)
    if r != "BW_OK":
        log("ERROR", f"❌ BrowserWing 未在端口 {BW_PORT} 运行！")
        log("ERROR", f"   请先启动：cd /tmp && browserwing --port {BW_PORT}")
        return

    # ── 导入模式 ──
    if args.import_csv:
        if not os.path.exists(args.import_csv):
            log("ERROR", f"❌ CSV 文件不存在: {args.import_csv}")
            return
        results = import_csv(args.import_csv)
        if not results:
            log("ERROR", "没有有效的优化记录")
            return

        # 预览确认
        to_apply = preview_and_confirm(results)
        if not to_apply:
            return

        # 执行修改
        success, failed = apply_changes(to_apply, log_path)

        print("\n" + "=" * 50)
        log("OK", f"  ✅ 修改成功: {success}")
        log("ERROR", f"  ❌ 修改失败: {failed}")
        print("=" * 50)
        return

    # ── Phase 1: 扫描 ──
    products = scan_products(keyword=args.keyword or None, max_count=args.count)

    if not products:
        log("WARN", "没有找到商品")
        return

    # 导出扫描结果
    scan_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            SCAN_CSV.format(ts=ts))
    save_csv(products, scan_path, mode="scan")

    if args.scan_only:
        log("OK", f"🔍 扫描完成，结果已保存到: {scan_path}")
        log("INFO", "提示：可在 Excel 中编辑优化标题后，使用 --import 导入执行")
        return

    # ── Phase 2: AI 优化 ──
    results = optimize_titles(products, log_path)

    # 导出优化结果
    result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              RESULT_CSV.format(ts=ts))
    save_csv(results, result_path, mode="optimized")

    # ── Phase 3: 预览确认 ──
    to_apply = preview_and_confirm(results)
    if not to_apply:
        return

    # ── Phase 4: 执行修改 ──
    success, failed = apply_changes(to_apply, log_path)

    # 最终报告
    print("\n" + "=" * 50)
    log("INFO", "  📊 批量标题优化完成！")
    log("OK", f"  ✅ 修改成功: {success}")
    log("ERROR", f"  ❌ 修改失败: {failed}")
    log("INFO", f"  📄 扫描 CSV: {scan_path}")
    log("INFO", f"  📄 结果 CSV: {result_path}")
    log("INFO", f"  📄 执行日志: {log_path}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
