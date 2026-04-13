---
name: 1688-title-optimizer
description: "1688商品运营自动化技能。基于BrowserWing浏览器自动化平台，实现1688后台商品的AI标题优化、批量发货服务同步、批量退出哇噢定制、批量开启官方定制项。触发词：优化标题、修改标题、批量修改标题、同步发货服务、发货时间设置、批量设置发货、发货服务批量修改、退出哇噢定制、退出定制、设置官方定制项、批量开定制、包装定制。"
description_zh: "1688商品运营自动化技能 — AI标题优化 + 批量发货服务同步 + 批量退出哇噢定制 + 批量开启官方定制项"
description_en: "1688 product operations automation — AI title optimization + batch shipping service sync + batch exit waodingzhi + batch official customization enable"
version: 3.4.1
---

# 1688 商品运营自动化 Skill

> 基于 BrowserWing 浏览器自动化平台，实现 1688 后台商品的 AI 标题优化、批量发货服务同步、批量退出哇噢定制和批量开启官方定制项。

## v3.4.1 更新（运行防空转）

- 功能四新增：待设置数量连续两轮不下降时自动停机，避免重复空转同一批类目。
- 功能四增强：当下拉滚动容器出现 `NO_HOLDER` 时，会自动重新打开下拉并重试一次再判失败。

## v3.4.0 更新（稳定性增强）

- 功能四修复：包装定制下拉框作用域改为“当前激活类目”优先，避免跨类目残留弹层导致误判已选中。
- 功能四修复：包装项点击与滚动匹配改为可见下拉列表优先，降低虚拟列表 `listId` 波动导致的漏选概率。
- 运行时增强：验证码/登录等待支持非交互轮询，不再依赖 `input()`，避免 `EOF` 导致脚本退出。
- 运行时增强：新增 BrowserWing 会话存活检测，遇到 `evaluateFailed` 会明确报错并终止，避免假性卡死。

## 触发条件

当用户提到以下意图时触发此 Skill：
- "帮我优化 1688 商品标题"
- "修改商品标题"、"优化标题"
- "1688 标题 SEO"
- "批量修改标题"
- "同步发货服务"、"发货时间设置"
- "批量设置发货"、"发货服务批量修改"
- "退出哇噢定制"、"退出定制"、"批量退出哇噢定制"
- "设置官方定制项"、"批量开定制"
- "包装定制"、"批量设置包装定制"

## 前置要求

1. **BrowserWing 插件**：本 Skill 依赖 BrowserWing 浏览器自动化平台，执行任何业务操作前**必须先完成安装和启动**
2. **Node.js 环境**：BrowserWing 需要 Node.js 18+，需确保 `node` 和 `npm` 命令可用
3. **登录状态**：首次使用需要手动登录 1688，之后 Cookie 自动复用
4. **MCP 配置**：WorkBuddy 的 `mcp.json` 中已配置 browserwing 端点

---

### 〇、BrowserWing 安装检测与环境准备（每次运行必检）

> ⚠️ **此步骤是强制前置条件**。任何 Agent 在执行本 Skill 的业务流程之前，必须先完成以下检测。如果 BrowserWing 未安装或未运行，必须先安装并启动成功，否则不得继续业务操作。

> 🌐 **跨平台说明**：本 Skill 同时支持 macOS 和 Windows。下面同时给出两种系统的命令，Agent 应根据当前操作系统选择对应命令执行。判断方法：`process.platform === "darwin"` 为 macOS，`process.platform === "win32"` 为 Windows。

#### Step 0.1：检测 BrowserWing 是否已安装

**macOS / Linux：**
```bash
which browserwing 2>/dev/null && browserwing --version 2>/dev/null
```

**Windows（PowerShell）：**
```powershell
Get-Command browserwing -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source; browserwing --version
```

**Windows（CMD）：**
```cmd
where browserwing 2>nul && browserwing --version
```

**判断逻辑**：
- 命令存在且输出版本号 → 已安装，跳到 Step 0.2
- 命令不存在或报错 → 未安装，执行 Step 0.1a 自动安装

#### Step 0.1a：自动安装 BrowserWing

```bash
# 通用安装命令（macOS / Windows 通用）
npm install -g browserwing

# 验证安装
browserwing --version
```

> **安装备注**：
> - 确保 Node.js 18+ 和 npm 已安装。检测方式：`node --version && npm --version`
> - 如果 npm 不可用，尝试 `pnpm add -g browserwing` 或 `yarn global add browserwing`
> - **macOS 权限问题**：不要使用 `sudo`，而是使用 managed Node.js 的 npm 路径，例如：
>   `~/.workbuddy/binaries/node/versions/22.12.0/bin/npm install -g browserwing`
> - **Windows 权限问题**：以管理员身份打开终端执行，或确保 npm 全局目录在 PATH 中
> - 安装成功后 `browserwing` 命令应可在终端直接执行

#### Step 0.2：检测 BrowserWing 服务是否已运行

**方式1 — 直接请求 API（推荐，跨平台通用）：**
```bash
curl -s --connect-timeout 3 http://localhost:8080/api/v1/executor/help
```

> ⚠️ **Windows 注意**：如果系统没有 `curl` 命令，可使用 PowerShell 替代：
> ```powershell
> Invoke-WebRequest -Uri "http://localhost:8080/api/v1/executor/help" -TimeoutSec 3 -UseBasicParsing | Select-Object -ExpandProperty Content
> ```

**方式2 — 检查端口占用：**

macOS / Linux：
```bash
lsof -i :8080 2>/dev/null | head -5
```

Windows（PowerShell）：
```powershell
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
```

**判断逻辑**：
- API 返回 JSON 响应 → 服务已运行，跳到 Step 0.4
- 端口占用但 API 无响应 → 服务异常，先 kill 再重启
- 端口无占用且 API 无响应 → 服务未运行，执行 Step 0.3 启动

#### Step 0.3：启动 BrowserWing 服务

**macOS / Linux：**
```bash
# 清理可能残留的进程
lsof -ti :8080 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# 在临时目录启动（重要：避免数据库路径问题导致超时）
cd /tmp && nohup browserwing --port 8080 > /tmp/browserwing.log 2>&1 &

# 等待服务就绪（最多等待 10 秒）
for i in $(seq 1 10); do
  if curl -s --connect-timeout 2 http://localhost:8080/api/v1/executor/help 2>/dev/null | grep -q "navigate"; then
    echo "BrowserWing started (took ${i}s)"
    break
  fi
  sleep 1
done
```

