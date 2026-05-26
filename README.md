# 每日全球重要新闻微信推送系统

每天北京时间 08:00 自动抓取全球重要新闻，筛选后生成中文简报，并推送到企业微信群机器人。企业微信不可用时，可改用 Server酱。

## 1. 系统目标

目标：每天自动推送不超过 10 条高价值国际新闻。

路径：

1. GitHub Actions 定时启动。
2. Python 抓取 RSS 新闻源。
3. 按关键词过滤娱乐、体育、标题党和低价值新闻。
4. 对候选新闻去重、评分、排序。
5. 调用 OpenAI 或兼容接口生成中文分析简报。
6. 优先推送企业微信；没有企业微信时推送 Server酱。

## 2. 项目文件

```text
main.py
requirements.txt
.env.example
.github/workflows/daily-news.yml
README.md
```

## 3. 如何准备新闻源

系统内置 RSS 源，覆盖国际政治、经济金融、科技、地缘冲突、中国相关国际新闻：

- BBC World
- Reuters
- New York Times World
- Financial Times World
- Al Jazeera
- NPR World
- South China Morning Post
- China Daily World / Business
- Ars Technica Technology

如果你要自定义新闻源，在 GitHub Secrets 新增 `NEWS_FEEDS`，每行一个 RSS 地址，例如：

```text
https://feeds.bbci.co.uk/news/world/rss.xml
https://www.ft.com/rss/world
https://www.aljazeera.com/xml/rss/all.xml
```

判断标准：

- 优先选择有 RSS 的权威媒体。
- 不要加入娱乐、社会奇闻、体育类 RSS。
- 新闻源不宜过多，10-20 个足够。过多会增加重复新闻和模型成本。

## 4. 如何配置 OpenAI API Key

到 OpenAI 平台创建 API Key，然后在 GitHub 仓库中配置 Secret：

