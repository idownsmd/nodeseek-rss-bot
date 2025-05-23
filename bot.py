import feedparser
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, JobQueue, CallbackContext # Filters 已移除
import telegram.utils.helpers # 确保导入
import time
import logging
import os
import json

# --- 配置信息 ---
# 从环境变量中获取 Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
# 可选: 管理员 Chat ID，用于接收机器人自身的管理通知和错误信息
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', None)
# RSS Feed URL，如果环境变量未设置，则使用默认值
RSS_URL = os.environ.get('RSS_URL', 'https://rss.nodeseek.com/')
# RSS 检查间隔时间（秒），如果环境变量未设置，则使用默认值
CHECK_INTERVAL_SECONDS = int(os.environ.get('CHECK_INTERVAL_SECONDS', 300))

# --- 数据持久化路径 ---
# Docker 容器内的数据存储路径
DATA_DIR = '/app/data'
# 全局已处理（已发送或已检查）的帖子链接记录文件
SENT_POSTS_FILE = os.path.join(DATA_DIR, 'sent_posts_global.txt')
# 用户订阅信息（关键词、启用状态等）的 JSON 文件
USER_SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, 'user_subscriptions.json')

# --- 日志配置 ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 用户订阅管理函数 ---
def load_user_subscriptions():
    """从 JSON 文件加载用户订阅信息。"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True) # 如果目录不存在则创建
    if not os.path.exists(USER_SUBSCRIPTIONS_FILE):
        return {} # 如果文件不存在，返回空字典
    try:
        with open(USER_SUBSCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"加载用户订阅失败 ({USER_SUBSCRIPTIONS_FILE}): {e}。将返回空配置。", exc_info=True)
        return {}

def save_user_subscriptions(subscriptions):
    """将用户订阅信息保存到 JSON 文件。"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True) # 如果目录不存在则创建
    try:
        with open(USER_SUBSCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(subscriptions, f, indent=4, ensure_ascii=False) # ensure_ascii=False 保证中文正确显示
        logger.info(f"用户订阅信息已保存到 {USER_SUBSCRIPTIONS_FILE}")
    except IOError as e:
        logger.error(f"保存用户订阅失败 ({USER_SUBSCRIPTIONS_FILE}): {e}", exc_info=True)

def get_user_config_and_subscriptions(user_id_str: str, chat_id: int, current_subscriptions: dict):
    """
    获取或初始化指定用户的配置。
    返回: 特定用户的配置字典, (可能被修改的)完整的订阅字典, 以及一个布尔值表示订阅字典是否被修改。
    """
    modified = False
    if user_id_str not in current_subscriptions:
        # 如果是新用户，创建默认配置
        current_subscriptions[user_id_str] = {
            "chat_id": chat_id,      # 存储用户的 chat_id，用于私聊推送
            "keywords": [],          # 用户订阅的关键词列表
            "enabled": True,         # 总体通知开关，默认为开
            "keyword_filter_active": True # 新增：关键词过滤模式开关，默认为开 (只接收关键词匹配)
        }
        modified = True
    # 确保 chat_id 是最新的
    elif current_subscriptions[user_id_str].get("chat_id") != chat_id:
         current_subscriptions[user_id_str]["chat_id"] = chat_id
         modified = True
    
    # 为老用户添加新字段的默认值
    if "keyword_filter_active" not in current_subscriptions[user_id_str]:
        current_subscriptions[user_id_str]["keyword_filter_active"] = True
        modified = True
    if "enabled" not in current_subscriptions[user_id_str]: # 确保老用户也有 enabled 字段
        current_subscriptions[user_id_str]["enabled"] = True
        modified = True

    return current_subscriptions[user_id_str], current_subscriptions, modified

# --- 全局已发送帖子管理函数 ---
def load_sent_posts_global():
    """加载全局已处理的帖子链接集合。"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(SENT_POSTS_FILE):
        return set()
    try:
        with open(SENT_POSTS_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    except IOError as e:
        logger.error(f"加载全局已发送帖子记录失败 ({SENT_POSTS_FILE}): {e}。将返回空集合。", exc_info=True)
        return set()

def save_sent_post_global(post_link):
    """将一个已处理的帖子链接追加到全局记录文件。"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(SENT_POSTS_FILE, 'a', encoding='utf-8') as f:
            f.write(post_link + '\n')
    except IOError as e:
        logger.error(f"保存全局已发送帖子记录失败 ({SENT_POSTS_FILE}): {e}", exc_info=True)

globally_sent_posts_links = load_sent_posts_global()

# --- RSS 检查与推送逻辑 ---
def check_rss_and_send_to_users(context: CallbackContext):
    global globally_sent_posts_links
    user_subscriptions = load_user_subscriptions()

    logger.info(f"正在检查 RSS feed: {RSS_URL}，准备向订阅用户推送。")

    try:
        feed = feedparser.parse(RSS_URL)
        if feed.bozo:
            error_message = f"解析 RSS feed ({RSS_URL}) 时出错: {feed.bozo_exception}"
            logger.error(error_message)
            if ADMIN_CHAT_ID:
                try:
                    context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"RSS 机器人警告: {error_message}")
                except Exception as e_admin:
                    logger.error(f"向管理员发送 RSS 解析错误通知失败: {e_admin}", exc_info=True)
            return

        new_posts_pushed_this_cycle = 0
        subscriptions_modified_due_to_send_failure = False

        for entry in reversed(feed.entries):
            post_title = entry.title
            post_link = entry.link

            if post_link in globally_sent_posts_links:
                continue

            for user_id_str, config in user_subscriptions.items():
                if not config.get("enabled", False):
                    continue

                user_chat_id = config.get("chat_id")
                if not user_chat_id:
                    logger.warning(f"用户 {user_id_str} 的配置中缺少 chat_id，无法推送。")
                    continue

                send_this_post = False
                keyword_filter_is_active = config.get("keyword_filter_active", True)

                if not keyword_filter_is_active:
                    send_this_post = True
                    logger.info(f"关键词过滤已为用户 {user_id_str} 关闭。准备发送帖子 '{post_title}'。")
                else:
                    if not config.get("keywords"):
                        logger.info(f"关键词过滤为用户 {user_id_str} 开启，但其没有设置关键词。跳过帖子 '{post_title}'。")
                    else:
                        for keyword in config["keywords"]:
                            if keyword.lower() in post_title.lower():
                                send_this_post = True
                                logger.info(f"帖子 '{post_title}' 匹配到用户 {user_id_str} 的关键词 '{keyword}'。")
                                break

                if send_this_post:
                    # 转义帖子标题以安全地在 MarkdownV2 中显示
                    escaped_post_title = telegram.utils.helpers.escape_markdown(post_title, version=2)
                    message_text = f"*{escaped_post_title}*\n\n{post_link}" # 链接通常不需要转义
                    try:
                        context.bot.send_message(chat_id=user_chat_id,
                                                 text=message_text,
                                                 parse_mode=telegram.ParseMode.MARKDOWN_V2)
                        logger.info(f"成功发送帖子 '{post_title}' 给用户 {user_id_str}")
                        new_posts_pushed_this_cycle += 1
                        time.sleep(1)
                    except telegram.error.BadRequest as e_badreq:
                        logger.error(f"发送给用户 {user_id_str} 的帖子 '{post_title}' 失败 (BadRequest): {e_badreq}")
                        if "can't parse entities" in str(e_badreq).lower():
                            logger.info(f"尝试为用户 {user_id_str} 发送纯文本版本的帖子 '{post_title}'")
                            try:
                                context.bot.send_message(chat_id=user_chat_id, text=f"{post_title}\n\n{post_link}")
                                new_posts_pushed_this_cycle += 1
                            except Exception as e_plain:
                                 logger.error(f"向用户 {user_id_str} 发送纯文本帖子 '{post_title}' 也失败: {e_plain}", exc_info=True)
                    except telegram.error.ChatMigrated as e_mig:
                        logger.warning(f"用户 {user_id_str} 的聊天已迁移。旧 chat_id: {user_chat_id}, 新 chat_id: {e_mig.new_chat_id}。")
                        user_subscriptions[user_id_str]['chat_id'] = e_mig.new_chat_id
                        subscriptions_modified_due_to_send_failure = True
                    except (telegram.error.Forbidden, telegram.error.Unauthorized) as e_auth:
                        logger.warning(f"用户 {user_id_str} (chat_id: {user_chat_id}) 已屏蔽机器人或账户已停用: {e_auth}。将禁用其通知。")
                        user_subscriptions[user_id_str]['enabled'] = False
                        subscriptions_modified_due_to_send_failure = True
                    except Exception as e_send:
                        logger.error(f"向用户 {user_id_str} 发送帖子 '{post_title}' 时发生未知错误: {e_send}", exc_info=True)

            globally_sent_posts_links.add(post_link)
            save_sent_post_global(post_link)

        if subscriptions_modified_due_to_send_failure:
            save_user_subscriptions(user_subscriptions)

        if new_posts_pushed_this_cycle == 0:
            logger.info("本轮检查没有发现符合任何用户条件的新帖子。")

    except Exception as e:
        logger.error(f"RSS 检查/发送循环中发生一般性错误: {e}", exc_info=True)
        if ADMIN_CHAT_ID:
            try:
                context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"RSS 机器人严重错误 (主循环): {e}")
            except Exception as e_admin_crit:
                logger.error(f"向管理员发送严重错误通知失败: {e_admin_crit}", exc_info=True)