**Windows（PowerShell）：**
```powershell
# 清理可能残留的进程
Get-Process -Name browserwing -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

# 在临时目录启动
$tempDir = [System.IO.Path]::GetTempPath()
Start-Process -FilePath "browserwing" -ArgumentList "--port 8080" -WorkingDirectory $tempDir -WindowStyle Hidden -RedirectStandardOutput "$tempDir\browserwing.log" -RedirectStandardError "$tempDir\browserwing_err.log"

# 等待服务就绪（最多等待 10 秒）
for ($i = 1; $i -le 10; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8080/api/v1/executor/help" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($resp.Content -match "navigate") {
            Write-Host "BrowserWing started (took ${i}s)"
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
}
```

> ⚠️ **启动注意事项**：
> - **必须在临时目录下运行**（macOS: `/tmp`，Windows: `%TEMP%`），否则可能因数据库路径问题导致超时
> - 默认端口 `8080`，如被占用需先关闭旧进程
> - macOS 使用 `nohup` 后台运行，Windows 使用 `Start-Process -WindowStyle Hidden`

#### Step 0.4：验证 BrowserWing 工作正常

```bash
# 跨平台通用验证命令
curl -s http://localhost:8080/api/v1/executor/help
```

**期望输出**：包含 `navigate`、`evaluate`、`click`、`screenshot` 等 API 端点列表的 JSON。

> ✅ **验证通过** → 可以开始执行业务流程（Step 1）
> ❌ **验证失败** → 检查日志（macOS: `/tmp/browserwing.log`，Windows: `%TEMP%\browserwing.log`），排查错误原因

#### Step 0.5：确认 MCP 配置（可选，首次使用检查）

检查 WorkBuddy 的 MCP 配置文件中是否已配置 BrowserWing MCP 端点。

**配置文件路径**：
- macOS: `~/.workbuddy/mcp.json`
- Windows: `%USERPROFILE%\.workbuddy\mcp.json`

**需要添加的配置**：
```json
{
  "mcpServers": {
    "browserwing": {
      "type": "http",
      "url": "http://localhost:8080/api/v1/mcp/message"
    }
  }
}
```

如果配置缺失，需要添加上述配置。MCP 端点提供 `browser_click`、`browser_navigate` 等高级操作能力，REST API 则提供更灵活的底层控制。本 Skill 主要使用 REST API。

#### 完整检测流程图

```
开始
  │
  ├─ Step 0.1: browserwing 已安装？
  │    ├─ 否 → Step 0.1a: npm install -g browserwing
  │    │        → 安装失败？→ 报错终止，提示用户手动安装
  │    └─ 是 ↓
  │
  ├─ Step 0.2: BrowserWing 服务运行中？
  │    ├─ 否 → Step 0.3: 在临时目录启动 browserwing --port 8080
  │    │        → 启动失败？→ 查看临时目录下的 browserwing.log
  │    └─ 是 ↓
  │
  ├─ Step 0.4: API 验证通过？
  │    ├─ 否 → 检查日志，尝试重启
  │    └─ 是 ✅
  │
  └─ 进入业务流程 Step 1
```

---

## 完整操作流程

> 📌 **以下所有 API 调用通过 BrowserWing REST API 执行**，核心端点为 `http://localhost:8080/api/v1/executor`。所有 `curl` 命令在 macOS 和 Windows（Git Bash / WSL）下通用。Windows 原生 CMD 用户请注意：CMD 不支持单引号，需将 `-d '...'` 中的单引号改为双引号，并将内部双引号转义为 `\"`。

### Step 1：导航到商品管理列表页

```
POST http://localhost:8080/api/v1/executor/navigate
```

**请求体**：
```json
{
  "url": "https://offer.1688.com/offer/manage.htm?show_type=valid",
  "wait_until": "load",
  "timeout": 30
}
```

**curl 示例**：
```bash
curl -s -X POST "http://localhost:8080/api/v1/executor/navigate" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://offer.1688.com/offer/manage.htm?show_type=valid\", \"wait_until\": \"load\", \"timeout\": 30}"
```

**关键 URL**：
- 商品管理列表：`https://offer.1688.com/offer/manage.htm?show_type=valid`
- 商品编辑页（新）：`https://offer-new.1688.com/popular/publish.htm?id={offerId}&operator=edit`

> ⚠️ 注意：旧 URL `p.1688.com/pmsOffer/offerList.htm` 已 404，不要使用。
> ⚠️ 工作台 `work.1688.com` 使用 iframe 嵌套商品列表，BrowserWing 无法直接操作 iframe 内元素。

### Step 1.5：检查登录状态

**请求体**（发送至 `/evaluate` 端点）：
```json
{
  "script": "() => { return JSON.stringify({ url: location.href, text: document.body ? document.body.innerText.substring(0, 300) : 'no body' }); }"
}
```

如果页面显示"请登录"或跳转到登录页：
- 暂停流程，引导用户在 BrowserWing 控制的浏览器窗口中手动登录
- 登录成功后重新导航到商品列表

### Step 1.8：验证码/风控检测（每步操作后执行）

在**每个关键操作后**都执行验证码检测。如果检测到验证码元素且可见，立即暂停流程并提示用户手动处理。

**检测脚本**（发送至 `/evaluate` 端点）：
```javascript
() => {
  const captchaSelectors = [
    ".nc_wrapper", "#nc_1__wrapper", "[id*=nocaptcha]", "[class*=nocaptcha]",
    "[class*=slider-captcha]", "[class*=captcha]", "[class*=verify]",
    "[class*=slider-track]", "[class*=aliyun-captcha]", ".no-captcha",
    "#nc_1_wrapper", "[class*=risk]", "[class*=security-check]"
  ];
  let captchaFound = [];
  captchaSelectors.forEach(sel => {
    try {
      document.querySelectorAll(sel).forEach(el => {
        if (el.offsetParent !== null) captchaFound.push(sel);
      });
    } catch(e) {}
  });
  if (captchaFound.length > 0) {
    return JSON.stringify({ captcha: true, selectors: captchaFound });
  }
  return JSON.stringify({ captcha: false });
}
```

