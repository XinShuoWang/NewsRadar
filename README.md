# NewsRadar

NewsRadar 是一个面向数据库内核、OLAP 引擎和大数据执行引擎方向的每日技术情报邮件工具。它从配置的论文、博客和检索接口抓取候选内容，使用增量状态去重，可选调用 OpenAI 兼容 LLM 做精选排序，最后通过 SMTP 发送日报邮件。

## 当前运行模型

- 邮件是主要输出：运行完成后发送当日技术情报。
- 日志是可观测输出：关键阶段、抓取异常、LLM 降级、邮件发送和状态写入都会打印。
- 状态是唯一持久化数据：`state/seen_items.json` 保存跨天去重指纹。

## 项目结构

```text
src/newsradar/
  app.py             每日流程应用服务
  collectors/        来源注册表、抓取服务和解析器
  llm/               OpenAI 兼容客户端、runner 装配和 LLM 排序流水线
  output/            邮件标题、正文和 SMTP 发送
  config.py          环境变量和路径配置
  logging.py         TRACE/DEBUG/INFO/WARNING/ERROR 日志配置
  main.py            CLI 入口
  models.py          核心数据模型
  paths.py           仓库路径工具
  storage.py         增量去重状态读写

config/
  source.yaml        官方来源列表
  llm_prompt.yaml    LLM 提示词模板

state/
  seen_items.json
```

## 安装

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

本地运行测试：

```bash
PYTHONPATH=src .venv/bin/pytest -q
```

## 配置

LLM 配置：

```bash
export LLM_ENABLED=true
export LLM_BASE_URL=https://example.com/v1
export LLM_API_KEY=your-api-key
export LLM_MODEL=your-model
```

SMTP 配置：

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USERNAME=sender@example.com
export SMTP_PASSWORD=app-password
export EMAIL_TO=reader@example.com
```

`LLM_ENABLED=false` 时系统会走降级路径，邮件中直接列出去重后的原始候选条目，并在标题中标记 `[LLM 不可用]`。

## 运行

```bash
PYTHONPATH=src .venv/bin/python -m newsradar.main
```

常用参数：

```bash
PYTHONPATH=src .venv/bin/python -m newsradar.main \
  --run-date 2026-05-06 \
  --official-sources-path config/source.yaml \
  --state-root state \
  --log-level INFO
```

日志等级支持：

- `TRACE`：最细粒度诊断日志，适合排查流程细节。
- `DEBUG`：调试信息。
- `INFO`：默认等级，展示正常运行阶段。
- `WARNING`：降级或可恢复异常。
- `ERROR`：运行失败或不可恢复异常。

## 去重逻辑

去重分两层：

- 来源游标：如果条目的 `published_at` 不晚于该来源上次处理时间，会被过滤。
- 历史指纹：优先使用规范化 URL 生成 `url:<normalized-url>`，没有 URL 时使用来源名和标题生成 `title:<source>:<title>`。

只有邮件发送成功，或者 SMTP 未配置导致发送被跳过时，状态才会推进；邮件发送失败时状态不会写入，避免下次运行漏发内容。

## GitHub Actions

`.github/workflows/daily-digest.yml` 每天 UTC 00:00 运行，对应上海时间 08:00。工作流会：

- 安装依赖。
- 执行 `PYTHONPATH=src python -m newsradar.main`。
- 仅提交 `state/` 中的去重状态变化。
- 不上传 archive artifact，也不提交每日归档文件。

需要在 GitHub Secrets 或 Variables 中配置 LLM 和 SMTP 环境变量。
