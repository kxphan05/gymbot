"""Handlers for user settings (rest time configuration)."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from sqlalchemy import select
from database import AsyncSessionLocal, User
import handlers.common as common


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user settings and options to change them."""
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        default_rest = user.default_rest_seconds if user else 300

    minutes = default_rest // 60
    seconds = default_rest % 60
    if seconds > 0:
        rest_text = f"{minutes}m{seconds}s"
    else:
        rest_text = f"{minutes}m"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"⏰ Rest Time: {rest_text}", callback_data="set_rest"
                )
            ],
        ]
    )

    await update.message.reply_text(
        f"⚙️ Your Settings:\n\nDefault Rest Time: {rest_text}\n\nTap below to change:",
        reply_markup=keyboard,
    )


async def settings_rest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt for new rest time."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Enter your default rest time in seconds (e.g., 90 for 1:30, 180 for 3m):"
    )
    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id, message_id=common.last_msg_id
            )
        except Exception as e:
            print(f"Could not delete: {e}")
    common.last_msg_id = query.message.message_id
    return common.SETTINGS_REST_CONFIRM


async def settings_rest_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the new rest time."""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    try:
        rest_seconds = int(text)
        if rest_seconds <= 0 or rest_seconds > 600:
            await update.message.reply_text(
                "Please enter between 1-600 seconds (10 minutes max)."
            )
            return common.SETTINGS_REST_CONFIRM
    except ValueError:
        await update.message.reply_text("Invalid number. Enter seconds (e.g., 90):")
        return common.SETTINGS_REST_CONFIRM

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.default_rest_seconds = rest_seconds
            await session.commit()

    context.user_data["default_rest_seconds"] = rest_seconds

    minutes = rest_seconds // 60
    seconds = rest_seconds % 60
    if seconds > 0:
        rest_text = f"{minutes}m{seconds}s"
    else:
        rest_text = f"{minutes}m"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"⏰ Rest Time: {rest_text}", callback_data="set_rest"
                )
            ],
        ]
    )

    await update.message.reply_text(
        f"✅ Default rest time updated to {rest_text}!",
    )
    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
        except Exception as e:
            print(f"Could not delete: {e}")
    common.last_msg_id = update.message.message_id
    return ConversationHandler.END