**处理策略**：检测到验证码时 → 暂停自动化 → 提示用户在 BrowserWing 浏览器窗口中手动完成验证 → 用户确认后继续流程。

### Step 2：搜索目标商品

> ⚠️ 商品管理列表页也使用 React，搜索框必须用 `nativeInputValueSetter` 填入关键词，否则值会被清空。

**搜索脚本**（发送至 `/evaluate` 端点）：
```javascript
() => {
  // React 兼容方式填入搜索关键词
  const input = document.querySelector("#keyword");
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  nativeSetter.call(input, "搜索关键词");
  input.dispatchEvent(new Event("input", {bubbles: true}));
  input.dispatchEvent(new Event("change", {bubbles: true}));
  input.dispatchEvent(new Event("compositionend", {bubbles: true}));

  // 点击搜索按钮
  const btn = document.querySelector("button.simple-search__submit-btn");
  btn.click();
  return "搜索已执行";
}
```

等待 3-4 秒后截图确认搜索结果，并执行 Step 1.8 验证码检测。

### Step 3：定位目标商品

搜索后从页面中提取商品信息：

**提取商品列表脚本**（发送至 `/evaluate` 端点）：
```javascript
() => {
  const allLinks = document.querySelectorAll("a");
  const items = [];
  allLinks.forEach(a => {
      const href = a.href || "";
      if (href.includes("detail.1688.com/offer/")) {
          items.push({
              text: a.innerText.trim().substring(0, 80),
              href: href,
              offerId: href.match(/offer\/(\d+)/) ? href.match(/offer\/(\d+)/)[1] : ""
          });
      }
  });
  return JSON.stringify(items);
}
```

让用户选择目标商品后，使用导航 API 直接跳转到编辑页（无需点击"修改详情"按钮）：

**直接导航到编辑页**（推荐方式，更可靠）：
```
POST http://localhost:8080/api/v1/executor/navigate
```
```json
{
  "url": "https://offer-new.1688.com/popular/publish.htm?id={offerId}&operator=edit",
  "wait_until": "load",
  "timeout": 30
}
```

### Step 4：进入编辑页面

编辑页 URL 格式：
```
https://offer-new.1688.com/popular/publish.htm?id={offerId}&operator=edit
```

> ⚠️ 旧格式 `offer.1688.com/offer/post/fill_product_info.vm?operator=edit&offerId={offerId}` 会自动跳转到新格式，建议直接使用新格式。

等待 5 秒让页面完全加载后，截图确认。

### Step 5：提取原标题

**提取标题脚本**（发送至 `/evaluate` 端点）：
```javascript
() => {
  const inputs = document.querySelectorAll("input");
  for (const input of inputs) {
      if (input.value && input.value.length > 10 && input.type === "text") {
          if (input.placeholder && input.placeholder.includes("建议使用")) {
              return input.value;  // 这就是原标题
          }
      }
  }
  return "TITLE_NOT_FOUND";
}
```

### Step 6：AI 优化标题

基于原标题和 1688 SEO 最佳实践生成优化标题：

**优化规则**：
1. **关键词前置**：将核心搜索词放在标题最前面
2. **空格分词**：用空格分隔不同关键词组，提升搜索分词效果
3. **覆盖搜索场景**：包含同义词、关联搜索词（如"解压球"→"减压神器"+"发泄球"）
4. **去除冗余**：删除重复概念和不重要的修饰词
5. **增加场景词**：补充使用场景（如"办公室""桌面""情绪释放"）
6. **避免违规词**：不含"最""第一""绝对"等极限词
7. **标题长度**：控制在 60 个字符以内（1688 标题限制）

**Prompt 模板**：
```
你是一个 1688 商品标题 SEO 优化专家。请基于以下原标题生成优化标题。

原标题：{originalTitle}

优化要求：
1. 关键词前置，核心搜索词放最前
2. 用空格分隔关键词组
3. 覆盖买家可能的搜索词和关联词
4. 去除冗余修饰
5. 增加使用场景词
6. 避免极限词（最、第一等）
7. 标题不超过 60 字符

输出格式：
- 优化标题：xxx
- 优化说明：xxx（简要说明做了哪些改动和原因）
```

**让用户确认**优化标题后再执行修改。

### Step 7：填入新标题（React 兼容方式）

1688 编辑页使用 React 框架，普通 `input.value = xxx` 不会触发 React 状态更新。必须使用 `nativeInputValueSetter`。

**填入标题脚本**（发送至 `/evaluate` 端点）：
```javascript
() => {
  const inputs = document.querySelectorAll("input");
  for (const input of inputs) {
      if (input.value === "原标题内容") {
          const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
              window.HTMLInputElement.prototype, "value"
          ).set;
          nativeInputValueSetter.call(input, "新的优化标题");
          input.dispatchEvent(new Event("input", {bubbles: true}));
          input.dispatchEvent(new Event("change", {bubbles: true}));
          input.dispatchEvent(new Event("compositionend", {bubbles: true}));
          return "标题已修改: " + input.value;
      }
  }
  return "未找到标题输入框";
}
```

> ⚠️ **关键提醒**：必须将脚本中的 `"原标题内容"` 替换为 Step 5 提取到的实际原标题，将 `"新的优化标题"` 替换为 Step 6 确认的优化标题。

### Step 8：提交保存

**提交脚本**（发送至 `/evaluate` 端点）：
```javascript
() => {
  // 滚动到底部
  window.scrollTo(0, document.body.scrollHeight);

  // 点击提交按钮
  const btn = document.querySelector("button.submit-buttom-action");
  if (!btn) return "SUBMIT_BTN_NOT_FOUND";
  btn.click();
  return "已点击提交";
}
```

等待 3 秒，检查页面标题是否变为"商品发布成功"。

---

## 页面元素定位参考

### 商品管理列表页

