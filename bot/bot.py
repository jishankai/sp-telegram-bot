import os
import logging
import traceback
import html
import json
import requests
import re
from datetime import datetime
from pathlib import Path

import telegram
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from telegram.constants import ParseMode, ChatAction

import config
import database
import chatgpt
import deribit_ws


# setup
db = database.Database()
logger = logging.getLogger(__name__)
bot = telegram.Bot(token=config.telegram_token)

START_MESSAGE = """
<i>
Commands:
- /coin – Token's Info[eg. /coin btc]
- /help – Help

Want to know what whales are doing in the options market? Contact ​@pieceofelephant and receive Block Trade Alert for free!
</i>
"""
HELP_MESSAGE = """
<i>
Commands:
- @signalplus_derivatives_bot - ChatGPT function [eg. @signalplus_derivatives_bot how to price options?]
- /coin – Token's Info[eg. /coin btc]
- /help – Help

Want to know what whales are doing in the options market? Contact ​@pieceofelephant and receive Block Trade Alert for free!
</i>
"""
config_dir = Path(__file__).parent.parent.resolve() / "config"
with open(config_dir / "SYMBOL2ID.json", 'r') as f:
    symbol_to_id = json.load(f)

async def register_user_if_not_exists(update: Update, context: CallbackContext, user: User):
    if not db.check_if_user_exists(user.id):
        db.add_new_user(
            user.id,
            update.message.chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name= user.last_name
        )
        db.start_new_dialog(user.id)

    if db.get_user_attribute(user.id, "current_dialog_id") is None:
        db.start_new_dialog(user.id)


async def start_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.start_new_dialog(user_id)
    
    reply_text = "Hi! I'm <b>SignalPlus</b> bot. How can I help you today? 🤖"
    reply_text += START_MESSAGE
    
    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)

async def help_handle(update: Update, context: CallbackContext):
    await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.HTML)

async def coin_handle(update: Update, context: CallbackContext):
    args = context.args
    if len(args) == 0:
        await update.message.reply_text('eg. /coin btc')
        return
    
    currency = args[0].upper()
    id = symbol_to_id.get(currency)
    if id is None:
        await update.message.reply_text('Token cannot be found. Please check its symbol is correct.')
        return

    # 发送请求获取货币数据
    url = 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={}'.format(id)
    response = requests.get(url)
    if response.status_code != 200:
        await update.message.reply_text('Data is not available. Please try again later.')
        return
    data = response.json()
    if len(data) == 0:
        await update.message.reply_text('Token cannot be found. Please check its symbol is correct.')
        return

    try:
        name = data[0]['name']
        price = data[0]['current_price']
        change = data[0]['price_change_percentage_24h']
        high_24h = data[0]['high_24h']
        low_24h = data[0]['low_24h']
        volume = data[0]['total_volume']
        market_cap = data[0]['market_cap']
        market_cap_rank = data[0]['market_cap_rank']

        # 发送响应消息
        if currency in ["BTC", "ETH"]:
            deribit_ws_instance = deribit_ws.DeribitWS(client_id=config.deribit_id, client_secret=config.deribit_secret)
            res = await deribit_ws_instance.ws_operation("subscribe", f"deribit_volatility_index.{currency.lower()}_usd")
            if not res["params"]["data"]["volatility"]:
                logger.error("DVOL is not available.")
                message = f'<i>📜{name}📜\n\nRank:{market_cap_rank}\n1 Day Price Change: {change:.2f}%{"📈" if change>0 else "📉"}\n💵Price: ${price:.6f}\n⬆️High in 24 hours: ${high_24h:.6f}\n⬇️Low in 24 hours: ${low_24h:.6f}\nTotal Volume: ${volume:,}\nMarket Cap: ${market_cap:,}</i>'
            else:
                message = f'<i>📜{name}📜\n\nRank:{market_cap_rank}\n1 Day Price Change: {change:.2f}%{"📈" if change>0 else "📉"}\n💵Price: ${price:.6f}\n⬆️High in 24 hours: ${high_24h:.6f}\n⬇️Low in 24 hours: ${low_24h:.6f}\nTotal Volume: ${volume:,}\nMarket Cap: ${market_cap:,}\nDVOL: {res["params"]["data"]["volatility"]:.2f}</i>'
                
        else:
            message = f'<i>📜{name}📜\n\nRank:{market_cap_rank}\n1 Day Price Change: {change:.2f}%{"📈" if change>0 else "📉"}\n💵Price: ${price:.6f}\n⬆️High in 24 hours: ${high_24h:.6f}\n⬇️Low in 24 hours: ${low_24h:.6f}\nTotal Volume: ${volume:,}\nMarket Cap: ${market_cap:,}</i>'

        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    except Exception as e:
        error_text = f"Something went wrong during completion.\nReason: {e}"
        logger.error(error_text)
        await update.message.reply_text('Data is not available.')