# --- Telegram 命令处理函数 ---
def get_command_args_as_string(args: list) -> str:
    """将命令参数列表合并为一个字符串。"""
    return " ".join(args).strip()

def start_command(update: telegram.Update, context: CallbackContext):
    """处理 /start 命令，欢迎用户并初始化其配置 (已修正转义)。"""
    user = update.effective_user
    user_id_str = str(user.id)
    chat_id = update.effective_chat.id

    if chat_id != user.id:
        update.message.reply_text("请在与我的私聊中管理您的 RSS 关键词订阅。")
        logger.info(f"用户 {user.username} ({user_id_str}) 尝试从非私聊 ({chat_id}) 执行 /start 命令。")
        return

    subscriptions = load_user_subscriptions()
    _, subscriptions, modified = get_user_config_and_subscriptions(user_id_str, chat_id, subscriptions)

    if modified:
        save_user_subscriptions(subscriptions)
        logger.info(f"用户 {user.username} ({user_id_str}) 初始化配置或更新了 chat_id 为 {chat_id}。")

    # 对可能包含特殊字符的用户名字进行转义
    escaped_first_name = telegram.utils.helpers.escape_markdown(user.first_name or "用户", version=2)

    help_message_parts = [
        f"👋 您好, {escaped_first_name}!",
        "\n我可以根据您设置的关键词，在 RSS 有新帖子时通知您。\n",
        "可用命令:",
        f"/start \\- {telegram.utils.helpers.escape_markdown('显示此帮助信息', version=2)}",
        f"/addkeyword <关键词或短语> \\- {telegram.utils.helpers.escape_markdown('添加关键词。', version=2)}",
        f"/delkeyword <关键词或短语 或 序号> \\- {telegram.utils.helpers.escape_markdown('删除关键词。', version=2)}",
        f"/editkeyword <序号> <新的关键词或短语> \\- {telegram.utils.helpers.escape_markdown('修改关键词。', version=2)}",
        f"/listkeywords \\- {telegram.utils.helpers.escape_markdown('显示您订阅的关键词。', version=2)}",
        f"/togglefilter \\- {telegram.utils.helpers.escape_markdown('切换关键词过滤模式 (开/关)。', version=2)}",
        f"/enablenotifications \\- {telegram.utils.helpers.escape_markdown('开启所有来自此机器人的通知。', version=2)}",
        f"/disablenotifications \\- {telegram.utils.helpers.escape_markdown('关闭所有来自此机器人的通知。', version=2)}",
        f"/myrssstatus \\- {telegram.utils.helpers.escape_markdown('查看您当前的订阅状态。', version=2)}",
        "\n我会定期检查新帖子！"
    ]
    # 注意: `\-` 用于确保 `-` 不被 MarkdownV2 错误地解析为列表标记的一部分。

    update.message.reply_text("\n".join(help_message_parts), parse_mode=telegram.ParseMode.MARKDOWN_V2)