| 元素 | 定位方式 | 备注 |
|------|---------|------|
| 搜索框 | `#keyword` | placeholder: "产品标题/货号" |
| 商品ID输入 | `#filterOfferId` | |
| 搜索按钮 | `.simple-search__submit-btn` | |
| 修改详情按钮 | `a[href*=offerId]` 且文本="修改详情" | 每行一个 |
| 商品标题 | `a[href*="detail.1688.com/offer/"]` | |

### 商品编辑页（新）

| 元素 | 定位方式 | 备注 |
|------|---------|------|
| 标题输入框 | 匹配 `value` 包含原标题的 `input[type=text]` | React 组件，需用 nativeInputValueSetter |
| 提交按钮 | `button.submit-buttom-action` | 文本："同意协议条款，我要发布" |
| 保存草稿 | `a.link` 且文本="保存草稿" | |

---

## 错误处理

### 验证码/风控触发
- **检测时机**：每个关键操作后（导航、搜索、跳转、提交）都执行 Step 1.8 检测
- **检测方式**：扫描页面中 13 个常见验证码选择器是否可见
- **处理**：暂停自动化 → 提示用户在 BrowserWing 浏览器中手动完成 → 用户确认后继续

### 登录过期
- **检测**：页面包含"请登录"或跳转到登录页
- **处理**：暂停流程，引导用户在 BrowserWing 浏览器窗口中重新登录

### 提交失败
- **检测**：页面标题不是"商品发布成功"
- **处理**：截图查看错误信息，可能原因：
  - 标题含违规词（含"最""第一"等极限词）
  - 必填项未填写
  - 网络超时

### 页面加载超时
- **检测**：`document.readyState` 不是 "complete" 或 body 文本长度为 0
- **处理**：增加等待时间，刷新页面重试

### Cookie 失效
- **检测**：直接访问 `offer.1688.com` 显示"请登录"
- **处理**：需要重新从工作台获取 Cookie（导航到 `work.1688.com`，手动登录后重试）

---

## 批量操作流程（Agent 引导式）

对于批量标题优化，Agent 按以下步骤引导：

1. 获取商品列表（搜索或遍历）
2. 逐个进入编辑页
3. 提取原标题 → AI 优化 → 填入 → 提交
4. 每个商品操作后截图记录
5. 记录修改日志（时间、原标题、新标题、结果）

### 批量脚本（全自动）

本 Skill 包含 Python 批量脚本 `batch_title_optimizer.py`，实现三阶段全自动流程：

```
Phase 1 扫描：遍历商品列表，提取 offerId + 标题 → 导出 CSV
Phase 2 优化：调用 Qwen AI 批量生成优化标题 → 导出 CSV
Phase 3 执行：预览对照表 → 用户确认 → 逐个进入编辑页修改并提交
```

**运行方式**：
```bash
# macOS / Linux
python3 batch_title_optimizer.py                    # 完整三阶段流程
# Windows
python batch_title_optimizer.py
```

**常用参数**：

| 参数 | 说明 |
|------|------|
| （无参数） | 完整流程：扫描 → AI 优化 → 预览确认 → 执行 |
| `--scan-only` | 只扫描导出 CSV，不优化不执行 |
| `--count 20` | 只处理前 20 个商品 |
| `--keyword 解压球` | 先搜索关键词再扫描 |
| `--import titles.csv` | 导入已有优化结果 CSV，直接执行 |

**CSV 导入导出**：
- `--scan-only` 导出扫描结果 CSV（可用 Excel 编辑）
- 在 Excel 中手动填写 `optimizedTitle` 列后，用 `--import` 导入执行
- 适合需要人工审核优化标题的场景

**脚本特性**：
- ✅ 三阶段流程（扫描 → 优化 → 确认执行），安全可控
- ✅ Qwen AI 自动生成 SEO 优化标题（模型可配置）
- ✅ 支持关键词搜索 + 全量扫描 + 翻页遍历
- ✅ CSV 导入导出（Excel 友好，UTF-8-BOM）
- ✅ 编辑页标题匹配验证（防止误改）
- ✅ 验证码检测（检测到则暂停，提示手动处理）
- ✅ 登录状态检测
- ✅ 连续错误保护（连续 5 次错误自动终止）
- ✅ 执行日志记录（logs/title_optimizer_*.log）

**AI 配置**（环境变量）：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `QWEN_API_KEY` | `sk-37d3...` | DashScope API Key |
| `QWEN_MODEL` | `qwen-plus` | 模型名称（qwen-plus/qwen-turbo/qwen-max） |

> ⚠️ **与功能二/三共享 BrowserWing 环境**，不需要额外安装或停止服务。

---

## API 快速参考

所有操作通过 BrowserWing Executor API 执行：

```
基础 URL: http://localhost:8080/api/v1/executor
```

| 方法 | 端点 | 用途 |
|------|------|------|
| GET | `/help` | 查看所有可用命令 |
| GET | `/snapshot` | 获取页面结构 + RefID |
| POST | `/navigate` | 导航到 URL |
| POST | `/evaluate` | 执行 JavaScript（最常用） |
| POST | `/screenshot` | 截图 |
| POST | `/click` | 点击元素 |
| POST | `/type` | 输入文本 |
| POST | `/wait` | 等待 |
| POST | `/reload` | 刷新页面 |
| GET | `/page-info` | 获取页面信息 |

---

## 功能二：批量同步发货服务

> 自动遍历所有商品，将"服务与承诺 → 发货服务"中的购买数量区间和发货时间统一为目标配置值。

### 触发条件

- "同步发货服务"、"发货时间设置"
- "批量设置发货"、"发货服务批量修改"

### 工作流程

```
1. 读取配置文件 → 获取目标发货时间和数量区间
2. 导航到商品管理列表（含翻页遍历全部商品）
3. 对每个商品：
   a. 进入编辑页 → 滚动到"服务与承诺"区域
   b. 提取当前发货服务表格值（2行 × 发货时间 + 数量区间）
   c. 与目标值比对 → 匹配则跳过，不匹配则修改
   d. 修改：使用 React Fiber onChange 直调设置发货时间（核心方法）
   e. 滚动到底部 → 点击提交按钮
   f. 截图记录（修改前/修改后/跳过）
4. 输出汇总报告（总数/修改/跳过/失败）
```

### 配置文件说明

`shipping_target_config.json` — 运行前修改此文件即可自定义所有参数：

