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
    "🔥 **WELCOME TO GYMBOT v2.0!** 🔥\n"
        "Your digital spotter for massive gains. 🦾✨\n\n"
        
        "🛠️ **BUILD YOUR ROUTINE**\n"
        "────────────────────\n"
        "📝 /create_template — Manual step-by-step setup 🏗️\n"
        "🤖 /add_template_ai — Just type it, I'll build it! 🧠⚡\n"
        "🎯 /recommend_template — Get a PRO routine based on YOUR stats 📈💎\n"
        "✏️ /edit_template — Tweak your existing gains-blueprints 🛠️\n\n"
        
        "🏋️ **TIME TO LIFT**\n"
        "────────────────────\n"
        "🚀 /start_workout — Let's hit the iron! 🔔🔥\n"
        "📅 /history — See your consistency calendar 🗓️💪\n\n"
        
        "⚙️ **SYSTEM**\n"
        "────────────────────\n"
        "🔧 /settings — Adjust units, bio, and LLM preferences ⚙️\n\n"
        
        "**What are we smashing today?** 👇"
    )
    try:
        if common.last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    common.last_msg_id = update.message.message_id
