---
name: 1688-title-optimizer
description: "1688商品运营自动化技能。基于BrowserWing浏览器自动化平台，实现1688后台商品的AI标题优化、批量发货服务同步、批量退出哇噢定制、批量开启官方定制项。触发词：优化标题、修改标题、批量修改标题、同步发货服务、发货时间设置、批量设置发货、发货服务批量修改、退出哇噢定制、退出定制、设置官方定制项、批量开定制、包装定制。"
description_zh: "1688商品运营自动化技能（高成功率执行规范版）"
version: 3.5.0
---

# 1688 商品运营自动化 Skill（执行规范）

本 Skill 用于 1688 卖家后台四类批处理任务：
1. AI 标题优化
2. 发货服务同步
3. 批量退出哇噢定制
4. 批量开启官方定制项

目标：在不同机器/不同 agent 环境下，尽量避免跑偏，提升一次执行成功率。

## 一、总原则（必须遵守）

- 浏览器自动化动作优先且尽量全部使用 BrowserWing：`/navigate`、`/evaluate`、`/click`、`/screenshot`。
- 禁止主实现切换到 Playwright；仅允许 BrowserWing 内部多策略重试。
- 每次进入“开始自动化操作”的页面前，先做登录态检查；未登录必须先提示人工登录。
- 出现验证码时先暂停自动化，人工处理后继续。
- 单点动作连续尝试 3 种 BrowserWing 方法仍失败：立即停机汇报，不允许盲目无限重试。

## 二、启动前检查（每次必做）

1. BrowserWing 可用：
```bash
curl -s --connect-timeout 3 http://localhost:8080/api/v1/executor/help
```

2. 浏览器中已登录 1688 商家后台。

3. 运行脚本语法自检：
```bash
python3 -m py_compile ./batch_title_optimizer.py
bash -n ./batch_shipping_sync.sh
python3 -m py_compile ./exit_waodingzhi.py
python3 -m py_compile ./batch_official_customize_enable.py
```

4. BrowserWing 服务复用策略（硬性）：
- 先探测，后启动；探测通过就直接复用，禁止重复拉起。
- 仅当探测失败时，才允许静默后台启动。

复用探测命令：
```bash
curl -s --connect-timeout 2 http://localhost:8080/api/v1/executor/help | grep -q '"navigate"'
```

若探测成功：
- 直接进入业务流程。
- 不执行 `pkill`、不重启 BrowserWing。

若探测失败（才允许启动）：
```bash
cd /Users/robbin/Codex/1688Skill
nohup browserwing --config /Users/robbin/Codex/1688Skill/config.toml >/tmp/browserwing.out 2>&1 &
sleep 2
curl -s --connect-timeout 3 http://localhost:8080/api/v1/executor/help
```

说明：
- 上述启动为后台静默启动（无前台阻塞）。
- 目标是尽量避免每次执行时再弹 BrowserWing 管理页面（`http://127.0.0.1:xxxxx/`）。
- 若仍偶发弹页，保持“复用优先”即可显著降低出现频次。

## 三、功能选择与输入约束

### 功能1：AI 标题优化（`batch_title_optimizer.py`）

强制要求：必须提供以下之一，不允许全量扫描全店。
- `--sku-list`
- `--sku-file`
- `--keyword`

### 功能2：发货服务同步（`batch_shipping_sync.sh`）

强制要求：必须提供以下之一，不允许全量扫描全店。
- `--sku-list`
- `--sku-file`
- `--keyword`

说明：
- 运行时按“检索词逐个执行（先搜索再处理）”。
- `SKU00027165/27167/27168` 这种写法按一个完整 SKU 字符串处理，不自动拆分。

### 功能3：批量退出哇噢定制

支持按数量、关键词、SKU清单方式执行；建议先小批量压测再放开。

### 功能4：批量开启官方定制项

按“待设置 -> 下一步 -> 类目逐个处理 -> 保存 -> 返回待设置循环”执行，直到待设置为空。

## 四、功能SOP与成功判定

### 功能1 SOP（标题优化）

1. 导航商品列表并验证登录。
2. 按输入条件检索目标商品。
3. 扫描并导出 CSV。
4. 生成优化标题并预览。
5. 用户确认后逐个提交。

成功判定：
- 扫描阶段：至少命中目标商品，且输出扫描 CSV。
- 执行阶段：每个商品返回 `发布成功` 或 `进入审核` 视为成功。

### 功能2 SOP（发货服务同步）