```json
{
  "_说明": "运行前修改此文件的 target 部分即可自定义发货服务参数",
  "target": {
    "row1": {
      "min_qty": "1",
      "max_qty": "2",
      "ship_time": "48小时发货",
      "ship_time_code": "ssbxsfh",
      "description": "第1行：1~2件 承诺48小时发货"
    },
    "row2": {
      "min_qty": "3",
      "max_qty": "",
      "max_qty_label": "库存上限（留空表示不限）",
      "ship_time": "72小时发货",
      "ship_time_code": "essebsfh",
      "description": "第2行：3件以上 承诺72小时发货"
    }
  }
}
```

**可选的发货时间**（1688 下拉框选项及内部编码）：

| 显示文本 | 内部值编码 |
|---------|-----------|
| 当日发 | `drfh` |
| 24小时发货 | `essxsfh` |
| 48小时发货 | `ssbxsfh` |
| 72小时发货 | `essebsfh` |
| 7天发货 | `qtfh` |
| 10天发货 | `sytffh` |
| 15天发货 | `swtffh` |
| 20天发货 | `esttffh` |
| 30天发货 | `ssttffh` |
| 45天发货 | `sswttfh` |

> ⚠️ **修改发货时间时必须使用内部值编码**（如 `ssbxsfh`），不是显示文本（如"48小时发货"）。配置文件中 `ship_time_code` 字段即为内部编码，`ship_time` 字段仅供人工阅读。

### 关键技术要点

#### Ant Design Select 下拉框操作 — React Fiber onChange 直调

1688 编辑页使用 Ant Design 组件库，其 select 下拉框通过 React Portal 渲染，**无法通过普通 JS `click()`、`MouseEvent`、PointerEvent 或 REST API click 触发**。唯一可靠的方法是通过 React Fiber 树找到 Select 组件的 `onChange` 并直接调用。

> ✅ **最佳方案（2026-04-10 验证通过）**：React Fiber onChange 直调，不需要点击下拉框，通过 `/evaluate` API 即可完成。

**修改发货时间脚本**（发送至 `/evaluate` 端点）：

```javascript
() => {
  // === 修改第 N 行发货时间 ===
  // 参数说明：
  //   rowIndex = 1 或 2（表格行号，从1开始）
  //   valueCode = 内部值编码（见上方对照表，如 "ssbxsfh" = 48小时发货）

  var rowIndex = 1;  // ← 修改此处：1=第1行，2=第2行
  var valueCode = "ssbxsfh";  // ← 修改此处：目标发货时间编码

  // --- 以下不需要修改 ---

  // 内部值编码 → 显示文本
  var labels = {
    "drfh": "当日发",
    "essxsfh": "24小时发货",
    "ssbxsfh": "48小时发货",
    "essebsfh": "72小时发货",
    "qtfh": "7天发货",
    "sytffh": "10天发货",
    "swtffh": "15天发货",
    "esttffh": "20天发货",
    "ssttffh": "30天发货",
    "sswttfh": "45天发货"
  };
  var label = labels[valueCode] || valueCode;

  // 定位发货服务表格中的 select 元素
  var rows = document.querySelectorAll("table tbody tr");
  var targetRow = rows[rowIndex - 1];
  if (!targetRow) return "ROW_NOT_FOUND: row " + rowIndex;

  var selectEl = targetRow.querySelector(".ant-select");
  if (!selectEl) return "SELECT_NOT_FOUND in row " + rowIndex;

  // 获取 React 内部实例（React 16 使用 __reactInternalInstance$）
  var instKey = Object.keys(selectEl).find(function(k) { return k.startsWith("__reactInternalInstance$"); });
  if (!instKey) return "NO_REACT_INSTANCE";

  var inst = selectEl[instKey];
  var f = inst;

  // 遍历 Fiber 树查找 onChange
  while (f) {
    var props = f._currentElement ? f._currentElement.props : (f.memoizedProps || null);
    if (props && typeof props.onChange === "function") {
      props.onChange(valueCode, { key: valueCode, label: label, value: valueCode, children: label });
      return "OK: row " + rowIndex + " set to " + label;
    }
    f = f._hostParent || f.return || f.stateNode;
  }
  return "ONCHANGE_NOT_FOUND";
}
```

> ⚠️ **使用方法**：将上述脚本中的 `rowIndex` 和 `valueCode` 替换为实际需要的值，然后通过 `/evaluate` 端点发送。每次调用只能修改一行，如需修改两行，需调用两次。

**提取当前发货服务值**（发送至 `/evaluate` 端点）：

```javascript
() => {
  var rows = document.querySelectorAll("table tbody tr");
  var result = [];
  for (var i = 0; i < 2 && i < rows.length; i++) {
    var row = rows[i];
    // 从 select 的当前显示值获取发货时间
    var selectEl = row.querySelector(".ant-select-selection-item");
    var shipTime = selectEl ? selectEl.innerText.trim() : "";
    // 从 input 获取数量
    var inputs = row.querySelectorAll("input");
    var minQty = inputs[0] ? inputs[0].value.trim() : "";
    var maxQty = inputs[1] ? inputs[1].value.trim() : "";
    result.push({ row: i + 1, shipTime: shipTime, minQty: minQty, maxQty: maxQty });
  }
  return JSON.stringify(result);
}
```

> ⚠️ **为什么不使用 click 方法？**
> - Ant Design 5.x 的 Select 下拉框通过 React Portal 渲染到 `document.body`
> - REST API `/click` 无法触发 Portal 层的 dropdown 展开逻辑
> - JS `el.click()`、`new MouseEvent()`、`dispatchEvent(mousedown→mouseup→click)` 均无法使 dropdown 出现
> - 只有 MCP `browser_click` 偶尔能触发，但极其不稳定
> - **React Fiber onChange 直调** 完美绕过 dropdown，不依赖任何 click 操作

#### 翻页机制

1688 商品列表使用 Fusion Design 分页组件：
- 分页信息：`.next-pagination-display`
- 下一页按钮：`button.next-pagination-item.next`
- 最后一页时按钮 `disabled` 属性为 true

#### 发货服务表格定位

通过文本匹配找到包含"发货时间"和"购买数量"的 table 元素，然后按 `tbody tr` 提取两行数据。

