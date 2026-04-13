#!/usr/bin/env python3
"""
1688 批量开启官方定制项（BrowserWing REST API）

功能：
  1. 进入 1688 商家后台
  2. 打开「找工厂 -> 设置官方定制项」
  3. 检查「待设置」列表并循环处理
  4. 逐个类目补齐「包装定制」四个固定选项
  5. 确认报价并保存当前类目定制项

运行方式：
  python3 batch_official_customize_enable.py
  python3 batch_official_customize_enable.py --max-rounds 50 --delay 2

前置条件：
  1. BrowserWing 已启动（browserwing --port 8080）
  2. 已在 BrowserWing 控制的浏览器中登录 1688
  3. requests 已安装
"""

import argparse
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

import requests


SHOP_BACKEND_URL = "https://work.1688.com/"
TARGET_OPTIONS = [
    {"label": "手工贴标 +0.3 3件起定", "keyword": "手工贴标", "price": "+0.3"},
    {"label": "塑封 +0.2 3件起定", "keyword": "塑封", "price": "+0.2"},
    {"label": "OPP袋 +0.2 3件起定", "keyword": "opp袋", "price": "+0.2"},
    {"label": "气泡袋 +0.25 3件起定", "keyword": "气泡袋", "price": "+0.25"},
]

ENTRY_WAIT = 5
TAB_WAIT = 1.5
PICKER_WAIT = 2
SAVE_WAIT = 2.5
ROUND_RESET_WAIT = 3

COMMON_JS = r"""
function bwNorm(text) {
  return (text || "").replace(/\u3000/g, " ").replace(/\s+/g, " ").trim();
}
function bwNormKey(text) {
  return bwNorm(text).toLowerCase();
}
function bwVisible(el) {
  if (!el) return false;
  var style = window.getComputedStyle(el);
  if (!style || style.display === "none" || style.visibility === "hidden") return false;
  var rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
function bwText(el) {
  return bwNorm(el && (el.innerText || el.textContent || ""));
}
function bwClickable(el) {
  if (!el) return null;
  return el.closest("a,button,[role=button],.next-btn,.ant-btn,.next-tabs-tab,.ant-tabs-tab,[role=tab]") || el;
}
function bwMouseClick(el) {
  if (!el) return false;
  try { el.scrollIntoView({behavior: "auto", block: "center", inline: "center"}); } catch (e) {}
  try { el.click(); return true; } catch (e1) {}
  try {
    ["mouseover", "mousedown", "mouseup", "click"].forEach(function(type) {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    });
    return true;
  } catch (e2) {}
  return false;
}
function bwCallReactHandler(el, names, eventFactory) {
  if (!el) return "";
  var propKeys = Object.keys(el).filter(function(k) {
    return k.indexOf("__reactProps$") === 0 || k.indexOf("__reactEventHandlers$") === 0;
  });
  for (var i = 0; i < propKeys.length; i++) {
    var props = el[propKeys[i]] || {};
    for (var j = 0; j < names.length; j++) {
      var name = names[j];
      if (typeof props[name] === "function") {
        try {
          props[name](eventFactory ? eventFactory(el) : { currentTarget: el, target: el });
          return name;
        } catch (e) {}
      }
    }
  }
  return "";
}
function bwCollectTabs() {
  var selectors = [
    "[role=tab]",
    ".next-tabs-tab",
    ".ant-tabs-tab",
    ".next-menu-item",
    ".category-tab",
    ".tab-item"
  ];
  var seen = {};
  var tabs = [];
  selectors.forEach(function(selector) {
    document.querySelectorAll(selector).forEach(function(el) {
      var text = bwText(el);
      if (!text || !bwVisible(el)) return;
      if (text === "待设置" || text === "已设置") return;
      if (seen[text]) return;
      seen[text] = true;
      tabs.push(text);
    });
  });
  return tabs;
}
function bwFindVisibleByText(selectors, targets, exact) {
  var list = [];
  selectors.forEach(function(selector) {
    document.querySelectorAll(selector).forEach(function(el) {
      if (!bwVisible(el)) return;
      var text = bwText(el);
      if (!text) return;
      targets.forEach(function(target) {
        var ok = exact ? text === target : text.indexOf(target) >= 0;
        if (ok) list.push({ el: el, text: text, target: target });
      });
    });
  });
  list.sort(function(a, b) { return a.text.length - b.text.length; });
  return list;
}
function bwFindPackagingField() {
  var root = document.querySelector(".ant-tabs-tabpane-active,[class*=tabpane-active]") || document.body;
  var labels = [];
  root.querySelectorAll("label,span,div,p,strong").forEach(function(el) {
    if (!bwVisible(el)) return;
    if (bwText(el) === "包装定制") labels.push({ el: el });
  });
  if (labels.length === 0) return null;
  var label = labels[0].el;
  var container = label.closest("[class*=settingItem],.setting-item,.next-form-item,.ant-form-item") || label.parentElement || label;
  var selectRoot = container.querySelector(".ant-select,.next-select,[role=combobox],.next-tag-list");
  if (!selectRoot) {
    var node = label;
    for (var i = 0; i < 6 && node; i++) {
      if (node.querySelector(".ant-select,.next-select,[role=combobox],.next-tag-list")) {
        container = node;
        selectRoot = node.querySelector(".ant-select,.next-select,[role=combobox],.next-tag-list");
        break;
      }
      node = node.parentElement;
    }
  }
  if (!selectRoot) return null;
  var input = container.querySelector("input.ant-select-selection-search-input,input") ||
    selectRoot.querySelector("input.ant-select-selection-search-input,input");
  return { root: root, label: label, container: container, selectRoot: selectRoot, input: input };
}
function bwVisiblePickerScopes() {
  return Array.from(document.querySelectorAll(".ant-select-dropdown,[role=listbox]")).filter(function(el) {
    return bwVisible(el);
  });
}
function bwResolvePickerScope(listId) {
  var list = listId ? document.getElementById(listId) : null;
  var scope = null;
  if (list) scope = list.closest(".ant-select-dropdown,[role=listbox]") || list;
  if (scope && bwVisible(scope)) return scope;
  var visibleScopes = bwVisiblePickerScopes();
  for (var i = 0; i < visibleScopes.length; i++) {
    if (visibleScopes[i].querySelector(".rc-virtual-list-holder,.ant-select-item-option,[role=option]")) {
      return visibleScopes[i];
    }
  }
  return visibleScopes[0] || null;
}
"""


def js_string(value):
    return json.dumps(value, ensure_ascii=False)


