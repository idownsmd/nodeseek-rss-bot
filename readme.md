# Nodeseek RSS 多用户订阅机器人 🤖

一个功能丰富的 Telegram 机器人，允许用户个性化订阅 Nodeseek RSS Feed 更新，支持多用户、关键词过滤和灵活的推送模式。

[![Docker Pulls](https://img.shields.io/docker/pulls/sooxoo/nodeseek-rss-bot.svg)](https://hub.docker.com/r/sooxoo/nodeseek-rss-bot)
## 📖 项目简介

本项目是一个基于 Python 开发的多用户 Nodeseek Telegram 机器人，旨在为用户提供个性化的 RSS Feed 更新推送服务。用户可以通过与机器人私聊，订阅特定的关键词，并选择仅接收包含这些关键词的 RSS 帖子，或者接收 RSS Feed 中的所有帖子。机器人会定期检查指定的 RSS Feed，并将符合用户订阅条件的最新帖子标题和链接直接推送到用户的 Telegram。

默认配置下，机器人监控 NodeSeek 社区的 RSS Feed (`https://rss.nodeseek.com/`)，但此 RSS 源 URL 可以通过环境变量灵活配置，使其适用于监控任何公开的 RSS Feed。

项目采用 Docker进行容器化部署，简化了安装和管理过程，并通过数据卷实现用户数据和已处理帖子记录的持久化存储。

## ✨ 主要功能

* **👤 多用户支持**: 每个用户拥有独立的订阅配置和隐私。
* **🔑 个性化关键词过滤**: 用户可自定义关键词列表，机器人根据列表推送相关内容。
* **⚙️ 灵活推送模式**:
    * **关键词过滤模式**: (默认开启) 仅推送匹配用户关键词的帖子。若无关键词则不推送。
    * **接收全部模式**: (关键词过滤关闭) 推送 RSS Feed 中的所有新帖子。
    * 用户可通过 `/togglefilter` 命令轻松切换。
* **🗣️ 丰富命令集**: 提供完整的命令集用于关键词管理、通知设置、模式切换和状态查询。
* **🔄 自动 RSS 监控**: 定期检查 RSS Feed 更新 (间隔可配置)。
* **💬 Telegram 即时通知**: 新帖子标题和链接通过 MarkdownV2 格式清晰推送。
* **💾 数据持久化**: 用户设置和已处理帖子记录通过 Docker Volume 持久化存储。
* **🛡️ 管理员通知 (可选)**: 可配置向管理员发送机器人状态和错误信息。
* **🐳 Docker化部署**: 方便快捷地通过 Docker 部署和管理。

## 🛠️ 技术栈

* **Python 3**
* **python-telegram-bot** (v13.x 兼容版本)
* **feedparser**
* **JSON** (用于数据存储)
* **Docker**

## 🚀 快速开始与部署 (使用 Docker)

本机器人已在 Docker Hub 上提供预构建的镜像 `sooxoo/nodeseek-rss-bot:latest`，方便快速部署。

### 📋 前提条件

1.  **Docker 已安装**: 确保您的服务器或本地机器上已安装并运行 Docker。
2.  **Telegram Bot Token**: 从 Telegram 上的 `@BotFather` 获取一个有效的 API Token。
3.  (可选) **RSS Feed URL**: 您希望监控的 RSS Feed 地址 (默认为 NodeSeek)。
4.  (可选) **管理员 Chat ID**: 用于接收机器人管理通知的 Telegram Chat ID。

### ⚙️ 环境变量配置

在运行 Docker 容器时，您可以通过以下环境变量配置机器人：

| 环境变量                 | 描述                                                           | 是否必需 | 默认值                         |
| :----------------------- | :------------------------------------------------------------- | :------- | :----------------------------- |
| `TELEGRAM_BOT_TOKEN`     | 您的 Telegram Bot Token。                                      | **是** | 无                             |
| `RSS_URL`                | 您希望监控的 RSS Feed URL。                                      | 否       | `https://rss.nodeseek.com/`    |
| `CHECK_INTERVAL_SECONDS` | RSS Feed 检查间隔时间（秒）。                                    | 否       | `300` (5 分钟)                 |
| `ADMIN_CHAT_ID`          | (可选) 接收机器人管理和错误通知的管理员 Telegram Chat ID。         | 否       | 无                             |

### 🐳 使用预构建的 Docker Hub 镜像进行部署 (推荐)

1.  **拉取 Docker 镜像:**
    打开终端并运行以下命令，从 Docker Hub 拉取预构建的镜像：
    ```bash
    docker pull sooxoo/nodeseek-rss-bot:latest
    ```

2.  **创建持久化数据目录:**
    为了在容器重启后保留用户数据和已发送帖子记录，您需要在宿主机上创建一个目录用于数据持久化。
    ```bash
    # 示例：在 /opt 目录下创建数据文件夹
    sudo mkdir -p /opt/my_rss_bot_data
    # (可选，根据您的系统和用户调整权限，确保 Docker 有写入权限)
    # sudo chown $(whoami):$(whoami) /opt/my_rss_bot_data
    ```
    *(您可以选择其他路径，例如 `$(pwd)/bot_data` 以在当前目录下创建)*

3.  **运行 Docker 容器:**
    执行以下命令启动机器人容器。请务必替换占位符为您自己的实际值。
    ```bash
    docker run -d \
      --name nodeseek-rss-subscriber \
      -e TELEGRAM_BOT_TOKEN="YOUR_ACTUAL_TELEGRAM_BOT_TOKEN" \
      -e RSS_URL="[https://rss.nodeseek.com/](https://rss.nodeseek.com/)" \
      -e CHECK_INTERVAL_SECONDS="300" \
      # 如果需要管理员通知，请取消下一行的注释并填入您的 Chat ID
      # -e ADMIN_CHAT_ID="YOUR_ADMIN_TELEGRAM_CHAT_ID" \
      -v /opt/my_rss_bot_data:/app/data \
      --restart unless-stopped \
      sooxoo/nodeseek-rss-bot:latest
    ```
    * **重要**:
        * 将 `YOUR_ACTUAL_TELEGRAM_BOT_TOKEN` 替换为您的真实 Bot Token。
        * 根据需要调整 `RSS_URL` 和 `CHECK_INTERVAL_SECONDS`。
        * 将 `/opt/my_rss_bot_data` 替换为您在第2步中创建的宿主机数据目录路径。
        * `sooxoo/nodeseek-rss-bot:latest` 是您从 Docker Hub 拉取的镜像名称。

4.  **(可选) 查看日志**:
    您可以使用以下命令查看机器人的运行日志：
    ```bash
    docker logs nodeseek-rss-subscriber
    ```
    要实时跟踪日志，请添加 `-f` 参数：
    ```bash
    docker logs -f nodeseek-rss-subscriber
    ```

### 🛠️ (可选) 从源码构建并部署

如果您希望自行从源码构建镜像，请按以下步骤操作：

1.  **获取项目文件:**
    克隆本 GitHub 仓库或下载源码压缩包，并解压到您的项目目录 (例如 `telegram_rss_bot`)。确保该目录下包含 `bot.py`, `Dockerfile`, 和 `requirements.txt`。

2.  **构建 Docker 镜像:**
    在您的项目目录下，打开终端并运行：
    ```bash
    docker build -t your-custom-image-name:latest .
    ```
    *(将 `your-custom-image-name` 替换为您希望的本地镜像名称，例如 `my-local-rss-bot:latest`)*

3.  **创建持久化数据目录:**
    (同上文“使用预构建的 Docker Hub 镜像进行部署”中的第2步)

4.  **运行 Docker 容器:**
    使用您在上面第2步中构建的自定义镜像名称替换 `docker run` 命令中的镜像名：
    ```bash
    docker run -d \
      --name nodeseek-rss-subscriber \
      -e TELEGRAM_BOT_TOKEN="YOUR_ACTUAL_TELEGRAM_BOT_TOKEN" \
      -e RSS_URL="[https://rss.nodeseek.com/](https://rss.nodeseek.com/)" \
      -e CHECK_INTERVAL_SECONDS="300" \
      # -e ADMIN_CHAT_ID="YOUR_ADMIN_TELEGRAM_CHAT_ID" \
      -v /opt/my_rss_bot_data:/app/data \
      --restart unless-stopped \
      your-custom-image-name:latest
    ```

## 🤖 如何使用

### 1. 设置机器人命令 (通过 `@BotFather`)

为了提升用户体验，建议您为机器人在 Telegram 中设置预设命令列表。操作步骤如下：

1.  打开 Telegram，找到 `@BotFather` 并开始聊天。
2.  发送 `/setcommands` 命令给 `@BotFather`。
3.  选择您要配置的机器人。
4.  发送以下格式的命令列表给 `@BotFather` (每行一个命令及其描述)：
    ```
    start - 启动机器人并显示帮助信息
    addkeyword - 添加关键词到订阅列表
    listkeywords - 显示当前订阅的关键词
    delkeyword - 删除一个订阅的关键词
    editkeyword - 修改一个已订阅的关键词
    togglefilter - 切换关键词过滤模式 (开/关)
    enablenotifications - 开启 RSS 推送通知
    disablenotifications - 关闭 RSS 推送通知
    myrssstatus - 查看当前订阅状态和关键词
    ```

### 2. 用户命令列表

用户可以在与机器人的**私聊**中使用以下命令：

| 命令                       | 描述                                       |
| :------------------------- | :----------------------------------------- |
| `/start`                   | 启动机器人并显示帮助信息。                   |
| `/addkeyword <关键词或短语>` | 添加一个新的关键词或短语到您的订阅列表。     |
| `/listkeywords`            | 显示您当前订阅的所有关键词及其序号。         |
| `/delkeyword <关键词、短语或序号>` | 从您的订阅列表中删除指定的关键词。         |
| `/editkeyword <序号> <新关键词>` | 修改您订阅列表中指定序号的关键词。           |
| `/togglefilter`            | 切换您的关键词过滤模式 (开启/关闭)。       |
| `/enablenotifications`     | 开启所有来自此机器人的 RSS 推送通知。        |
| `/disablenotifications`    | 关闭所有来自此机器人的 RSS 推送通知。        |
| `/myrssstatus`             | 查看您当前的总体通知状态、关键词过滤模式状态以及关键词列表。 |

## 💾 数据持久化

* **用户订阅信息**: 包括用户的 Chat ID、关键词列表、通知启用状态和关键词过滤模式状态，存储在挂载到宿主机的 `/app/data/user_subscriptions.json` 文件中。
* **全局已发送帖子**: 记录机器人已处理过的所有帖子链接，以避免重复推送，存储在挂载到宿主机的 `/app/data/sent_posts_global.txt` 文件中。

确保在运行 Docker 容器时正确配置了数据卷 (`-v` 参数)，以便在容器重启或更新后这些数据能够保留。

## 📄 日志

机器人的运行日志可以通过 Docker 查看：
```bash
docker logs <您的容器名称或ID>