def add_keyword_command(update: telegram.Update, context: CallbackContext):
    user = update.effective_user
    user_id_str = str(user.id)
    chat_id = update.effective_chat.id
    if chat_id != user.id: return

    keyword_to_add = get_command_args_as_string(context.args)
    if not keyword_to_add:
        update.message.reply_text("使用方法: /addkeyword <关键词或短语>")
        return

    subscriptions = load_user_subscriptions()
    user_config, subscriptions, modified_by_get = get_user_config_and_subscriptions(user_id_str, chat_id, subscriptions)

    if keyword_to_add.lower() not in [kw.lower() for kw in user_config['keywords']]:
        user_config['keywords'].append(keyword_to_add)
        user_config['keywords'].sort()
        subscriptions[user_id_str] = user_config
        save_user_subscriptions(subscriptions)
        # 回复时转义用户输入的关键词，以防其包含 Markdown 特殊字符
        escaped_keyword_to_add = telegram.utils.helpers.escape_markdown(keyword_to_add, version=2)
        update.message.reply_text(f"✅ 关键词 '{escaped_keyword_to_add}' 已添加到您的列表。", parse_mode=telegram.ParseMode.MARKDOWN_V2)
    else:
        if modified_by_get: save_user_subscriptions(subscriptions)
        escaped_keyword_to_add = telegram.utils.helpers.escape_markdown(keyword_to_add, version=2)
        update.message.reply_text(f"⚠️ 关键词 '{escaped_keyword_to_add}' 已经存在于您的列表中。", parse_mode=telegram.ParseMode.MARKDOWN_V2)