1. 导航商品列表并验证登录。
2. 对每个检索词：先在列表搜索框搜索，再提取命中商品。
3. 逐个进入编辑页，定位“服务与承诺 -> 发货服务”表格。
4. 校验规则：
   - 第1行数量区间 `1~2`，发货时间 `48小时发货`
   - 第2行数量区间 `3+`，发货时间 `72小时发货`
5. 如不一致则修改并提交。

成功判定：
- 单商品：提交后返回“提交成功”或无报错且保存完成截图。
- 整批：`FAILED=0` 为最佳；若有失败，必须输出具体 offerId 与失败原因。

### 功能3 SOP（退出哇噢定制）

1. 导航列表并验证登录。
2. 按输入条件筛选目标商品。
3. 逐个执行“退出定制”动作并确认。

成功判定：
- 目标商品状态从“已加入哇噢定制”变为“可加入/无定制状态”。

### 功能4 SOP（开启官方定制项）

1. 打开 1688 商家后台。
2. 进入“找工厂 -> 设置官方定制项”。
3. 在“待设置”检查是否有商品；无则结束。
4. 有商品则点“下一步”，进入类目页。
5. 逐类目处理：
   - 若存在“包装定制”下拉，选中以下四项（重复项只选一次）：
     - 手工贴标 +0.3 3件起定
     - 塑封 +0.2 3件起定
     - OPP袋 +0.2 3件起定
     - 气泡袋 +0.25 3件起定
   - 点“确定，去设置报价”
   - 弹窗点“确定”
   - 点“保存XXXX商品的定制项”
6. 全类目完成后回到待设置继续循环。

成功判定：
- 每个类目保存后无报错。
- 循环结束条件是“待设置为空”。

## 五、最常见跑偏点（重点避坑）

1. 未登录直接开跑：
- 处理：进入关键页前先检测登录文本（登录/请登录）。

2. 验证码触发后继续点：
- 处理：立即暂停，人工过码后再继续。

3. 功能1/2误跑全店：
- 处理：无 SKU/筛选条件时直接退出并提示。

4. 每次都重启 BrowserWing 导致弹管理页：
- 处理：严格执行“先探测复用，失败才静默后台启动”。

5. 功能2 下拉项“看得到但点不到”：
- 原因：下拉层过渡态/虚拟列表/不可见过滤误判。
- 处理：使用 `mousedown + click` 打开；选项匹配不依赖可见性；必要时滚动下拉容器再匹配。

6. 功能4 第二类目开始漏选四项：
- 原因：残留弹层/类目切换后作用域漂移。
- 处理：每类目都重新打开当前类目的包装定制下拉，完成后核验弹窗中是否包含四项再保存。

7. `SAVE_UNKNOWN`：
- 解释：不一定失败，可能已成功保存。
- 处理：以页面实际状态为准（是否可继续下个类目、是否出现报错）。

## 六、异常升级规则（硬性）

当某个关键动作失败时，按顺序最多尝试 3 种 BrowserWing 方法：
1. `evaluate` 精准定位点击。
2. `click` API（`wait_visible=false`）。
3. 重新定位容器后再次 `evaluate`（必要时滚动容器）。

若仍失败：
- 立即停机，输出：
  - 当前功能
  - 当前 offerId / 类目
  - 最后一次错误
  - 已尝试的 3 种方法
  - 对应截图路径

## 七、运行后标准输出（必须给用户）

至少包含：
- 执行参数（SKU/关键词/轮次）
- 命中数量
- 成功/失败/跳过数量
- 失败明细（offerId + 原因）
- 日志路径
- 截图路径

## 八、推荐命令模板

功能1（扫描预检）：
```bash
NON_INTERACTIVE=1 python3 batch_title_optimizer.py --scan-only --sku-list "SKU1,SKU2"
```

功能2（发货同步）：
```bash
NON_INTERACTIVE=1 ./batch_shipping_sync.sh --sku-list "SKU1,SKU2"
```

功能3（退出哇噢定制）：
```bash
NON_INTERACTIVE=1 python3 exit_waodingzhi.py --sku-list "SKU1,SKU2"
```

功能4（开启官方定制项，小轮次压测）：
```bash
NON_INTERACTIVE=1 MAX_ROUNDS=1 python3 batch_official_customize_enable.py
```

功能4（整轮）：
```bash
NON_INTERACTIVE=1 MAX_ROUNDS=200 python3 batch_official_customize_enable.py
```

---

如需跨机器迁移，优先参考本文件与 `RUNBOOK.md`，并先执行“小样本压测 -> 放量执行”。
