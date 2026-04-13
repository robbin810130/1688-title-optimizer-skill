# 1688-title-optimizer Runbook (v3.4.1)

本 Runbook 用于让其他 agent 在同一台机器上稳定执行「功能四：批量开启官方定制项」。

## 0. 执行原则

- 浏览器自动化动作统一使用 BrowserWing REST API。
- 本项目当前不维护“已知例外类目”名单；任何类目失败都按运行时异常处理。
- 先小范围压测，再放开整轮。

## 1. 环境前置检查

在终端执行：

```bash
which browserwing
browserwing --version
curl -s --connect-timeout 3 http://localhost:8080/api/v1/executor/help | head
```

要求：

- `browserwing` 命令存在并可返回版本。
- `help` 接口可返回 JSON。
- BrowserWing 控制的浏览器中已登录 1688 商家后台。

## 2. 启动 BrowserWing（如未运行）

```bash
browserwing --port 8080
```

说明：

- 建议单独终端常驻运行 BrowserWing。
- 若端口异常，先结束旧进程再重启 BrowserWing。

## 3. 试跑（建议先做）

先用小轮次验证当前环境：

```bash
MAX_ROUNDS=1 MAX_CONSECUTIVE_ERRORS=20 /Users/robbin/.agents/skills/1688-title-optimizer/batch_official_customize_enable.sh
```

## 4. 整轮执行

```bash
MAX_ROUNDS=200 MAX_CONSECUTIVE_ERRORS=20 /Users/robbin/.agents/skills/1688-title-optimizer/batch_official_customize_enable.sh
```

## 5. 运行中观察点

关注日志中的以下字段：

- `待设置商品数`
- `CATEGORY_SUCCESS / CATEGORY_FAILED / CATEGORY_SKIPPED`
- `PENDING_REMAINING`
- 每类目的 `已保存，反馈：...`

日志路径：

```text
/Users/robbin/.agents/skills/1688-title-optimizer/logs/official_customize_{timestamp}.log
```

截图路径：

```text
/Users/robbin/.agents/skills/1688-title-optimizer/screenshots/official_customize/
```

## 6. 异常处理

### 6.1 验证码

- 看到验证码提示时，在 BrowserWing 浏览器窗口手工完成验证。
- v3.4.1 已支持非交互轮询，不会因为 `input()` 报 `EOF` 直接退出。

### 6.2 BrowserWing 会话断开

现象：

- 日志出现 `ERROR:error.evaluateFailed`、`error.navigationFailed` 等。

处理：

1. 结束当前批处理进程。
2. 重启 BrowserWing。
3. 重新执行批处理命令。

### 6.3 待设置数量不下降

- v3.4.1 已加入防空转保护：若待设置数量连续两轮不下降，会自动停机。
- 停机后先检查页面状态，再决定是否继续跑批。

## 7. 手工停止

```bash
pkill -f batch_official_customize_enable.py
```

## 8. 发布前最小检查

```bash
python3 -m py_compile /Users/robbin/.agents/skills/1688-title-optimizer/batch_official_customize_enable.py
bash -n /Users/robbin/.agents/skills/1688-title-optimizer/batch_official_customize_enable.sh
```

## 9. 验收建议

- 至少完成一次「前 10 类目」连续成功验证。
- 再执行整轮，确认无会话断开、无持续性错误、无重复空转。