def list_keywords_command(update: telegram.Update, context: CallbackContext):
    user = update.effective_user
    user_id_str = str(user.id)
    chat_id = update.effective_chat.id
    if chat_id != user.id: return

    subscriptions = load_user_subscriptions()
    user_config, subscriptions, modified_by_get = get_user_config_and_subscriptions(user_id_str, chat_id, subscriptions)
    if modified_by_get: save_user_subscriptions(subscriptions)

    if not user_config['keywords']:
        update.message.reply_text(telegram.utils.helpers.escape_markdown("您还没有设置任何关键词。使用 /addkeyword 命令来添加吧！", version=2), parse_mode=telegram.ParseMode.MARKDOWN_V2)
    else:
        message_parts = [telegram.utils.helpers.escape_markdown("您当前订阅的关键词 (匹配时不区分大小写):", version=2)]
        for i, kw in enumerate(user_config['keywords']):
            # 转义每个关键词和列表的点号
            message_parts.append(f"  {i+1}\\. {telegram.utils.helpers.escape_markdown(kw, version=2)}")
        update.message.reply_text("\n".join(message_parts), parse_mode=telegram.ParseMode.MARKDOWN_V2)

def del_keyword_command(update: telegram.Update, context: CallbackContext):
    user = update.effective_user
    user_id_str = str(user.id)
    chat_id = update.effective_chat.id
    if chat_id != user.id: return

    arg_input = get_command_args_as_string(context.args)
    if not arg_input:
        update.message.reply_text("使用方法: /delkeyword <关键词或短语 或 /listkeywords 显示的序号>")
        return

    subscriptions = load_user_subscriptions()
    user_config, subscriptions, modified_by_get = get_user_config_and_subscriptions(user_id_str, chat_id, subscriptions)

    if not user_config['keywords']:
        if modified_by_get: save_user_subscriptions(subscriptions)
        update.message.reply_text("您没有任何关键词可以删除。")
        return

    keyword_deleted = False
    deleted_keyword_value = "" # 未转义的，用于日志或内部逻辑
    display_deleted_keyword_value = "" # 转义后的，用于回复用户

    if arg_input.isdigit():
        try:
            index_to_delete = int(arg_input) - 1
            if 0 <= index_to_delete < len(user_config['keywords']):
                deleted_keyword_value = user_config['keywords'].pop(index_to_delete)
                display_deleted_keyword_value = telegram.utils.helpers.escape_markdown(deleted_keyword_value, version=2)
                keyword_deleted = True
            else:
                update.message.reply_text(f"⚠️ 无效的序号。请使用 /listkeywords 查看可用的关键词序号。")
                if modified_by_get: save_user_subscriptions(subscriptions)
                return
        except ValueError:
            pass
    
    if not keyword_deleted:
        keyword_to_delete_lower = arg_input.lower()
        original_length = len(user_config['keywords'])
        
        # 找到要删除的关键词的原始大小写形式
        temp_keywords = []
        found_kw_original_case = None
        for kw_idx, kw_val in enumerate(user_config['keywords']):
            if kw_val.lower() == keyword_to_delete_lower:
                found_kw_original_case = kw_val
                # 不添加到新列表，实现删除
            else:
                temp_keywords.append(kw_val)
        
        if found_kw_original_case:
            user_config['keywords'] = temp_keywords
            keyword_deleted = True
            deleted_keyword_value = found_kw_original_case # 记录原始大小写形式
            display_deleted_keyword_value = telegram.utils.helpers.escape_markdown(deleted_keyword_value, version=2)
        else:
            escaped_arg_input = telegram.utils.helpers.escape_markdown(arg_input, version=2)
            update.message.reply_text(f"⚠️ 未在您的订阅列表中找到关键词 '{escaped_arg_input}'。", parse_mode=telegram.ParseMode.MARKDOWN_V2)
            if modified_by_get: save_user_subscriptions(subscriptions)
            return

    if keyword_deleted:
        subscriptions[user_id_str] = user_config
        save_user_subscriptions(subscriptions)
        update.message.reply_text(f"🗑️ 关键词 '{display_deleted_keyword_value}' 已从您的订阅列表中移除。", parse_mode=telegram.ParseMode.MARKDOWN_V2)