#### 滚动到发货服务区域

**滚动脚本**（发送至 `/evaluate` 端点）：
```javascript
() => {
  // 方式1：点击左侧导航"服务与承诺"
  var links = document.querySelectorAll("a,span,div");
  for (var i = 0; i < links.length; i++) {
    if (links[i].innerText.trim() === "服务与承诺" && links[i].offsetParent !== null) {
      links[i].scrollIntoView({behavior: "auto", block: "center"});
      links[i].click();
      break;
    }
  }
  return "nav_clicked";
}
```

等待 1 秒后再滚动到表格：
```javascript
() => {
  var tables = document.querySelectorAll("table");
  for (var i = 0; i < tables.length; i++) {
    if (tables[i].innerText.includes("发货时间") && tables[i].innerText.includes("购买数量")) {
      tables[i].scrollIntoView({behavior: "auto", block: "center"});
      return "scrolled_to_table";
    }
  }
  return "table_not_found";
}
```

### 批量脚本

本 Skill 包含一个 Bash 批量脚本 `batch_shipping_sync.sh`，可在 macOS/Linux 上直接运行。

> ⚠️ **Windows 用户注意**：此脚本为 Bash 脚本，无法在 Windows CMD/PowerShell 中直接运行。Windows 用户有两种选择：
> 1. **使用 WSL（推荐）**：在 Windows Subsystem for Linux 中运行该脚本
> 2. **手动执行**：参照上方"工作流程"和"关键技术要点"，通过 BrowserWing REST API 逐步操作。Agent 可直接读取 `shipping_target_config.json` 获取目标配置，然后逐个商品调用 `/evaluate` 端点执行修改。

**macOS / Linux 运行方式**：
```bash
# 1. 编辑配置文件，设置目标发货时间和数量区间
vim shipping_target_config.json

# 2. 运行批量脚本
chmod +x batch_shipping_sync.sh && ./batch_shipping_sync.sh
```

### 目录结构

```
1688_title_optimizer/
├── SKILL.md                              # 本文档（Skill 说明）
├── shipping_target_config.json           # 发货服务目标配置（运行前编辑）
├── batch_shipping_sync.sh                # 批量同步脚本（仅 macOS/Linux）
├── screenshots/
│   └── batch_shipping/                   # 批量操作截图
│       ├── {offerId}_before.png
│       ├── {offerId}_after.png
│       └── {offerId}_skip.png
└── logs/
    └── batch_shipping_{timestamp}.log    # 执行日志
```

---

## 功能三：批量退出哇噢定制

> 自动遍历"已加入哇噢定制"商品列表，逐个悬停问号图标 → 点击"退出哇噢定制"按钮 → 确认退出，直到列表清空。

### 触发条件

- "退出哇噢定制"、"退出定制"
- "批量退出哇噢定制"

### 🔑 关键技术突破（2026-04-11 验证通过）

哇噢定制页面原本使用**双层嵌套 iframe**：

```
work.1688.com (主页面)
  └─ iframe.jhook-harmony-iframe (同域：work.1688.com)
       └─ iframe.invoice-container (跨域：sale.1688.com) ← 实际内容
```

**关键发现：直接导航 `https://sale.1688.com/factory/ossdql9d.html` 可完全绕过 iframe 限制！** BrowserWing 的 `evaluate` 可以直接操作 DOM，无需穿透跨域 iframe。

> ✅ **首选方案（推荐）**：BrowserWing REST API + Bash 脚本（`exit_waodingzhi.sh`），无需额外依赖
> ⚙️ **备选方案**：Playwright Python 脚本（`exit_waodingzhi.py`），需额外安装 Playwright

### 首选方案：BrowserWing REST API

#### 操作原理

| 步骤 | 方法 | 说明 |
|------|------|------|
| 1. 导航 | `/navigate` | 直接导航到 `sale.1688.com/factory/ossdql9d.html` |
| 2. 检测列表 | `/evaluate` | 检查 `tbody tr` 行数，0 行则结束 |
| 3. 悬停触发 | `/evaluate` | React Fiber `onMouseEnter` 直调（唯一可靠方法） |
| 4. 点击退出 | `/evaluate` | 点击 `.my-ant-btn.my-ant-btn-primary` |
| 5. 确认退出 | `/evaluate` | 点击 `.next-dialog .next-btn-primary` |
| 6. 等待刷新 | `sleep` | 等待商品从列表移除 |

#### React Fiber onMouseEnter 直调

问号图标使用 React 组件，`dispatchEvent` 无法触发 React 合成事件。必须通过 `__reactFiber$` 遍历 Fiber 树找到 `onMouseEnter` 并直接调用：

```javascript
// 找到第一行商品的问号图标
var imgs = document.querySelectorAll('img[style*="cursor"]');
var target = null;
for (var i = 0; i < imgs.length; i++) {
    var r = imgs[i].getBoundingClientRect();
    if (r.top > 300 && r.left > 1500) { target = imgs[i]; break; }
}

// 遍历 React Fiber 树找到 onMouseEnter
var fiberKey = Object.keys(target).find(function(k) {
    return k.indexOf("__reactFiber$") === 0;
});
var fiber = target[fiberKey];
var el = fiber;
while (el) {
    var p = el.memoizedProps || el.pendingProps || {};
    if (p.onMouseEnter) {
        p.onMouseEnter({
            currentTarget: target, target: target,
            type: 'mouseenter',
            clientX: target.getBoundingClientRect().left + 8,
            clientY: target.getBoundingClientRect().top + 8
        });
        break;  // depth 通常为 2
    }
    el = el.return;
}
```

#### 批量脚本

**脚本文件**：`exit_waodingzhi.sh`

**运行方式**：

macOS / Linux：
```bash
chmod +x exit_waodingzhi.sh && ./exit_waodingzhi.sh
```

> ⚠️ **Windows 用户注意**：此脚本为 Bash 脚本，无法在 Windows CMD/PowerShell 中直接运行。Windows 用户有两种选择：
> 1. **使用 WSL（推荐）**：在 Windows Subsystem for Linux 中运行该脚本
> 2. **使用备选方案**：运行 `exit_waodingzhi.py`（Playwright Python 版，跨平台）

