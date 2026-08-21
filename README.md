# Hyperliquid Monitor

![Python Version](https://img.shields.io/badge/python-3.14%2B-blue.svg)
![Aiogram Version](https://img.shields.io/badge/aiogram-3.x-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

> 一个运行在 Docker 中的 Telegram Bot，用于实时监控 Hyperliquid 链上地址的交易活动。

## 📖 项目简介

**Hyperliquid Monitor** 是一个强大的 Telegram Bot，设计用于帮助交易者、分析师以及自动化策略监控 Hyperliquid 上的地址活动。它能够实时追踪指定地址的开仓、平仓等交易行为，并通过 Telegram 第一时间推送通知。

## ✨ 核心功能

- **🚀 实时监控与推送**: 基于 WebSocket 订阅，秒级获取指定地址的最新交易动态并发送 Telegram 通知。
- **🧩 智能订单聚合**: 自动识别并合并被拆分的碎单（通过 `oid` 关联），有效避免消息刷屏，保持通知的整洁。
- **🛡️ 可靠通知**: 事件去重与通知队列持久化到 SQLite；短暂断网、Telegram 失败或正常重启后会继续补发。
- **🔌 精确地址归属**: 每个地址使用独立用户级 WebSocket，订单更新不再依赖模糊猜测；断线后自动补查近期订单状态。
- **📊 多维数据查询**: 支持快速查看地址的当前持仓、账户权益、未实现盈亏等核心指标。
- **⚙️ 灵活的阈值设置**: 支持设置全局推送过滤阈值（如：只推送超过 $1000 的交易），屏蔽低价值通知。
- **🌍 多语言支持 (i18n)**: 原生支持中文 (zh) 和英文 (en) 语言环境切换。
- **🐳 极简部署**: 全面拥抱 Docker 化部署，提供完整 `docker-compose` 配置文件，真正做到开箱即用。

## 💬 交互命令

| 命令 | 说明 |
|------|------|
| `/start`, `/help` | 初始化 Bot 并查看帮助菜单 |
| `/add <0x地址>` | 增加一个需要监控的钱包地址 |
| `/del <0x地址>` | 移除不再需要监控的钱包地址 |
| `/list` | 查看当前监控列表及地址详情 |
| `/settings` | 设置全局的通知选项及偏好 |
| `/set_filter` | 配置触发通知的资金阈值过滤 |

## 🛠️ 快速部署

### 1. 准备目录与配置

在您的服务器上创建一个工作目录。由于容器内采用非 root 用户运行以保证安全，我们需要手动创建数据挂载目录并赋予相应的权限 (1000:1000)，最后新建配置文件：

```bash
mkdir hyperliquid-monitor && cd hyperliquid-monitor
mkdir data
sudo chown -R 1000:1000 data
touch .env
```

编辑 `.env` 文件，填入相关的配置信息：

| 环境变量 | 必填 | 说明 | 示例 |
|---------|------|------|------|
| `TG_BOT_TOKEN` | ✅ | Telegram Bot Token（向 [@BotFather](https://t.me/BotFather) 获取） | `123456789:ABCdef...` |
| `TG_ADMIN_CHAT_ID`| ✅ | 管理员的 Telegram Chat ID（向 [@userinfobot](https://t.me/userinfobot) 获取） | `123456789` |
| `TG_ADMIN_USER_ID` | 群组通知时必填 | 可操作机器人的管理员用户 ID；私聊时默认与 Chat ID 相同 | `123456789` |
| `DB_PATH` | ❌ | SQLite 数据库文件的挂载路径 | `data/bot.db` |
| `LOG_LEVEL` | ❌ | 控制台日志级别 (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `BOT_LANGUAGE` | ❌ | 默认展示语言 (`zh` 或 `en`) | `zh` |
| `DISPLAY_TIMEZONE` | ❌ | Telegram 消息使用的 IANA 时区 | `Asia/Shanghai` |
| `FILL_BUFFER_SECONDS` | ❌ | 同一订单最后一笔成交后的静默聚合时间（秒） | `3.0` |
| `FILL_MAX_WAIT_SECONDS` | ❌ | 连续成交的最长聚合等待时间（秒） | `15.0` |
| `ORDER_BUFFER_SECONDS` | ❌ | 订单更新聚合窗口(秒)，窗口内多条订单通知合并成一条 | `2.0` |
| `MAX_WS_USERS` | ❌ | 实时 WebSocket 地址上限；官方每 IP 最大为 10 | `10` |
| `OUTBOX_POLL_SECONDS` | ❌ | 持久化通知队列扫描间隔（秒） | `1.0` |
| `OUTBOX_RETRY_MAX_SECONDS` | ❌ | 通知失败后的最大重试间隔（秒） | `300` |

> Hyperliquid 对单个 IP 的用户级 WebSocket 订阅最多允许 10 个不同地址。本项目会阻止继续添加超限地址；旧数据库若已有超限数据，只启用最早添加的 10 个并在 Telegram 中告警。

### 2. 启动服务

推荐使用 `docker-compose` 运行。在同一目录下创建 `compose.yaml` 文件：

```yaml
services:
  hyperliquid-monitor:
    image: yushum/hyperliquid-monitor:latest
    container_name: hyperliquid-monitor
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./data:/app/data
```

一键拉取镜像并启动：

```bash
docker compose up -d
```

### 3. 日志与维护

**查看运行日志：**
```bash
docker compose logs -f hyperliquid-monitor
```

**停止服务：**
```bash
docker compose down
```

## 🏗️ 架构与设计

本项目遵循模块化的结构设计，各组件职责分明：

```text
hyperliquid-monitor/
├── core/            # 核心配置与全局依赖注入 (pydantic-settings)
├── infrastructure/  # 基础设施层：SQLite 数据库连接、Hyperliquid API/WS 客户端集成
├── services/        # 领域服务层：区块链数据实时监控 (BlockchainMonitor) 和通知推送 (TelegramNotifier)
├── tg_bot/          # 表现层：Telegram 命令处理、事件路由以及国际化 (i18n) 文案
├── main.py          # 应用程序入口及异步生命周期 (优雅启停) 管理
├── Dockerfile       # 容器构建指令
└── compose.yaml     # 容器编排配置
```

## 💻 技术栈

- **语言**: Python 3.14 + 原生 `asyncio` 异步编程模型
- **Bot 框架**: [aiogram 3.x](https://docs.aiogram.dev/en/latest/) - 高性能的异步 Telegram Bot API
- **网络通信**: [aiohttp](https://docs.aiohttp.org/en/stable/) - 处理与 Hyperliquid REST/WebSocket 接口的交互
- **数据持久化**: [aiosqlite](https://aiosqlite.omnilib.dev/en/stable/) - 非阻塞式 SQLite 驱动
- **重试机制**: [tenacity](https://tenacity.readthedocs.io/en/latest/) - 提升网络异常下的容错性
- **配置管理**: [pydantic-settings](https://docs.pydantic.dev/latest/usage/pydantic_settings/) - 类型安全的配置校验解析

---
*Developed with ❤️ for the Hyperliquid Community.*