def edit_keyword_command(update: telegram.Update, context: CallbackContext):
    user = update.effective_user
    user_id_str = str(user.id)
    chat_id = update.effective_chat.id
    if chat_id != user.id: return

    args = context.args
    if len(args) < 2:
        update.message.reply_text("使用方法: /editkeyword <序号> <新的关键词或短语>\n(序号来自 /listkeywords 命令)")
        return

    subscriptions = load_user_subscriptions()
    user_config, subscriptions, modified_by_get = get_user_config_and_subscriptions(user_id_str, chat_id, subscriptions)

    if not user_config['keywords']:
        if modified_by_get: save_user_subscriptions(subscriptions)
        update.message.reply_text("您没有任何关键词可以修改。")
        return

    try:
        index_to_edit = int(args[0]) - 1
        new_keyword_phrase = " ".join(args[1:]).strip()

        if not new_keyword_phrase:
            update.message.reply_text("⚠️ 新的关键词或短语不能为空。")
            if modified_by_get: save_user_subscriptions(subscriptions)
            return

        if 0 <= index_to_edit < len(user_config['keywords']):
            old_keyword = user_config['keywords'][index_to_edit]
            user_config['keywords'][index_to_edit] = new_keyword_phrase
            user_config['keywords'].sort()
            subscriptions[user_id_str] = user_config
            save_user_subscriptions(subscriptions)
            
            escaped_old_keyword = telegram.utils.helpers.escape_markdown(old_keyword, version=2)
            escaped_new_keyword = telegram.utils.helpers.escape_markdown(new_keyword_phrase, version=2)
            update.message.reply_text(f"🔄 关键词 '{escaped_old_keyword}' (序号 {index_to_edit + 1}) 已成功修改为 '{escaped_new_keyword}'。", parse_mode=telegram.ParseMode.MARKDOWN_V2)
        else:
            update.message.reply_text(f"⚠️ 无效的序号。请使用 /listkeywords 查看可用的关键词序号。")
            if modified_by_get: save_user_subscriptions(subscriptions)
    except ValueError:
        update.message.reply_text("⚠️ 第一个参数 (序号) 必须是 /listkeywords 命令显示的有效数字。")
        if modified_by_get: save_user_subscriptions(subscriptions)
    except Exception as e:
        logger.error(f"用户 {user_id_str} 执行 /editkeyword 时发生错误: {e}", exc_info=True)
        update.message.reply_text("修改关键词时发生了一个预期之外的错误，请稍后再试。")
        if modified_by_get: save_user_subscriptions(subscriptions)

