"""Handlers for workout history viewing."""

import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, desc
from database import AsyncSessionLocal, WorkoutLog


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    two_weeks_ago = datetime.datetime.now() - datetime.timedelta(days=14)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkoutLog)
            .where(WorkoutLog.user_id == user_id)
            .where(WorkoutLog.timestamp >= two_weeks_ago)
            .order_by(desc(WorkoutLog.timestamp))
        )
        logs = result.scalars().all()

    if not logs:
        await update.message.reply_text(
            "No workouts in the last 2 weeks. Time to get moving! 💪"
        )
        return

    workouts_by_date = {}
    for log in logs:
        date_key = log.timestamp.date()
        template_name = log.template_name or "Unknown"
        key = (date_key, template_name)
        if key not in workouts_by_date:
            workouts_by_date[key] = []
        workouts_by_date[key].append(log)

    keyboard = []
    for date, template_name in sorted(workouts_by_date.keys(), reverse=True):
        log_count = len(workouts_by_date[(date, template_name)])
        date_str = date.strftime("%b %d, %Y")
        callback_data = f"hist_{date.isoformat()}_{template_name}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📅 {date_str} - {template_name} ({log_count} exercises)",
                    callback_data=callback_data,
                )
            ]
        )

    text = "🏋️ Your workouts from the last 2 weeks:"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def history_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for viewing workout details."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "hist_back":
        return await history_back_callback(update, context)

    if not data.startswith("hist_"):
        return

    parts = data.replace("hist_", "").split("_", 1)
    date_str = parts[0]
    template_name = parts[1] if len(parts) > 1 else ""
    date = datetime.datetime.fromisoformat(date_str).date()
    user_id = update.effective_user.id

    next_day = date + datetime.timedelta(days=1)

    async with AsyncSessionLocal() as session:
        if template_name:
            result = await session.execute(
                select(WorkoutLog)
                .where(WorkoutLog.user_id == user_id)
                .where(
                    WorkoutLog.timestamp
                    >= datetime.datetime.combine(date, datetime.datetime.min.time())
                )
                .where(
                    WorkoutLog.timestamp
                    < datetime.datetime.combine(next_day, datetime.datetime.min.time())
                )
                .where(WorkoutLog.template_name == template_name)
            )
        else:
            result = await session.execute(
                select(WorkoutLog)
                .where(WorkoutLog.user_id == user_id)
                .where(
                    WorkoutLog.timestamp
                    >= datetime.datetime.combine(date, datetime.datetime.min.time())
                )
                .where(
                    WorkoutLog.timestamp
                    < datetime.datetime.combine(next_day, datetime.datetime.min.time())
                )
            )
        logs = result.scalars().all()

    if not logs:
        await query.edit_message_text(f"No exercises logged on {date}.")
        return

    log_text = f"💪 Workout on {date.strftime('%B %d, %Y')}"
    if template_name:
        log_text += f" - {template_name}"
    log_text += ":\n\n"

    exercise_summary = {}
    for log in logs:
        key = f"{log.exercise_name}"
        if key not in exercise_summary:
            exercise_summary[key] = {
                "sets": 0,
                "weight": log.weight,
                "reps": log.reps,
                "volume": 0,
            }
        exercise_summary[key]["sets"] += 1
        exercise_summary[key]["volume"] += log.sets * log.weight * log.reps

    for ex_name, ex_data in exercise_summary.items():
        log_text += f"• {ex_name}: {ex_data['sets']} set(s) @ {ex_data['weight']}kg x {ex_data['reps']} reps ({ex_data['volume']}kg vol)\n"

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="hist_back")]]
    await query.edit_message_text(log_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def history_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button in history detail view."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data != "hist_back":
        return

    user_id = update.effective_user.id
    two_weeks_ago = datetime.datetime.now() - datetime.timedelta(days=14)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkoutLog)
            .where(WorkoutLog.user_id == user_id)
            .where(WorkoutLog.timestamp >= two_weeks_ago)
            .order_by(desc(WorkoutLog.timestamp))
        )
        logs = result.scalars().all()

    if not logs:
        await query.edit_message_text(
            "No workouts in the last 2 weeks. Time to get moving! 💪"
        )
        return

    workouts_by_date = {}
    for log in logs:
        date_key = log.timestamp.date()
        template_name = log.template_name or "Unknown"
        key = (date_key, template_name)
        if key not in workouts_by_date:
            workouts_by_date[key] = []
        workouts_by_date[key].append(log)

    keyboard = []
    for date, template_name in sorted(workouts_by_date.keys(), reverse=True):
        log_count = len(workouts_by_date[(date, template_name)])
        date_str = date.strftime("%b %d, %Y")
        callback_data = f"hist_{date.isoformat()}_{template_name}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📅 {date_str} - {template_name} ({log_count} exercises)",
                    callback_data=callback_data,
                )
            ]
        )

    await query.edit_message_text(
        "🏋️ Your workouts from the last 2 weeks:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