def parse_args():
    parser = argparse.ArgumentParser(description="1688 批量开启官方定制项（BrowserWing）")
    parser.add_argument("--bw-port", type=int, default=int(os.environ.get("BW_PORT", "8080")))
    parser.add_argument("--delay", type=float, default=float(os.environ.get("ACTION_DELAY", "2")))
    parser.add_argument("--page-load-wait", type=float, default=float(os.environ.get("PAGE_LOAD_WAIT", "8")))
    parser.add_argument("--max-rounds", type=int, default=int(os.environ.get("MAX_ROUNDS", "200")))
    parser.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=int(os.environ.get("MAX_CONSECUTIVE_ERRORS", "5")),
    )
    return parser.parse_args()


class Runner:
    def __init__(self, args):
        self.args = args
        self.base = f"http://localhost:{args.bw_port}/api/v1/executor"
        self.root = Path(__file__).resolve().parent
        self.log_dir = self.root / "logs"
        self.shot_dir = self.root / "screenshots" / "official_customize"
        self.timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = self.log_dir / f"official_customize_{self.timestamp}.log"
        self.entry_url = ""
        self.round_total = 0
        self.category_total = 0
        self.category_success = 0
        self.category_skipped = 0
        self.category_failed = 0
        self.pending_remaining = 0
        self.pending_selected = 0
        self.prev_round_pending = None
        self.pending_no_drop_rounds = 0
        self.consecutive_errors = 0
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.shot_dir.mkdir(parents=True, exist_ok=True)

    def log(self, level, msg):
        colors = {
            "INFO": "\033[0;34m",
            "OK": "\033[0;32m",
            "WARN": "\033[0;33m",
            "ERROR": "\033[0;31m",
        }
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] [{level}] {msg}"
        color = colors.get(level, "\033[0m")
        print(f"{color}{line}\033[0m", flush=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def screenshot(self, name):
        path = str(self.shot_dir / name)
        try:
            requests.post(f"{self.base}/screenshot", json={"path": path}, timeout=15)
        except Exception:
            pass

    def evaluate(self, script, timeout=20):
        try:
            response = requests.post(
                f"{self.base}/evaluate",
                json={"script": script},
                timeout=timeout,
            )
            data = response.json()
            if data.get("success"):
                return data.get("data", {}).get("result", "")
            return f"ERROR:{data.get('error', 'unknown')}"
        except Exception as exc:
            return f"ERROR:{exc}"

    def navigate(self, url, timeout=40):
        try:
            response = requests.post(
                f"{self.base}/navigate",
                json={"url": url, "wait_until": "load", "timeout": 30},
                timeout=timeout,
            )
            return response.json().get("success", False)
        except Exception:
            return False

    def healthcheck(self):
        try:
            response = requests.get(f"{self.base}/help", timeout=5)
            return bool(response.text.strip())
        except Exception:
            return False

    def current_url(self):
        return self.evaluate("() => location.href")

    def wait_for_url_change(self, before_url, timeout_sec):
        deadline = time.time() + timeout_sec
        last = before_url
        while time.time() < deadline:
            time.sleep(1)
            last = self.current_url()
            if last and not last.startswith("ERROR:") and last != before_url:
                return last
        return last

    def parse_json_result(self, raw, default=None):
        if not raw or raw.startswith("ERROR:"):
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    def check_login(self):
        text = self.evaluate(
            """() => document.body ? document.body.innerText.substring(0, 300) : "NO_BODY" """
        )
        if not text or text.startswith("ERROR:"):
            return False
        return not (text == "NO_BODY" or "请登录" in text or "登录" in text[:100])

    def check_captcha(self):
        status = self.evaluate(
            """() => {
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
        )
        return status

    def browser_session_alive(self):
        url = self.current_url()
        return bool(url and not url.startswith("ERROR:"))

    def wait_for_captcha_clear(self):
        self.log("WARN", "检测到验证码，请在 BrowserWing 浏览器窗口中完成验证。")
        if sys.stdin is not None and sys.stdin.isatty():
            input("完成后按回车继续...")
        else:
            self.log("WARN", "当前为非交互模式：自动轮询验证码状态，直到清除。")

        start = time.time()
        error_count = 0
        while True:
            if not self.browser_session_alive():
                raise RuntimeError("BrowserWing 会话已断开，无法继续验证码校验。")
            status = self.check_captcha()
            if status == "CLEAN":
                self.log("OK", "验证码已清除，继续执行。")
                return
            if status.startswith("ERROR:"):
                error_count += 1
                if error_count >= 3:
                    raise RuntimeError(f"验证码状态检查失败（会话异常）：{status}")
                self.log("WARN", f"验证码状态读取异常，重试中：{status}")
                time.sleep(2)
                continue
            if time.time() - start > 900:
                raise RuntimeError(f"验证码等待超时：{status}")
            self.log("WARN", f"仍检测到验证码元素：{status}")
            time.sleep(5)

    def wait_for_login_ready(self):
        self.log("WARN", "检测到未登录状态，请在 BrowserWing 浏览器中完成 1688 登录。")
        if sys.stdin is not None and sys.stdin.isatty():
            input("完成后按回车继续...")
        else:
            self.log("WARN", "当前为非交互模式：自动轮询登录状态，直到恢复。")

        start = time.time()
        while True:
            if not self.browser_session_alive():
                raise RuntimeError("BrowserWing 会话已断开，无法继续等待登录。")
            if self.check_login():
                self.log("OK", "登录状态已恢复。")
                return
            if time.time() - start > 900:
                raise RuntimeError("等待登录超时，请确认账号状态。")
            time.sleep(5)

    def ensure_runtime_ready(self):
        if not self.healthcheck():
            raise RuntimeError(f"BrowserWing 未在端口 {self.args.bw_port} 运行")
        self.log("OK", f"BrowserWing 连通（端口 {self.args.bw_port}）")
        if not self.navigate(SHOP_BACKEND_URL):
            raise RuntimeError("商家后台导航失败")
        time.sleep(self.args.page_load_wait)
        if not self.check_login():
            self.wait_for_login_ready()
        captcha = self.check_captcha()
        if captcha != "CLEAN":
            self.wait_for_captcha_clear()

    def js_open_entry(self):
        return f"""() => {{
          {COMMON_JS}
          var menuTargets = ["找工厂"];
          var entryTarget = "设置官方定制项";
          var menus = bwFindVisibleByText(["a","button","span","div"], menuTargets, false);
          if (menus.length > 0) {{
            bwMouseClick(bwClickable(menus[0].el));
          }}
          var entryHref = "";
          document.querySelectorAll("a").forEach(function(a) {{
            var text = bwText(a);
            if (text.indexOf(entryTarget) >= 0 && a.href && !entryHref) entryHref = a.href;
          }});
          if (entryHref) {{
            window.location.href = entryHref;
            return "ENTRY_NAVIGATING:" + entryHref;
          }}
          var entries = bwFindVisibleByText(["a","button","span","div"], [entryTarget], false);
          if (entries.length === 0) return "ENTRY_NOT_FOUND";
          var el = bwClickable(entries[0].el);
          var anchor = el.closest("a") || el.querySelector("a");
          if (anchor && anchor.href) {{
            window.location.href = anchor.href;
            return "ENTRY_NAVIGATING:" + anchor.href;
          }}
          if (bwMouseClick(el)) return "ENTRY_CLICKED";
          return "ENTRY_CLICK_FAILED";
        }}"""

    def js_find_entry_href(self):
        return f"""() => {{
          {COMMON_JS}
          var target = "设置官方定制项";
          var href = "";
          document.querySelectorAll("a").forEach(function(a) {{
            if (bwText(a).indexOf(target) >= 0 && a.href && !href) href = a.href;
          }});
          return href ? "ENTRY_HREF:" + href : "ENTRY_HREF_NOT_FOUND";
        }}"""

    def open_entry_page(self):
        before_url = self.current_url()
        result = self.evaluate(self.js_open_entry(), timeout=25)
        time.sleep(ENTRY_WAIT)
        current = self.current_url()
        if current and not current.startswith("ERROR:") and current != before_url and current != SHOP_BACKEND_URL:
            self.entry_url = current
            self.log("OK", f"已进入官方定制项页面：{current}")
            return current
        if result.startswith("ENTRY_NAVIGATING:"):
            href = result.split(":", 1)[1]
            self.entry_url = href
            return href
        href_result = self.evaluate(self.js_find_entry_href())
        if href_result.startswith("ENTRY_HREF:"):
            href = href_result.split(":", 1)[1]
            self.log("WARN", f"菜单点击未完成跳转，改用 BrowserWing 直达 URL：{href}")
            if not self.navigate(href):
                raise RuntimeError("官方定制项兜底 URL 导航失败")
            time.sleep(self.args.page_load_wait)
            self.entry_url = href
            return href
        raise RuntimeError(f"无法打开“设置官方定制项”入口：{result}")

    def js_switch_pending_tab(self):
        return f"""() => {{
          {COMMON_JS}
          var tabs = bwFindVisibleByText(["[role=tab]",".next-tabs-tab",".ant-tabs-tab","a","span","div"], ["待设置"], true);
          if (tabs.length === 0) return "PENDING_TAB_NOT_FOUND";
          var tab = bwClickable(tabs[0].el);
          var selected = tab.getAttribute("aria-selected") === "true" ||
            tab.className.indexOf("active") >= 0 ||
            tab.className.indexOf("selected") >= 0;
          if (selected) return "PENDING_TAB_READY";
          return bwMouseClick(tab) ? "PENDING_TAB_SWITCHED" : "PENDING_TAB_CLICK_FAILED";
        }}"""

    def js_check_pending(self):
        return f"""() => {{
          {COMMON_JS}
          var body = bwText(document.body);
          var matched = body.match(/已选\\s*(\\d+)/);
          if (matched && matched[1] && matched[1] !== "0") return "PENDING_HAS_ITEMS:" + matched[1];
          var offerItems = Array.from(document.querySelectorAll("[class*=offerItem]")).filter(function(el) {{
            return bwVisible(el) && bwText(el).indexOf("ID：") >= 0;
          }});
          if (offerItems.length > 0) return "PENDING_HAS_ITEMS:" + offerItems.length;
          var rows = Array.from(document.querySelectorAll("tbody tr")).filter(function(row) {{
            return bwVisible(row) && bwText(row).indexOf("ID：") >= 0;
          }});
          if (rows.length > 0) return "PENDING_HAS_ITEMS:" + rows.length;
          if (body.indexOf("/500(最多)") >= 0 || body.indexOf("已选") >= 0) {{
            var selected = body.match(/已选\\s*(\\d+)/);
            if (selected && selected[1] && selected[1] !== "0") return "PENDING_HAS_ITEMS:" + selected[1];
          }}
          if (body.indexOf("暂无") >= 0 || body.indexOf("没有数据") >= 0 || body.indexOf("待设置") >= 0) return "PENDING_EMPTY";
          return "PENDING_UNKNOWN";
        }}"""

    def js_pending_summary(self):
        return f"""() => {{
          {COMMON_JS}
          var body = bwText(document.body);
          var selectedMatch = body.match(/已选\\s*(\\d+)\\s*\\/\\s*500\\(最多\\)/);
          var visibleOffers = Array.from(document.querySelectorAll("[class*=offerItem]")).filter(function(el) {{
            return bwVisible(el) && bwText(el).indexOf("ID：") >= 0;
          }});
          var hasNext = bwFindVisibleByText(["button","a","span","div"], ["下一步"], true).length > 0;
          return JSON.stringify({{
            selectedCount: selectedMatch ? parseInt(selectedMatch[1], 10) : 0,
            visibleOfferCount: visibleOffers.length,
            hasNext: hasNext
          }});
        }}"""

    def js_select_all_pending(self):
        return f"""() => {{
          {COMMON_JS}
          var input = document.querySelector("input.ant-checkbox-input");
          if (!input) return "SELECT_ALL_NOT_FOUND";
          var label = input.closest("label") || input.parentElement || input;
          ["mouseover", "mousedown", "mouseup", "click"].forEach(function(type) {{
            try {{
              label.dispatchEvent(new MouseEvent(type, {{ bubbles: true, cancelable: true, view: window }}));
            }} catch (e) {{}}
          }});
          try {{ input.click(); }} catch (e) {{}}
          var body = bwText(document.body);
          var matched = body.match(/已选\\s*(\\d+)\\s*\\/\\s*500\\(最多\\)/);
          if (matched && matched[1] && matched[1] !== "0") return "SELECT_ALL_OK:" + matched[1];
          return "SELECT_ALL_CLICKED";
        }}"""

    def js_click_next(self):
        return f"""() => {{
          {COMMON_JS}
          var buttons = bwFindVisibleByText(["button","a","span","div"], ["下一步"], true);
          if (buttons.length === 0) return "NEXT_NOT_FOUND";
          var btn = buttons[0].el.closest("button") || bwClickable(buttons[0].el);
          var react = bwCallReactHandler(btn, ["onClick"], function(node) {{
            return {{
              type: "click",
              button: 0,
              currentTarget: node,
              target: node,
              preventDefault: function() {{}},
              stopPropagation: function() {{}}
            }};
          }});
          if (react) return "NEXT_CLICKED_REACT:" + react;
          return bwMouseClick(btn) ? "NEXT_CLICKED" : "NEXT_CLICK_FAILED";
        }}"""

    def js_collect_categories(self):
        return f"""() => {{
          {COMMON_JS}
          var expandTargets = ["更多", "展开", "全部类目", "更多类目"];
          var expanded = 0;
          bwFindVisibleByText(["button","a","span","div"], expandTargets, true).forEach(function(item) {{
            if (bwMouseClick(bwClickable(item.el))) expanded += 1;
          }});
          var tabs = bwCollectTabs();
          return JSON.stringify({{ status: tabs.length ? "CATEGORY_LIST_READY" : "CATEGORY_LIST_EMPTY", expanded: expanded, categories: tabs }});
        }}"""

    def js_open_category(self, category_name):
        category = js_string(category_name)
        return f"""() => {{
          {COMMON_JS}
          var target = {category};
          var tabs = bwCollectTabs();
          if (tabs.indexOf(target) < 0) {{
            bwFindVisibleByText(["button","a","span","div"], ["更多", "展开", "全部类目", "更多类目"], true).forEach(function(item) {{
              bwMouseClick(bwClickable(item.el));
            }});
          }}
          var found = bwFindVisibleByText(["[role=tab]",".next-tabs-tab",".ant-tabs-tab",".next-menu-item",".category-tab",".tab-item","a","span","div"], [target], true);
          if (found.length === 0) return "CATEGORY_NOT_FOUND:" + target;
          return bwMouseClick(bwClickable(found[0].el)) ? "CATEGORY_OPENED:" + target : "CATEGORY_CLICK_FAILED:" + target;
        }}"""

    def js_packaging_state(self):
        options = json.dumps(TARGET_OPTIONS, ensure_ascii=False)
        return f"""() => {{
          {COMMON_JS}
          var targets = {options};
          var field = bwFindPackagingField();
          if (!field || !field.selectRoot) return JSON.stringify({{ status: "PACKAGING_NOT_FOUND", selected: [] }});
          var selectRoot = field.selectRoot;
          var selected = [];
          selectRoot.querySelectorAll(".ant-select-selection-item,.ant-tag,.next-tag,.next-tag-body,[class*=selection-item]").forEach(function(el) {{
            var text = bwText(el);
            if (!text) return;
            var textKey = bwNormKey(text);
            targets.forEach(function(target) {{
              var key = bwNormKey(target.keyword);
              if (textKey.indexOf(key) >= 0) selected.push(target.label);
            }});
          }});
          var input = field.input || selectRoot.querySelector("input.ant-select-selection-search-input,input");
          if (input) {{
            var inputValue = bwNormKey(input.value || "");
            targets.forEach(function(target) {{
              if (inputValue.indexOf(bwNormKey(target.keyword)) >= 0) selected.push(target.label);
            }});
          }}
          var uniq = [];
          selected.forEach(function(item) {{ if (uniq.indexOf(item) < 0) uniq.push(item); }});
          return JSON.stringify({{ status: "PACKAGING_FOUND", selected: uniq }});
        }}"""

    def js_open_packaging_picker(self):
        return f"""() => {{
          {COMMON_JS}
          try {{
            document.dispatchEvent(new KeyboardEvent("keydown", {{ key: "Escape", bubbles: true }}));
          }} catch (e) {{}}
          var field = bwFindPackagingField();
          if (!field || !field.selectRoot) return JSON.stringify({{ status: "PACKAGING_NOT_FOUND", listId: "" }});
          var container = field.container;
          var trigger = container.querySelector(".ant-select-selector,.next-select,.ant-select,[role=combobox],input,.next-tag-list");
          if (!trigger) {{
            var siblings = Array.from(container.querySelectorAll("*")).filter(function(el) {{
              return bwVisible(el) && (el.className.indexOf("select") >= 0 || el.getAttribute("role") === "combobox");
            }});
            trigger = siblings[0] || null;
          }}
          if (!trigger) return JSON.stringify({{ status: "PACKAGING_TRIGGER_NOT_FOUND", listId: "" }});
          var clickTarget = trigger.closest(".ant-select-selector") || trigger;
          var selectRoot = field.selectRoot || clickTarget.closest(".ant-select") || container.querySelector(".ant-select") || clickTarget;
          var input = field.input || container.querySelector("input.ant-select-selection-search-input,input");
          if (input) {{
            try {{ input.removeAttribute("readonly"); }} catch (e) {{}}
            try {{ input.focus(); }} catch (e) {{}}
          }}
          ["mouseover", "mousedown", "mouseup", "click"].forEach(function(type) {{
            try {{
              clickTarget.dispatchEvent(new MouseEvent(type, {{ bubbles: true, cancelable: true, view: window }}));
            }} catch (e) {{}}
          }});
          if (input) {{
            ["mousedown", "mouseup", "click"].forEach(function(type) {{
              try {{
                input.dispatchEvent(new MouseEvent(type, {{ bubbles: true, cancelable: true, view: window }}));
              }} catch (e) {{}}
            }});
          }}
          var opened = (input && input.getAttribute("aria-expanded") === "true") ||
            !!document.querySelector(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .rc-virtual-list-holder,[role=listbox] .rc-virtual-list-holder");
          var listId = "";
          if (input) listId = input.getAttribute("aria-controls") || input.getAttribute("aria-owns") || "";
          if (opened) return JSON.stringify({{ status: "PACKAGING_OPENED", listId: listId }});
          bwMouseClick(selectRoot);
          if (input) bwMouseClick(input);
          if ((input && input.getAttribute("aria-expanded") === "true") ||
              document.querySelector(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .rc-virtual-list-holder,[role=listbox] .rc-virtual-list-holder")) {{
            return JSON.stringify({{ status: "PACKAGING_OPENED_FALLBACK", listId: listId }});
          }}
          if (input && (input.getAttribute("aria-controls") || input.getAttribute("aria-owns") || input.id)) {{
            return JSON.stringify({{ status: "PACKAGING_OPEN_PENDING", listId: listId }});
          }}
          return JSON.stringify({{ status: "PACKAGING_OPEN_FAILED", listId: listId }});
        }}"""

    def js_select_option(self, option_text, option_keyword, option_price):
        option = js_string(option_text)
        option_keyword_json = js_string(option_keyword.lower())
        option_price_json = js_string(option_price)
        return f"""() => {{
          {COMMON_JS}
          var target = {option};
          var targetKeyword = bwNormKey({option_keyword_json});
          var targetPrice = bwNormKey({option_price_json});
          var selected = false;
          document.querySelectorAll("*").forEach(function(el) {{
            var text = bwText(el);
            if (!text) return;
            var textKey = bwNormKey(text);
            if (textKey.indexOf(targetKeyword) >= 0 && (el.className.indexOf("tag") >= 0 || el.className.indexOf("selection") >= 0)) selected = true;
          }});
          if (selected) return "OPTION_ALREADY_SELECTED:" + target;
          function matchOption(el) {{
            var text = bwNormKey(el.innerText || el.textContent || "");
            var name = "";
            var price = "";
            el.querySelectorAll("[class*=optionContentName], .ant-select-item-option-content, span, div").forEach(function(node) {{
              var nodeText = bwNormKey(node.innerText || node.textContent || "");
              if (!nodeText) return;
              if (!name && nodeText.indexOf(targetKeyword) >= 0) name = nodeText;
              if (!price && targetPrice && nodeText.indexOf(targetPrice) >= 0) price = nodeText;
            }});
            if (name && targetPrice) return !!price || text.indexOf(targetPrice) >= 0;
            return text.indexOf(targetKeyword) >= 0;
          }}
          var selectors = [
            ".ant-select-dropdown .ant-select-item-option",
            "[role=listbox] .ant-select-item-option",
            ".next-popup .ant-select-item-option"
          ];
          var holder = document.querySelector(".ant-select-dropdown .rc-virtual-list-holder, .rc-virtual-list-holder");
          var maxRounds = 40;
          for (var round = 0; round < maxRounds; round++) {{
            var found = [];
            selectors.forEach(function(selector) {{
              document.querySelectorAll(selector).forEach(function(el) {{
                if (!bwVisible(el)) return;
                if (matchOption(el)) found.push(el);
              }});
            }});
            if (found.length > 0) {{
              var targetEl = bwClickable(found[0]);
              return bwMouseClick(targetEl) ? "OPTION_CLICKED:" + target + ":" + round : "OPTION_CLICK_FAILED:" + target;
            }}
            if (!holder) break;
            var nextTop = Math.min(holder.scrollHeight - holder.clientHeight, holder.scrollTop + Math.max(holder.clientHeight * 0.8, 120));
            if (nextTop <= holder.scrollTop + 1) break;
            holder.scrollTop = nextTop;
            holder.dispatchEvent(new Event("scroll", {{ bubbles: true }}));
          }}
          return "OPTION_NOT_FOUND:" + target;
        }}"""

    def js_get_picker_metrics(self, list_id):
        list_id_json = js_string(list_id or "")
        return f"""() => {{
          {COMMON_JS}
          var listId = {list_id_json};
          var scope = bwResolvePickerScope(listId);
          var holder = scope ? scope.querySelector(".rc-virtual-list-holder") : null;
          if ((!holder || !bwVisible(holder)) && scope && scope.closest(".ant-select-dropdown,[role=listbox]")) {{
            holder = scope.closest(".ant-select-dropdown,[role=listbox]").querySelector(".rc-virtual-list-holder");
          }}
          if ((!holder || !bwVisible(holder)) && bwVisiblePickerScopes().length > 0) {{
            var scopes = bwVisiblePickerScopes();
            for (var i = 0; i < scopes.length; i++) {{
              var candidate = scopes[i].querySelector(".rc-virtual-list-holder");
              if (candidate && bwVisible(candidate)) {{
                holder = candidate;
                break;
              }}
            }}
          }}
          if (!holder) return JSON.stringify({{ status: "NO_HOLDER", scrollTop: 0, scrollHeight: 0, clientHeight: 0 }});
          return JSON.stringify({{
            status: "OK",
            scrollTop: holder.scrollTop,
            scrollHeight: holder.scrollHeight,
            clientHeight: holder.clientHeight
          }});
        }}"""

    def js_set_picker_scroll(self, list_id, scroll_top):
        list_id_json = js_string(list_id or "")
        return f"""() => {{
          {COMMON_JS}
          var listId = {list_id_json};
          var scope = bwResolvePickerScope(listId);
          var holder = scope ? scope.querySelector(".rc-virtual-list-holder") : null;
          if ((!holder || !bwVisible(holder)) && scope && scope.closest(".ant-select-dropdown,[role=listbox]")) {{
            holder = scope.closest(".ant-select-dropdown,[role=listbox]").querySelector(".rc-virtual-list-holder");
          }}
          if ((!holder || !bwVisible(holder)) && bwVisiblePickerScopes().length > 0) {{
            var scopes = bwVisiblePickerScopes();
            for (var i = 0; i < scopes.length; i++) {{
              var candidate = scopes[i].querySelector(".rc-virtual-list-holder");
              if (candidate && bwVisible(candidate)) {{
                holder = candidate;
                break;
              }}
            }}
          }}
          if (!holder) return "NO_HOLDER";
          holder.scrollTop = {int(scroll_top)};
          holder.dispatchEvent(new Event("scroll", {{ bubbles: true }}));
          return "SCROLLED:" + holder.scrollTop;
        }}"""

    def js_click_visible_option(self, option_text, option_keyword, option_price, list_id):
        option = js_string(option_text)
        option_keyword_json = js_string(option_keyword.lower())
        option_price_json = js_string(option_price)
        list_id_json = js_string(list_id or "")
        return f"""() => {{
          {COMMON_JS}
          var target = {option};
          var targetKeyword = bwNormKey({option_keyword_json});
          var targetPrice = bwNormKey({option_price_json});
          var listId = {list_id_json};
          var field = bwFindPackagingField();
          var selected = false;
          if (field && field.selectRoot) {{
            field.selectRoot.querySelectorAll(".ant-select-selection-item,.ant-tag,.next-tag,.next-tag-body,[class*=selection-item]").forEach(function(el) {{
              var text = bwText(el);
              if (!text) return;
              var textKey = bwNormKey(text);
              if (textKey.indexOf(targetKeyword) >= 0 && (!targetPrice || textKey.indexOf(targetPrice) >= 0)) selected = true;
            }});
            if (!selected && field.input) {{
              var inputValue = bwNormKey(field.input.value || "");
              if (inputValue.indexOf(targetKeyword) >= 0 && (!targetPrice || inputValue.indexOf(targetPrice) >= 0)) {{
                selected = true;
              }}
            }}
          }}
          if (selected) return "OPTION_ALREADY_SELECTED:" + target;
          function matchOption(el) {{
            var text = bwNormKey(el.innerText || el.textContent || "");
            if (text.indexOf(targetKeyword) < 0) return false;
            if (targetPrice && text.indexOf(targetPrice) < 0) return false;
            return true;
          }}
          var scopes = [];
          var resolvedScope = bwResolvePickerScope(listId);
          if (resolvedScope) scopes.push(resolvedScope);
          bwVisiblePickerScopes().forEach(function(scope) {{
            if (scopes.indexOf(scope) < 0) scopes.push(scope);
          }});
          scopes.push(document);
          var found = [];
          for (var i = 0; i < scopes.length && found.length === 0; i++) {{
            found = Array.from(scopes[i].querySelectorAll(".ant-select-item-option,[role=option]"))
              .filter(function(el) {{ return bwVisible(el); }})
              .filter(matchOption);
          }}
          if (found.length === 0) return "OPTION_NOT_VISIBLE:" + target;
          var targetEl = bwClickable(found[0]);
          return bwMouseClick(targetEl) ? "OPTION_CLICKED:" + target : "OPTION_CLICK_FAILED:" + target;
        }}"""

    def js_click_quote(self):
        return f"""() => {{
          {COMMON_JS}
          var texts = [
            "确定，去设置报价",
            "确定,去设置报价",
            "去设置报价",
            "修改报价",
            "点击修改起定量和报价"
          ];
          var found = bwFindVisibleByText(["button","a","span","div"], texts, false);
          if (found.length === 0) return "OPTIONS_APPLY_NOT_FOUND";
          return bwMouseClick(bwClickable(found[0].el)) ? "OPTIONS_APPLIED" : "OPTIONS_APPLY_FAILED";
        }}"""

    def js_confirm_pricing(self):
        return f"""() => {{
          {COMMON_JS}
          var dialogs = Array.from(document.querySelectorAll(".next-dialog,.ant-modal,[role=dialog]")).filter(function(el) {{
            return bwVisible(el);
          }});
          if (dialogs.length === 0) return "PRICING_DIALOG_NOT_FOUND";
          for (var i = 0; i < dialogs.length; i++) {{
            var dialog = dialogs[i];
            var iframe = dialog.querySelector("iframe");
            if (iframe) {{
              try {{
                var frameWindow = iframe.contentWindow;
                var frameDoc = iframe.contentDocument || (frameWindow && frameWindow.document);
                if (frameDoc && frameDoc.body) {{
                  var candidates = Array.from(frameDoc.querySelectorAll("button,span,div,a")).filter(function(node) {{
                    if (!node) return false;
                    var style = frameWindow.getComputedStyle(node);
                    if (!style || style.display === "none" || style.visibility === "hidden") return false;
                    var rect = node.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) return false;
                    var text = bwNorm(node.innerText || node.textContent || "");
                    return text === "确定" || text === "确 定" || text === "确认";
                  }});
                  if (candidates.length > 0) {{
                    var button = candidates[0];
                    try {{ button.scrollIntoView({{ behavior: "auto", block: "center" }}); }} catch (e) {{}}
                    ["mouseover", "mousedown", "mouseup", "click"].forEach(function(type) {{
                      try {{
                        button.dispatchEvent(new frameWindow.MouseEvent(type, {{ bubbles: true, cancelable: true, view: frameWindow }}));
                      }} catch (e) {{}}
                    }});
                    try {{ button.click(); }} catch (e) {{}}
                    return "PRICING_CONFIRMED";
                  }}
                }}
              }} catch (e) {{}}
            }}
            var buttons = bwFindVisibleByText(["button","span","div"], ["确定", "确 定", "确认"], true).filter(function(item) {{
              return dialog.contains(item.el);
            }});
            if (buttons.length > 0) {{
              return bwMouseClick(bwClickable(buttons[0].el)) ? "PRICING_CONFIRMED" : "PRICING_CONFIRM_FAILED";
            }}
          }}
          return "PRICING_CONFIRM_NOT_FOUND";
        }}"""

    def js_check_pricing_modal_options(self):
        options = json.dumps(TARGET_OPTIONS, ensure_ascii=False)
        return f"""() => {{
          {COMMON_JS}
          var targets = {options};
          var dialogs = Array.from(document.querySelectorAll(".next-dialog,.ant-modal,[role=dialog]")).filter(function(el) {{
            return bwVisible(el);
          }});
          if (dialogs.length === 0) return JSON.stringify({{ status: "PRICING_DIALOG_NOT_FOUND", matched: [] }});
          for (var i = 0; i < dialogs.length; i++) {{
            var dialog = dialogs[i];
            var iframe = dialog.querySelector("iframe");
            if (!iframe) continue;
            try {{
              var frameWindow = iframe.contentWindow;
              var frameDoc = iframe.contentDocument || (frameWindow && frameWindow.document);
              if (!frameDoc || !frameDoc.body) continue;
              var values = [];
              frameDoc.querySelectorAll("input,textarea,select").forEach(function(node) {{
                var value = bwNorm(node.value || node.getAttribute("value") || node.placeholder || "");
                if (value) values.push(value);
              }});
              var bodyText = bwNorm(frameDoc.body.innerText || frameDoc.body.textContent || "");
              var haystack = bwNorm(values.join(" ") + " " + bodyText);
              var matched = [];
              targets.forEach(function(target) {{
                if (bwNormKey(haystack).indexOf(bwNormKey(target.keyword)) >= 0) matched.push(target.label);
              }});
              var uniq = [];
              matched.forEach(function(item) {{ if (uniq.indexOf(item) < 0) uniq.push(item); }});
              return JSON.stringify({{
                status: "PRICING_MODAL_READY",
                matched: uniq,
                values: values.slice(0, 40),
                bodyText: bodyText.substring(0, 1200)
              }});
            }} catch (e) {{
              return JSON.stringify({{ status: "PRICING_MODAL_IFRAME_ERROR", matched: [], error: String(e) }});
            }}
          }}
          return JSON.stringify({{ status: "PRICING_IFRAME_NOT_FOUND", matched: [] }});
        }}"""

    def js_save_category(self, category_name):
        category = js_string(category_name)
        return f"""() => {{
          {COMMON_JS}
          var target = "保存" + {category} + "的定制项";
          var target2 = "保存" + {category} + "商品的定制项";
          try {{ window.scrollTo(0, document.body.scrollHeight); }} catch (e) {{}}
          var found = bwFindVisibleByText(["button","a","span","div"], [target2, target], true);
          if (found.length === 0) {{
            found = bwFindVisibleByText(["button","a","span","div"], ["保存", "定制项"], false).filter(function(item) {{
              return item.text.indexOf({category}) >= 0 && item.text.indexOf("定制项") >= 0;
            }});
          }}
          if (found.length === 0) return "SAVE_NOT_FOUND:" + {category};
          return bwMouseClick(bwClickable(found[0].el)) ? "CATEGORY_SAVED:" + {category} : "CATEGORY_SAVE_CLICK_FAILED:" + {category};
        }}"""

    def js_check_save_feedback(self):
        return f"""() => {{
          {COMMON_JS}
          var success = bwFindVisibleByText([".next-message",".ant-message",".next-notice",".ant-notification-notice","body *"], ["成功"], false);
          if (success.length > 0) return "SAVE_SUCCESS";
          var fail = bwFindVisibleByText([".next-message",".ant-message",".next-notice",".ant-notification-notice","body *"], ["失败", "错误"], false);
          if (fail.length > 0) return "SAVE_FAILED";
          return "SAVE_UNKNOWN";
        }}"""

    def enter_pending_page(self):
        if self.entry_url:
            if not self.navigate(self.entry_url):
                self.log("WARN", "缓存的官方定制项 URL 导航失败，回退到后台入口重新打开。")
                self.navigate(SHOP_BACKEND_URL)
                time.sleep(self.args.page_load_wait)
                self.open_entry_page()
        else:
            self.navigate(SHOP_BACKEND_URL)
            time.sleep(self.args.page_load_wait)
            self.open_entry_page()
        time.sleep(max(self.args.page_load_wait / 2, 3))
        tab_status = self.evaluate(self.js_switch_pending_tab())
        if tab_status not in ("PENDING_TAB_READY", "PENDING_TAB_SWITCHED"):
            raise RuntimeError(f"待设置标签切换失败：{tab_status}")
        time.sleep(TAB_WAIT)

    def pending_status(self):
        status = self.evaluate(self.js_check_pending())
        summary = self.parse_json_result(self.evaluate(self.js_pending_summary()), {})
        self.pending_selected = int(summary.get("selectedCount", 0) or 0)
        if status.startswith("PENDING_HAS_ITEMS:"):
            try:
                self.pending_remaining = int(status.split(":", 1)[1])
            except ValueError:
                self.pending_remaining = -1
        else:
            self.pending_remaining = 0
        return status

    def ensure_pending_selection(self):
        if self.pending_selected > 0:
            return f"SELECT_READY:{self.pending_selected}"
        result = self.evaluate(self.js_select_all_pending())
        time.sleep(TAB_WAIT)
        summary = self.parse_json_result(self.evaluate(self.js_pending_summary()), {})
        self.pending_selected = int(summary.get("selectedCount", 0) or 0)
        if self.pending_selected > 0:
            return f"SELECT_READY:{self.pending_selected}"
        return result

    def collect_categories(self):
        raw = self.evaluate(self.js_collect_categories(), timeout=25)
        data = self.parse_json_result(raw, {"status": "CATEGORY_LIST_EMPTY", "categories": []})
        categories = data.get("categories", [])
        deduped = []
        seen = set()
        for category in categories:
            key = re.sub(r"\s+", " ", category).strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(category)
        return deduped, data.get("expanded", 0)

    def get_packaging_state(self):
        return self.parse_json_result(
            self.evaluate(self.js_packaging_state()),
            {"status": "PACKAGING_NOT_FOUND", "selected": []},
        )

    def ensure_option_selected(self, option_text, option_keyword, option_price):
        for _ in range(4):
            state = self.get_packaging_state()
            if state.get("status") != "PACKAGING_FOUND":
                return state.get("status", "PACKAGING_NOT_FOUND")
            if option_text in state.get("selected", []):
                return f"OPTION_ALREADY_SELECTED:{option_text}"

            metrics = {}
            open_data = {}
            for _ in range(3):
                open_data = self.parse_json_result(
                    self.evaluate(self.js_open_packaging_picker()),
                    {"status": "PACKAGING_OPEN_FAILED", "listId": ""},
                )
                if not (
                    str(open_data.get("status", "")).startswith("PACKAGING_OPENED")
                    or open_data.get("status") == "PACKAGING_OPEN_PENDING"
                ):
                    continue
                time.sleep(PICKER_WAIT)
                metrics = self.parse_json_result(
                    self.evaluate(self.js_get_picker_metrics(open_data.get("listId", ""))),
                    {},
                )
                if metrics.get("status") == "OK":
                    break
                time.sleep(1)
            if not (
                str(open_data.get("status", "")).startswith("PACKAGING_OPENED")
                or open_data.get("status") == "PACKAGING_OPEN_PENDING"
            ):
                return open_data.get("status", "PACKAGING_OPEN_FAILED")
            if metrics.get("status") != "OK":
                if metrics.get("status") == "NO_HOLDER":
                    # Some categories render dropdown lazily; reopen once and re-read metrics.
                    time.sleep(0.8)
                    reopen_data = self.parse_json_result(
                        self.evaluate(self.js_open_packaging_picker()),
                        {"status": "PACKAGING_OPEN_FAILED", "listId": ""},
                    )
                    if str(reopen_data.get("status", "")).startswith("PACKAGING_OPENED") or reopen_data.get(
                        "status"
                    ) == "PACKAGING_OPEN_PENDING":
                        time.sleep(PICKER_WAIT)
                        metrics = self.parse_json_result(
                            self.evaluate(self.js_get_picker_metrics(reopen_data.get("listId", ""))),
                            {},
                        )
                return f"PICKER_METRICS_FAILED:{metrics}"

            scroll_height = int(metrics.get("scrollHeight", 0) or 0)
            client_height = int(metrics.get("clientHeight", 0) or 0)
            step = max(int(client_height * 0.8), 120) if client_height else 120
            positions = [0]
            if scroll_height > client_height > 0:
                pos = 0
                max_top = max(scroll_height - client_height, 0)
                while pos < max_top:
                    pos = min(pos + step, max_top)
                    positions.append(pos)
            seen = set()
            ordered_positions = []
            for pos in positions:
                if pos not in seen:
                    seen.add(pos)
                    ordered_positions.append(pos)

            clicked = False
            for pos in ordered_positions:
                self.evaluate(self.js_set_picker_scroll(open_data.get("listId", ""), pos))
                time.sleep(0.8)
                result = self.evaluate(
                    self.js_click_visible_option(option_text, option_keyword, option_price, open_data.get("listId", "")),
                    timeout=25,
                )
                if result.startswith("OPTION_CLICKED:") or result.startswith("OPTION_ALREADY_SELECTED:"):
                    clicked = True
                    time.sleep(0.8)
                    confirm = self.get_packaging_state()
                    if confirm.get("status") == "PACKAGING_FOUND" and option_text in confirm.get("selected", []):
                        return f"OPTION_CONFIRMED:{option_text}"
                    break
            if not clicked:
                return f"OPTION_NOT_FOUND:{option_text}"
            time.sleep(0.8)

        return f"OPTION_NOT_CONFIRMED:{option_text}"

    def process_category(self, category_index, category_name):
        self.category_total += 1
        prefix = f"round_{self.round_total:03d}_cat_{category_index:02d}"
        self.log("INFO", f"[类目] {category_name}")
        open_status = self.evaluate(self.js_open_category(category_name))
        if not open_status.startswith("CATEGORY_OPENED:"):
            self.category_failed += 1
            self.consecutive_errors += 1
            self.log("ERROR", f"类目切换失败：{open_status}")
            self.screenshot(f"{prefix}_open_error.png")
            return False

        time.sleep(TAB_WAIT)
        packaging = self.get_packaging_state()
        if packaging.get("status") != "PACKAGING_FOUND":
            self.category_skipped += 1
            self.log("WARN", f"{category_name} 未发现“包装定制”，跳过。")
            self.screenshot(f"{prefix}_skip.png")
            return True

        selected = packaging.get("selected", [])
        self.log("INFO", f"已选包装项：{selected if selected else '空'}")
        self.screenshot(f"{prefix}_before.png")

        for option in TARGET_OPTIONS:
            option_text = option["label"]
            if option_text in selected:
                self.log("OK", f"已存在选项：{option_text}")
                continue
            result = self.ensure_option_selected(option_text, option["keyword"], option["price"])
            packaging = self.get_packaging_state()
            selected = packaging.get("selected", [])
            if result.startswith("OPTION_CONFIRMED:") or result.startswith("OPTION_ALREADY_SELECTED:"):
                self.log("OK", f"已补齐选项：{option_text}")
                continue
            self.category_failed += 1
            self.consecutive_errors += 1
            self.log("ERROR", f"选择包装选项失败：{result}")
            self.screenshot(f"{prefix}_option_error.png")
            return False

        packaging = self.get_packaging_state()
        final_selected = packaging.get("selected", [])
        missing = [option["label"] for option in TARGET_OPTIONS if option["label"] not in final_selected]
        if missing:
            self.category_failed += 1
            self.consecutive_errors += 1
            self.log("ERROR", f"包装定制未真正选中全部目标项，缺失：{missing}")
            self.screenshot(f"{prefix}_selection_mismatch.png")
            return False

        quote_status = self.evaluate(self.js_click_quote())
        if quote_status != "OPTIONS_APPLIED":
            self.category_failed += 1
            self.consecutive_errors += 1
            self.log("ERROR", f"点击“确定，去设置报价”失败：{quote_status}")
            self.screenshot(f"{prefix}_quote_error.png")
            return False

        time.sleep(PICKER_WAIT)
        pricing_modal = self.parse_json_result(
            self.evaluate(self.js_check_pricing_modal_options(), timeout=25),
            {"status": "PRICING_DIALOG_NOT_FOUND", "matched": []},
        )
        matched = pricing_modal.get("matched", [])
        missing_modal = [option["label"] for option in TARGET_OPTIONS if option["label"] not in matched]
        if pricing_modal.get("status") != "PRICING_MODAL_READY" or missing_modal:
            self.category_failed += 1
            self.consecutive_errors += 1
            self.log(
                "ERROR",
                f"报价弹窗未正常展示4个目标项：status={pricing_modal.get('status')} missing={missing_modal}",
            )
            self.screenshot(f"{prefix}_pricing_modal_mismatch.png")
            return False

        pricing_status = self.evaluate(self.js_confirm_pricing())
        if pricing_status != "PRICING_CONFIRMED":
            self.category_failed += 1
            self.consecutive_errors += 1
            self.log("ERROR", f"包装定制弹窗确认失败：{pricing_status}")
            self.screenshot(f"{prefix}_pricing_error.png")
            return False

        time.sleep(PICKER_WAIT)
        save_status = self.evaluate(self.js_save_category(category_name))
        if not save_status.startswith("CATEGORY_SAVED:"):
            self.category_failed += 1
            self.consecutive_errors += 1
            self.log("ERROR", f"保存类目失败：{save_status}")
            self.screenshot(f"{prefix}_save_error.png")
            return False

        time.sleep(SAVE_WAIT)
        feedback = self.evaluate(self.js_check_save_feedback())
        self.category_success += 1
        self.consecutive_errors = 0
        self.log("OK", f"{category_name} 已保存，反馈：{feedback}")
        self.screenshot(f"{prefix}_after.png")
        return True

    def run_round(self):
        self.round_total += 1
        self.log("INFO", f"开始第 {self.round_total} 轮处理。")
        self.enter_pending_page()
        status = self.pending_status()
        if status == "PENDING_EMPTY":
            self.log("OK", "待设置列表为空，任务结束。")
            return False
        if not status.startswith("PENDING_HAS_ITEMS:"):
            raise RuntimeError(f"无法确认待设置列表状态：{status}")

        self.log("OK", f"待设置商品数：{self.pending_remaining}")
        self.screenshot(f"round_{self.round_total:03d}_pending.png")

        if self.prev_round_pending is None:
            self.prev_round_pending = self.pending_remaining
            self.pending_no_drop_rounds = 0
        else:
            if self.pending_remaining < self.prev_round_pending:
                self.pending_no_drop_rounds = 0
            else:
                self.pending_no_drop_rounds += 1
                self.log(
                    "WARN",
                    f"待设置数量未下降：上一轮={self.prev_round_pending}，本轮={self.pending_remaining}",
                )
                if self.pending_no_drop_rounds >= 1:
                    self.log("WARN", "连续两轮待设置未下降，自动停机以避免重复空转。")
                    return False
            self.prev_round_pending = self.pending_remaining

        select_status = self.ensure_pending_selection()
        if not select_status.startswith("SELECT_READY:"):
            raise RuntimeError(f"待设置商品全选失败：{select_status}")
        self.log("OK", f"待设置已选商品数：{self.pending_selected}")

        next_status = self.evaluate(self.js_click_next())
        if not next_status.startswith("NEXT_CLICKED"):
            raise RuntimeError(f"点击下一步失败：{next_status}")
        self.log("OK", "已进入类目设置页。")
        time.sleep(self.args.page_load_wait)

        captcha = self.check_captcha()
        if captcha != "CLEAN":
            self.wait_for_captcha_clear()

        categories, expanded = self.collect_categories()
        if not categories:
            raise RuntimeError("未采集到任何类目标签")
        self.log("INFO", f"采集到 {len(categories)} 个类目标签，展开动作 {expanded} 次。")

        for index, category_name in enumerate(categories, start=1):
            ok = self.process_category(index, category_name)
            if self.consecutive_errors >= self.args.max_consecutive_errors:
                raise RuntimeError(f"连续错误达到上限 {self.args.max_consecutive_errors}")
            if not ok:
                time.sleep(self.args.delay)
            captcha = self.check_captcha()
            if captcha != "CLEAN":
                self.wait_for_captcha_clear()

        self.log("INFO", f"第 {self.round_total} 轮完成，准备返回待设置页。")
        time.sleep(ROUND_RESET_WAIT)
        return True

    def run(self):
        print("\n" + "=" * 60)
        print("  1688 批量开启官方定制项（BrowserWing）")
        print("=" * 60)
        print(f"  后台入口：{SHOP_BACKEND_URL}")
        print(f"  最大轮次：{self.args.max_rounds}")
        print(f"  操作间隔：{self.args.delay} 秒")
        print("=" * 60 + "\n")

        self.ensure_runtime_ready()
        self.open_entry_page()

        while self.round_total < self.args.max_rounds:
            keep_running = self.run_round()
            if not keep_running:
                break
            time.sleep(self.args.delay)

        self.log("INFO", "批量处理结束。")
        self.log("INFO", f"ROUND_TOTAL={self.round_total}")
        self.log("INFO", f"CATEGORY_TOTAL={self.category_total}")
        self.log("OK", f"CATEGORY_SUCCESS={self.category_success}")
        self.log("WARN", f"CATEGORY_SKIPPED={self.category_skipped}")
        self.log("ERROR", f"CATEGORY_FAILED={self.category_failed}")
        self.log("INFO", f"PENDING_REMAINING={self.pending_remaining}")
        self.log("INFO", f"日志文件：{self.log_path}")
        self.log("INFO", f"截图目录：{self.shot_dir}")


def main():
    args = parse_args()
    runner = Runner(args)
    try:
        runner.run()
    except RuntimeError as exc:
        runner.log("ERROR", str(exc))
        runner.screenshot(f"fatal_{runner.round_total:03d}.png")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