def toggle_notifications_command(update: telegram.Update, context: CallbackContext, enable: bool):
    user = update.effective_user
    user_id_str = str(user.id)
    chat_id = update.effective_chat.id
    if chat_id != user.id: return

    subscriptions = load_user_subscriptions()
    user_config, subscriptions, _ = get_user_config_and_subscriptions(user_id_str, chat_id, subscriptions)

    user_config['enabled'] = enable
    subscriptions[user_id_str] = user_config
    save_user_subscriptions(subscriptions)

    status_message_unescaped = "开启" if enable else "关闭"
    escaped_status_message = telegram.utils.helpers.escape_markdown(status_message_unescaped, version=2)
    icon = "🔔" if enable else "🔕"
    update.message.reply_text(f"{icon} 您（来自此机器人的）所有通知已设为 **{escaped_status_message}**。", parse_mode=telegram.ParseMode.MARKDOWN_V2)

def enable_notifications_command(update: telegram.Update, context: CallbackContext):
    toggle_notifications_command(update, context, True)

def disable_notifications_command(update: telegram.Update, context: CallbackContext):
    toggle_notifications_command(update, context, False)

def toggle_filter_command(update: telegram.Update, context: CallbackContext):
    """处理 /togglefilter 命令，切换用户的关键词过滤模式 (已修正转义)。"""
    user = update.effective_user
    user_id_str = str(user.id)
    chat_id = update.effective_chat.id
    if chat_id != user.id: return

    subscriptions = load_user_subscriptions()
    user_config, subscriptions, modified_by_get = get_user_config_and_subscriptions(user_id_str, chat_id, subscriptions)

    current_filter_state = user_config.get("keyword_filter_active", True)
    user_config["keyword_filter_active"] = not current_filter_state
    
    subscriptions[user_id_str] = user_config
    save_user_subscriptions(subscriptions)

    if user_config["keyword_filter_active"]:
        state_description_unescaped = "开启 (仅推送匹配关键词的帖子)"
    else:
        state_description_unescaped = "关闭 (推送所有帖子)"
    
    escaped_state_description = telegram.utils.helpers.escape_markdown(state_description_unescaped, version=2)
    icon = "🔎" if user_config["keyword_filter_active"] else "📢"
    
    note_unescaped = "（请注意：总体通知开关 /enablenotifications 必须也为开启状态才会收到推送。）"
    note_standard_parentheses = note_unescaped.replace("（", "(").replace("）", ")")
    escaped_note = telegram.utils.helpers.escape_markdown(note_standard_parentheses, version=2)

    message_to_send = (f"{icon} 您的关键词过滤模式已更新为: **{escaped_state_description}**。\n"
                       f"{escaped_note}")

    update.message.reply_text(message_to_send,
                              parse_mode=telegram.ParseMode.MARKDOWN_V2)

def my_rss_status_command(update: telegram.Update, context: CallbackContext):
    """处理 /myrssstatus 命令，显示用户的当前订阅状态和关键词 (已修正转义)。"""
    user = update.effective_user
    user_id_str = str(user.id)
    chat_id = update.effective_chat.id
    if chat_id != user.id: return

    subscriptions = load_user_subscriptions()
    user_config, subscriptions, modified_by_get = get_user_config_and_subscriptions(user_id_str, chat_id, subscriptions)
    if modified_by_get: save_user_subscriptions(subscriptions)

    enabled_status_text_unescaped = "开启" if user_config.get('enabled', True) else "关闭"
    escaped_enabled_status_text = telegram.utils.helpers.escape_markdown(enabled_status_text_unescaped, version=2)
    enabled_icon = "🔔" if user_config.get('enabled', True) else "🔕"
    
    filter_active = user_config.get('keyword_filter_active', True)
    filter_status_text_part_unescaped = "开启 (仅关键词)" if filter_active else "关闭 (所有帖子)"
    escaped_filter_status_text_part = telegram.utils.helpers.escape_markdown(filter_status_text_part_unescaped, version=2)
    filter_icon = "🔎" if filter_active else "📢"
    
    message_parts = [
        telegram.utils.helpers.escape_markdown("ℹ️ 您当前的 RSS 订阅状态:", version=2),
        f"{enabled_icon} {telegram.utils.helpers.escape_markdown('总体通知: ', version=2)}**{escaped_enabled_status_text}**",
        f"{filter_icon} {telegram.utils.helpers.escape_markdown('关键词过滤: ', version=2)}**{escaped_filter_status_text_part}**",
        "" # 用于换行
    ]
    
    if not user_config['keywords']:
        message_parts.append(telegram.utils.helpers.escape_markdown("📜 关键词列表: 您还没有设置任何关键词。", version=2))
    else:
        keywords_list_str = telegram.utils.helpers.escape_markdown("📜 您已设置的关键词 (匹配时不区分大小写):", version=2) + "\n"
        for i, kw in enumerate(user_config['keywords']):
            keywords_list_str += f"  {i+1}\\. {telegram.utils.helpers.escape_markdown(kw, version=2)}\n"
        message_parts.append(keywords_list_str.strip())
    
    if filter_active and not user_config['keywords']:
        tip_unescaped = "提示: 当前关键词过滤已开启，但您没有设置任何关键词，因此不会收到任何帖子。请添加关键词或使用 /togglefilter 关闭过滤以接收所有帖子。"
        escaped_tip = telegram.utils.helpers.escape_markdown(tip_unescaped, version=2)
        message_parts.append(f"\n**⚠️** {escaped_tip}")
        
    update.message.reply_text("\n".join(message_parts), parse_mode=telegram.ParseMode.MARKDOWN_V2)