**脚本特性**：
- ✅ 基于 BrowserWing REST API（无需额外依赖，与功能一、二共享同一环境）
- ✅ 直接导航绕过 iframe 限制
- ✅ React Fiber onMouseEnter 直调触发弹出菜单
- ✅ 验证码检测（检测到则暂停，提示用户手动处理）
- ✅ 连续错误保护（连续 5 次错误自动终止）
- ✅ 最大退出数量限制（默认 500 件，防止死循环）
- ✅ 操作间隔控制（每个操作间隔 2 秒，避免触发风控）
- ✅ 结果截图保存
- ✅ 执行日志记录

**脚本参数**（脚本顶部可自定义）：

```bash
ACTION_DELAY=2          # 每次退出后等待（秒）
HOVER_WAIT=1            # hover 后等待弹出菜单（秒）
CONFIRM_WAIT=1          # 点击退出后等待确认弹窗（秒）
REFRESH_WAIT=3          # 退出后等待列表刷新（秒）
MAX_EXIT_COUNT=500      # 最大退出数量限制
MAX_CONSECUTIVE_ERRORS=5  # 连续错误上限
```

#### Agent 直接操作方式

如果不使用脚本，Agent 可按以下步骤通过 BrowserWing REST API 逐步操作：

**Step 1：导航到哇噢定制页面**
```bash
curl -s -X POST "http://localhost:8080/api/v1/executor/navigate" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://sale.1688.com/factory/ossdql9d.html", "wait_until": "load", "timeout": 30}'
```

**Step 2：检查列表状态**
```javascript
() => { var rows = document.querySelectorAll("tbody tr"); if (rows.length === 0) return "EMPTY"; var firstText = rows[0].innerText; if (firstText.indexOf("暂无") >= 0) return "EMPTY"; return "HAS_ITEMS:" + rows.length; }
```

**Step 3：悬停触发 + 退出 + 确认**（一次 evaluate 完成全流程）
```javascript
() => {
  // Hover
  var imgs = document.querySelectorAll('img[style*="cursor"]');
  var target = null;
  for (var i = 0; i < imgs.length; i++) {
    var r = imgs[i].getBoundingClientRect();
    if (r.top > 300 && r.left > 1500) { target = imgs[i]; break; }
  }
  if (!target) return "ICON_NOT_FOUND";
  var fiberKey = Object.keys(target).find(function(k) { return k.indexOf("__reactFiber$") === 0; });
  var fiber = target[fiberKey];
  var el = fiber;
  while (el) {
    var p = el.memoizedProps || el.pendingProps || {};
    if (p.onMouseEnter) { p.onMouseEnter({ currentTarget: target, target: target, type: "mouseenter" }); break; }
    el = el.return;
  }
  // Click exit (需要单独调用，等 popup 出现后)
  return "HOVER_OK";
}
```

> ⚠️ **注意**：hover、点击退出、确认退出必须分 3 次 evaluate 调用，中间需要 `sleep` 等待 UI 响应。

---

### 备选方案：Playwright Python

> 当 BrowserWing 方案不可用（如 sale.1688.com 直连被限制）时，可使用 Playwright Python 脚本。

**前置依赖：Playwright Python**

**macOS / Linux：**
```bash
python3 -c "from playwright.sync_api import sync_playwright; print('OK')" 2>/dev/null || echo "NOT_INSTALLED"
pip3 install playwright && python3 -m playwright install chromium
```

**Windows（PowerShell）：**
```powershell
python -c "from playwright.sync_api import sync_playwright; print('OK')" 2>$null
if ($LASTEXITCODE -ne 0) { pip install playwright; python -m playwright install chromium }
```

**运行方式**：
```bash
# macOS / Linux
python3 exit_waodingzhi.py
# Windows
python exit_waodingzhi.py
```

> ⚠️ **重要**：Playwright 版脚本复用 BrowserWing 的 Chrome 用户数据目录，运行时需先停止 BrowserWing。
>
> **操作步骤**：
> 1. 先停止 BrowserWing（`lsof -ti :8080 | xargs kill`）
> 2. 运行 `exit_waodingzhi.py`
> 3. 完成后重新启动 BrowserWing

---

### 页面结构分析（2026-04-10/11 实测）

**页面 URL**：`https://sale.1688.com/factory/ossdql9d.html`（直接导航，绕过 iframe）

**关键元素**：

| 元素 | 选择器/定位方式 | 备注 |
|------|---------------|------|
| 商品行 | `tbody tr` | 每行代表一个已加入的商品 |
| 问号图标 | `img[style*='cursor']` + `top>300, left>1500` | 入驻时间列 |
| React Fiber | `__reactFiber$` 属性 | depth=2 有 `onMouseEnter` |
| 弹出菜单 | `.next-balloon` | Fusion Design Balloon 组件 |
| "退出哇噢定制"按钮 | `.my-ant-btn.my-ant-btn-primary` | 在弹出菜单中 |
| 确认弹窗 | `.next-dialog.next-dialog-v2` | 含"您确定退出哇噢定制么" |
| 确定按钮 | `.next-btn-primary` | 在 `.next-dialog` 内 |
| 空列表状态 | `暂无` 文本或 0 行 | 所有商品退出后显示 |

### 目录结构更新

```
1688_title_optimizer/
├── SKILL.md                              # 本文档（Skill 说明）v3.3
├── batch_title_optimizer.py              # 批量 AI 标题优化脚本（功能一）
├── shipping_target_config.json           # 发货服务目标配置（功能二）
├── batch_shipping_sync.sh                # 批量同步发货服务脚本（功能二，仅 macOS/Linux）
├── exit_waodingzhi.py                    # 批量退出哇噢定制脚本（功能三首选，跨平台）
├── exit_waodingzhi.sh                    # 批量退出哇噢定制脚本（功能三备选，仅 macOS/Linux）
├── batch_official_customize_enable.py    # 批量开启官方定制项脚本（功能四主实现，跨平台）
├── batch_official_customize_enable.sh    # 功能四 Bash 入口（macOS/Linux）
├── screenshots/
│   ├── batch_shipping/                   # 功能二截图
│   └── exit_waodingzhi/                  # 功能三截图
│       ├── before_exit.png
│       └── after_exit.png
│   └── official_customize/               # 功能四截图
└── logs/
    ├── title_optimizer_{timestamp}.log   # 功能一执行日志
    ├── batch_shipping_{timestamp}.log    # 功能二执行日志
    ├── exit_waodingzhi_{timestamp}.log   # 功能三执行日志
    └── official_customize_{timestamp}.log # 功能四执行日志
```

