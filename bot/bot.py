import os
import logging
import traceback
import html
import json
from datetime import datetime

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


# setup
db = database.Database()
logger = logging.getLogger(__name__)

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
    
    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)

async def message_handle(update: Update, context: CallbackContext, message=None, use_new_dialog_timeout=True):
    # check if message is edited
    if update.edited_message is not None:
        await edited_message_handle(update, context)
        return

    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    # new dialog timeout
    if use_new_dialog_timeout:
        if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
            db.start_new_dialog(user_id)
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    # send typing action
    await update.message.chat.send_action(action="typing")

    try:
        message = message or update.message.text
        chat_type = update.message.chat.type
        if chat_type == 'private' or (chat_type == 'group' and config.bot_id in message):
            chatgpt_instance = chatgpt.ChatGPT(use_chatgpt_api=config.use_chatgpt_api)
            answer, n_used_tokens, n_first_dialog_messages_removed = chatgpt_instance.send_message(
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
                await update.message.reply_text(answer, parse_mode=ParseMode.HTML)
            except telegram.error.BadRequest:
                # answer has invalid characters, so we send it without parse_mode
                await update.message.reply_text(answer)

    except Exception as e:
        error_text = f"Something went wrong during completion.\nReason: {e}"
        logger.error(error_text)
        await update.message.reply_text(error_text)
        return


async def edited_message_handle(update: Update, context: CallbackContext):
    text = "🥲 Unfortunately, message <b>editing</b> is not supported"
    await update.edited_message.reply_text(text, parse_mode=ParseMode.HTML)


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

        # split text into multiple messages due to 4096 character limit
        message_chunk_size = 4000
        message_chunks = [message[i:i + message_chunk_size] for i in range(0, len(message), message_chunk_size)]
        for message_chunk in message_chunks:
            await context.bot.send_message(update.effective_chat.id, message_chunk, parse_mode=ParseMode.HTML)
    except:
        await context.bot.send_message(update.effective_chat.id, "Some error in error handler")

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

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, message_handle))
    
    application.add_error_handler(error_handle)
    
    # start the bot
    application.run_polling()


if __name__ == "__main__":
    run_bot()
    