def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(f'Update "{update}" 造成错误 "{context.error}"', exc_info=context.error)
    if ADMIN_CHAT_ID and isinstance(context.error, Exception):
        try:
            error_detail = f"RSS 机器人错误:\n类型: {type(context.error).__name__}\n错误信息: {context.error}\n"
            if update and hasattr(update, 'effective_message') and update.effective_message:
                 error_detail += f"导致错误的更新: {update.effective_message.to_json()}"
            elif update:
                 error_detail += f"Update 对象: {str(update)}"
            context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=error_detail[:4000])
        except Exception as e_admin_send:
            logger.error(f"向管理员 ({ADMIN_CHAT_ID}) 发送错误详情失败: {e_admin_send}", exc_info=True)

# --- 主函数 ---
def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("严重错误: 环境变量 TELEGRAM_BOT_TOKEN 未设置。机器人无法启动。")
        return

    logger.info("机器人正在启动...")
    if ADMIN_CHAT_ID:
        logger.info(f"管理员通知将发送到 Chat ID: {ADMIN_CHAT_ID}")
    else:
        logger.info("环境变量 ADMIN_CHAT_ID 未设置。管理员通知将仅记录到日志。")

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True) # 使用 python-telegram-bot v13.x
    dp = updater.dispatcher
    jq = updater.job_queue

    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("addkeyword", add_keyword_command))
    dp.add_handler(CommandHandler("listkeywords", list_keywords_command))
    dp.add_handler(CommandHandler("delkeyword", del_keyword_command))
    dp.add_handler(CommandHandler("editkeyword", edit_keyword_command))
    dp.add_handler(CommandHandler("togglefilter", toggle_filter_command))
    dp.add_handler(CommandHandler("enablenotifications", enable_notifications_command))
    dp.add_handler(CommandHandler("disablenotifications", disable_notifications_command))
    dp.add_handler(CommandHandler("myrssstatus", my_rss_status_command))

    dp.add_error_handler(error_handler)

    jq.run_repeating(check_rss_and_send_to_users, interval=CHECK_INTERVAL_SECONDS, first=10)
    logger.info(f"RSS 检查任务已安排。间隔时间: {CHECK_INTERVAL_SECONDS} 秒。")

    updater.start_polling()
    logger.info("机器人已启动并开始轮询更新。")

    if ADMIN_CHAT_ID:
        try:
            current_time_str = time.strftime('%Y-%m-%d %H:%M:%S %Z')
            updater.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"🤖 NodeSeek RSS 机器人 (多用户版) 已于 {current_time_str} 成功启动。")
        except Exception as e:
            logger.warning(f"无法向管理员 ({ADMIN_CHAT_ID}) 发送启动成功消息: {e}")

    updater.idle()
    logger.info("机器人已停止。")

if __name__ == '__main__':
    main()