---

## 功能四：批量开启官方定制项

> 自动进入「找工厂 → 设置官方定制项」，在“待设置”列表中逐轮处理商品，并为每个类目补齐“包装定制”四个固定选项，然后确认报价并保存当前类目。

### 触发条件

- "设置官方定制项"
- "批量开定制"
- "批量设置包装定制"
- "官方定制项批量设置"

### 工作流程

```
1. 打开 1688 商家后台
2. 点击“找工厂”栏目中的“设置官方定制项”
3. 切换到“待设置”标签，检查是否存在商品
4. 若有商品则点击“下一步”进入类目设置页
5. 采集顶部全部类目标签（含“更多/展开”里的隐藏标签）
6. 对每个类目：
   a. 查找“包装定制”字段
   b. 不存在则跳过当前类目
   c. 存在则补齐四个固定选项（去重，不重复选择）
   d. 点击“确定，去设置报价”
   e. 在弹窗中点击“确定”
   f. 点击“保存XXXX的定制项”
7. 当前轮次全部类目完成后返回“待设置”列表
8. 重复执行，直到“待设置”为空
```

### 固定包装定制项

- `手工贴标 +0.3 3件起定`
- `塑封 +0.2 3件起定`
- `OPP袋 +0.2 3件起定`
- `气泡袋 +0.25 3件起定`

> ⚠️ 本功能将上述 4 个选项写死在脚本常量中。脚本会先读取当前已选项，再只补齐缺失项，不会重复点击相同选项。

### 技术要点

- 浏览器自动化主流程全部通过 BrowserWing REST API 执行：`/navigate`、`/evaluate`、`/screenshot`
- 为避免新页签切换不稳定，入口点击优先提取链接并使用 BrowserWing 原地导航
- 类目采集支持“更多 / 展开 / 更多类目”等入口，尽量覆盖隐藏标签
- 类目保存、待设置检测、报价确认均返回稳定状态码，便于日志和后续排错
- Bash 脚本是 macOS/Linux 入口封装，内部直接调用同目录 Python 主实现，以确保两种入口共享完全一致的 BrowserWing 流程

### 运行方式

**Python 主实现（推荐，跨平台）**

```bash
python3 batch_official_customize_enable.py
python3 batch_official_customize_enable.py --max-rounds 50 --delay 2
```

**Bash 入口（macOS / Linux）**

```bash
chmod +x batch_official_customize_enable.sh && ./batch_official_customize_enable.sh
```

### 可用参数

```bash
BW_PORT=8080
ACTION_DELAY=2
PAGE_LOAD_WAIT=8
MAX_ROUNDS=200
MAX_CONSECUTIVE_ERRORS=5
```

### 统计输出

- `ROUND_TOTAL`
- `CATEGORY_TOTAL`
- `CATEGORY_SUCCESS`
- `CATEGORY_SKIPPED`
- `CATEGORY_FAILED`
- `PENDING_REMAINING`

---

## 验证记录

### 2026-04-08 首次验证通过 ✅

- **BrowserWing 端口**：8080
- **测试商品**：粉色压力球慢回弹治愈系捏捏乐（Offer ID: 1038703145429）
- **原标题**：粉色压力球慢回弹治愈系捏捏乐办公室桌面休闲摆件解压神器玩具
- **优化标题**：慢回弹捏捏乐解压球 粉色治愈系减压神器 办公室桌面趣味休闲玩具 情绪释放发泄球
- **结果**：提交成功，商品进入审核状态

### 2026-04-08 第二次验证通过 ✅（含验证码检测强化测试）

- **目标**：全流程验证 + 每步操作后验证码检测
- **测试商品**：身体护理贴（Offer ID: 1023682247069）
- **结果**：提交成功，全程零验证码触发
- **关键发现**：
  1. 搜索框也使用 React，必须用 `nativeInputValueSetter` 填入关键词
  2. 搜索按钮选择器为 `button.simple-search__submit-btn`

### 2026-04-10 React Fiber onChange 直调验证 ✅

- **测试**：4 个 SKU 发货时间批量修改（24h→48h）
- **结果**：4/4 成功，React Fiber onChange 直调法稳定可靠
- **关键发现**：REST API click 无法触发 Ant Design React Portal dropdown，只有 React Fiber 直调可靠

### 2026-04-11 功能三：退出哇噢定制 - Hover 方法测试 ✅

- **测试**：在 `sale.1688.com/factory/ossdql9d.html` 页面上测试多种 hover 方法
- **结果**：
  1. **React Fiber onMouseEnter 直调是唯一可靠方法** — `dispatchEvent` 无法触发 React 合成事件
  2. **直接导航 sale.1688.com 可完全绕过 iframe 限制** — evaluate 可直接操作 DOM
  3. **BrowserWing REST hover 端点不可用** — accessibility tree 无法定位页面内部元素
  4. **完整流程验证通过**：hover → 点击退出 → 确认弹窗出现
- **技术方案**：BrowserWing REST evaluate 实现全流程，无需 Playwright

### 关键发现

1. 1688 商品管理旧 URL（`p.1688.com`）已 404，需使用 `offer.1688.com/offer/manage.htm`
2. 工作台页面使用 iframe 嵌套，BrowserWing 无法直接操作 iframe，需直接导航到实际 URL
3. 编辑页使用 React 框架，修改 input 值必须用 `nativeInputValueSetter` + 事件触发
4. 编辑页自动从旧 URL 跳转到新 URL（`offer-new.1688.com`）
5. 提交按钮选择器：`button.submit-buttom-action`
6. **Ant Design Select 必须使用 React Fiber onChange 直调**，任何 click 方式均不可靠
7. **React 组件的 hover 事件（Fusion Design Balloon）必须使用 React Fiber onMouseEnter 直调**
8. **直接导航 iframe URL 可绕过跨域 iframe 限制**（BrowserWing evaluate + Playwright 均适用）