```text
OPENAI_API_KEY=你的 API Key
OPENAI_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

如果你使用兼容 OpenAI Chat Completions 的模型服务，修改：

```text
OPENAI_BASE_URL=https://你的服务地址/v1
OPENAI_MODEL=你的模型名
```

注意：不要把 API Key 写进代码，也不要提交 `.env` 文件。

## 5. 如何配置企业微信 Webhook

企业微信路径：

1. 打开企业微信群。
2. 点击群设置。
3. 添加群机器人。
4. 复制 Webhook 地址。
5. 在 GitHub Secrets 新增：

```text
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx
```

企业微信是首选方案，稳定、适合群推送。

## 6. 如何配置 Server酱 SendKey

如果没有企业微信，用 Server酱：

1. 打开 Server酱官网。
2. 用微信登录并绑定。
3. 复制 SendKey。
4. 在 GitHub Secrets 新增：

```text
SERVERCHAN_SENDKEY=你的 SendKey
```

代码逻辑：

- 有企业微信 Webhook，优先推送企业微信。
- 企业微信未配置或失败时，尝试 Server酱。
- 两个都没有或都失败，任务报错。

## 7. 如何配置 GitHub Secrets

进入你的 GitHub 仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

必须配置：

```text
OPENAI_API_KEY
```

至少配置一个推送密钥：

```text
WECOM_WEBHOOK
SERVERCHAN_SENDKEY
```

建议配置：

```text
OPENAI_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=https://api.openai.com/v1
MAX_NEWS_ITEMS=10
MAX_CANDIDATES=30
```

可选配置：

```text
NEWS_FEEDS
```

## 8. 如何本地测试

先安装依赖：

```bash
pip install -r requirements.txt
```

复制配置文件：

```bash
copy .env.example .env
```

在 `.env` 里填入：

```text
OPENAI_API_KEY=你的 Key
WECOM_WEBHOOK=你的企业微信 Webhook
DRY_RUN=true
```

运行：

```bash
python main.py
```

`DRY_RUN=true` 时只打印简报，不推送。确认内容正常后改成：

```text
DRY_RUN=false
```

再运行一次，测试真实推送。

## 9. 如何在 GitHub Actions 测试推送

进入 GitHub 仓库：

```text
Actions -> Daily Global News -> Run workflow
```

如果成功，会在日志中看到：

```text
[OK] 已推送到企业微信
```

或：

```text
[OK] 已通过 Server酱推送
```

## 10. 如何修改推送时间

文件：`.github/workflows/daily-news.yml`

当前配置：

```yaml
- cron: "0 0 * * *"
```

GitHub Actions 使用 UTC 时间。北京时间 = UTC + 8。

常用时间：

```text
北京时间 08:00 -> cron: "0 0 * * *"
北京时间 07:30 -> cron: "30 23 * * *"
北京时间 09:00 -> cron: "0 1 * * *"
```

风险：GitHub Actions 定时任务不是秒级准时，通常会有几分钟延迟。免费仓库在高峰期延迟更明显。

## 11. 常见报错处理

### 报错：缺少 OPENAI_API_KEY

原因：没有配置 API Key。

动作：

1. 本地运行时检查 `.env`。
2. GitHub Actions 运行时检查 `Settings -> Secrets and variables -> Actions`。

### 报错：大模型接口失败 HTTP 401

原因：API Key 错误、过期或没有权限。

动作：

1. 重新创建 API Key。
2. 检查 Secret 名称必须是 `OPENAI_API_KEY`。
3. 如果使用第三方兼容接口，检查 `OPENAI_BASE_URL` 和 `OPENAI_MODEL`。

### 报错：企业微信推送失败

原因：Webhook 不正确、机器人被删除、企业微信安全策略限制。

动作：

1. 重新复制群机器人 Webhook。
2. 确认 Secret 名称是 `WECOM_WEBHOOK`。
3. 如果企业微信设置了关键词校验，确保关键词包含“每日全球重要新闻”。

### 报错：Server酱推送失败

原因：SendKey 错误、账号未绑定微信、额度限制。

动作：

1. 重新复制 SendKey。
2. 检查 Server酱后台是否绑定微信。
3. 检查当日推送额度。

### 报错：未抓取到符合条件的新闻

原因：RSS 源不可用，或关键词过滤太严格。

动作：

1. 检查 `NEWS_FEEDS` 是否每行一个 RSS。
2. 暂时删除自定义 `NEWS_FEEDS`，使用内置源。
3. 在 `main.py` 的 `FOCUS_KEYWORDS` 中增加你关心的关键词。

### GitHub Actions 没有按时运行

原因：GitHub 定时任务使用 UTC，且可能延迟。

动作：

1. 检查 cron 是否按 UTC 配置。
2. 用 `workflow_dispatch` 手动运行一次确认流程正常。
3. 如果仓库长期无活动，GitHub 可能暂停定时任务，需要手动启用。

## 12. 如何调整新闻偏好

修改 `main.py`：

```python
FOCUS_KEYWORDS = {
    ...
}
```

优先增加这些方向的关键词：

- 国家和地区：china, taiwan, united states, russia, ukraine, iran
- 机构：nato, g7, g20, united nations, federal reserve
- 议题：sanction, tariff, export control, semiconductor, oil, inflation

不要把关键词写得太泛，例如 `people`、`new`、`report`，会引入大量低价值新闻。

## 13. 结果判断

短期动作：

- 先用内置 RSS 源跑通。
- 先用 `DRY_RUN=true` 检查内容。
- 再打开真实推送。

长期动作：

- 每两周检查一次新闻源质量。
- 删除重复率高、标题党多、低价值新闻多的 RSS。
- 根据推送结果调整关键词和模型。

最优方案：

- 企业微信群机器人 + OpenAI API + GitHub Actions。
- 成本低、维护简单、适合新手。

备选方案：

- Server酱替代企业微信。
- 第三方兼容 OpenAI 接口替代 OpenAI 官方接口。

风险：

- RSS 源会变化，部分媒体可能限制抓取。
- 模型摘要依赖候选新闻质量。
- GitHub Actions 定时任务可能延迟。
- 免费推送通道可能有频率或内容限制。
