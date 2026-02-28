"""Handler for the /start command."""

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select
from database import AsyncSessionLocal, User
from handlers.common import last_msg_id as _last_msg_id
import handlers.common as common


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(id=user_id, username=username)
            session.add(user)
            await session.commit()
        else:
            context.user_data["default_rest_seconds"] = user.default_rest_seconds

    await update.message.reply_text(
        "Welcome to GymBot! 💪\n"
        "Commands:\n"
        "/create_template - Create a new workout routine (step-by-step)\n"
        "/add_template_ai - Create a workout routine using AI (natural language)\n"
        "/edit_template - Edit an existing template\n"
        "/start_workout - Start logging a workout\n"
        "/history - View workout calendar\n"
        "/settings - Change your settings"
    )
    try:
        if common.last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    common.last_msg_id = update.message.message_id