async def message_handle(update: Update, context: CallbackContext, message=None, use_new_dialog_timeout=True):
    # check if message is edited
    if update.edited_message is not None:
        return

    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    # new dialog timeout
    if use_new_dialog_timeout:
        if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
            db.start_new_dialog(user_id)
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    try:
        message = message or update.message.text
        chat_type = update.message.chat.type
        if chat_type == 'private' or (chat_type in ['group', 'supergroup'] and config.bot_id in message):
            # collect group id
            await update_group_info(update.message.chat.id, update.message.chat.title)

            # send typing action
            await update.message.chat.send_action(action="typing")


            if re.search(config.filtered_pattern, message):
                text = "<i>我是一个衍生品专家，建议不要跟我讨论政治问题。但是您有任何关于期权交易的问题，我会很乐意为您效劳。</i>"
                await update.message.reply_text(text, parse_mode=ParseMode.HTML)
                return
            else:
                chatgpt_instance = chatgpt.ChatGPT(use_chatgpt_api=config.use_chatgpt_api)
                answer, n_used_tokens, n_first_dialog_messages_removed = await chatgpt_instance.send_message(
                    message,
                    dialog_messages=db.get_dialog_messages(user_id, dialog_id=None),
                    chat_mode=db.get_user_attribute(user_id, "current_chat_mode"),
                )

                # update user data
                new_dialog_message = {"user": message, "bot": answer, "date": datetime.now()}
                db.set_dialog_messages(
                    user_id,
                    db.get_dialog_messages(user_id, dialog_id=None) + [new_dialog_message],
                    dialog_id=None
                )

                db.set_user_attribute(user_id, "n_used_tokens", n_used_tokens + db.get_user_attribute(user_id, "n_used_tokens"))
                # send message if some messages were removed from the context
                if n_first_dialog_messages_removed > 0:
                    if n_first_dialog_messages_removed == 1:
                        text = "✍️ <i>Note:</i> Your current dialog is too long, so your <b>first message</b> was removed from the context."
                    else:
                        text = f"✍️ <i>Note:</i> Your current dialog is too long, so <b>{n_first_dialog_messages_removed} first messages</b> were removed from the context."

                    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

                try:
                    answer += "\n\n<i>Join the SignalPlus Community, Master Advanced Trading Strategies and Macro Analysis, and Start Your Journey to Success: https://t.me/SignalPlus_Playground. \n\nThe Ultimate Tools for Professional Traders: https://t.signalplus.com</i>."
                    await update.message.reply_text(answer, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except telegram.error.BadRequest:
                    # answer has invalid characters, so we send it without parse_mode
                    answer += "  Join the SignalPlus Community, Master Advanced Trading Strategies and Macro Analysis, and Start Your Journey to Success: https://t.me/SignalPlus_Playground. The Ultimate Tools for Professional Traders: https://t.signalplus.com."
                    await update.message.reply_text(answer, disable_web_page_preview=True)

    except Exception as e:
        error_text = f"Something went wrong during completion.\nReason: {e}"
        logger.error(error_text)
        await update.message.reply_text(error_text)


async def error_handle(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    try:
        # collect error message
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)[:2000]
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        message = (
            f"An exception was raised while handling an update\n"
            f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
            "</pre>\n\n"
            f"<pre>{html.escape(tb_string)}</pre>"
        )

        logger.error(message)
    except:
        logger.error("Error")


async def update_group_info(group_id, group_name) -> None:
    members_count = await bot.get_chat_member_count(chat_id=group_id)
    db.add_or_update_group(group_id, group_name, members_count)

def run_bot() -> None:
    application = (
        ApplicationBuilder()
        .token(config.telegram_token)
        .build()
    )

    # add handlers
    if len(config.allowed_telegram_usernames) == 0:
        user_filter = filters.ALL
    else:
        user_filter = filters.User(username=config.allowed_telegram_usernames)

    application.add_handler(CommandHandler("start", start_handle, filters=user_filter))
    application.add_handler(CommandHandler("help", help_handle, filters=user_filter))
    application.add_handler(CommandHandler("coin", coin_handle, filters=user_filter))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, message_handle))
    application.add_error_handler(error_handle)
    
    # start the bot
    application.run_polling()


if __name__ == "__main__":
    run_bot()
    
