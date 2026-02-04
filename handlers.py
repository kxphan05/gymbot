import datetime
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from database import AsyncSessionLocal, User, Template, TemplateExercise, WorkoutLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


(
    TEMPLATE_NAME,
    EXERCISE_NAME,
    EXERCISE_DETAILS,
    WORKOUT_TEMPLATE_SELECT,
    WORKOUT_EXERCISE_CONFIRM,
    WORKOUT_EXERCISE_INPUT,
    EXERCISE_SETS_INPUT,
) = range(7)

WEIGHT_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("10", callback_data="w_10"),
            InlineKeyboardButton("15", callback_data="w_15"),
            InlineKeyboardButton("20", callback_data="w_20"),
            InlineKeyboardButton("25", callback_data="w_25"),
        ],
        [
            InlineKeyboardButton("30", callback_data="w_30"),
            InlineKeyboardButton("35", callback_data="w_35"),
            InlineKeyboardButton("40", callback_data="w_40"),
            InlineKeyboardButton("45", callback_data="w_45"),
        ],
        [
            InlineKeyboardButton("50", callback_data="w_50"),
            InlineKeyboardButton("55", callback_data="w_55"),
            InlineKeyboardButton("60", callback_data="w_60"),
            InlineKeyboardButton("65", callback_data="w_65"),
        ],
        [
            InlineKeyboardButton("70", callback_data="w_70"),
            InlineKeyboardButton("75", callback_data="w_75"),
            InlineKeyboardButton("80", callback_data="w_80"),
            InlineKeyboardButton("85", callback_data="w_85"),
        ],
        [
            InlineKeyboardButton("90", callback_data="w_90"),
            InlineKeyboardButton("95", callback_data="w_95"),
            InlineKeyboardButton("100", callback_data="w_100"),
            InlineKeyboardButton("Custom", callback_data="w_custom"),
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="w_back"),
        ],
    ]
)

REPS_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("1", callback_data="r_1"),
            InlineKeyboardButton("2", callback_data="r_2"),
            InlineKeyboardButton("3", callback_data="r_3"),
            InlineKeyboardButton("4", callback_data="r_4"),
        ],
        [
            InlineKeyboardButton("5", callback_data="r_5"),
            InlineKeyboardButton("6", callback_data="r_6"),
            InlineKeyboardButton("7", callback_data="r_7"),
            InlineKeyboardButton("8", callback_data="r_8"),
        ],
        [
            InlineKeyboardButton("9", callback_data="r_9"),
            InlineKeyboardButton("10", callback_data="r_10"),
            InlineKeyboardButton("11", callback_data="r_11"),
            InlineKeyboardButton("12", callback_data="r_12"),
        ],
        [
            InlineKeyboardButton("13", callback_data="r_13"),
            InlineKeyboardButton("14", callback_data="r_14"),
            InlineKeyboardButton("15", callback_data="r_15"),
            InlineKeyboardButton("16", callback_data="r_16"),
        ],
        [
            InlineKeyboardButton("17", callback_data="r_17"),
            InlineKeyboardButton("18", callback_data="r_18"),
            InlineKeyboardButton("19", callback_data="r_19"),
            InlineKeyboardButton("20", callback_data="r_20"),
        ],
        [
            InlineKeyboardButton("⬅️ Back to Weight", callback_data="r_back"),
        ],
    ]
)


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

    await update.message.reply_text(
        "Welcome to GymBot! 💪\n"
        "Commands:\n"
        "/create_template - Create a new workout routine\n"
        "/start_workout - Start logging a workout\n"
        "/history - View workout calendar"
    )


async def create_template_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Let's create a workout template. What specific name would you like to give this routine? (e.g., 'Leg Day')"
    )
    return TEMPLATE_NAME


async def template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["template_name"] = name
    context.user_data["exercises"] = []
    await update.message.reply_text(
        f"Template '{name}' started. Enter the first exercise name (or /done to finish):"
    )
    return EXERCISE_NAME


async def exercise_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() == "/done":
        return await save_template(update, context)

    context.user_data["current_exercise_name"] = text.strip()
    await update.message.reply_text(
        f"Enter default sets, weight (kg), and reps for {text} separated by space (e.g., '3 50 10'):"
    )
    return EXERCISE_DETAILS


async def exercise_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text.lower() == "/done":
        return await save_template(update, context)

    parts = text.split()

    if len(parts) != 3:
        await update.message.reply_text(
            "Invalid format. Please enter 'Sets Weight Reps' (e.g., '3 50 10'):"
        )
        return EXERCISE_DETAILS

    try:
        sets = int(parts[0])
        weight = float(parts[1])
        reps = int(parts[2])

        if sets <= 0 or reps <= 0:
            raise ValueError("Values must be positive")
    except ValueError:
        await update.message.reply_text(
            "Invalid format. Please enter positive numbers for Sets and Reps (e.g., '3 50 10'):"
        )
        return EXERCISE_DETAILS

    exercises = context.user_data.get("exercises", [])
    exercises.append(
        {
            "name": context.user_data["current_exercise_name"],
            "sets": sets,
            "weight": weight,
            "reps": reps,
        }
    )
    context.user_data["exercises"] = exercises

    await update.message.reply_text(
        "Exercise added. Enter next exercise name (or /done to finish):"
    )
    return EXERCISE_NAME


async def save_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = context.user_data.get("template_name", "Unnamed Template")
    exercises_data = context.user_data.get("exercises", [])

    logger.info(f"save_template called: name={name}, exercises={len(exercises_data)}")

    if not exercises_data:
        await update.message.reply_text(
            "Cannot save template with no exercises. Use /create_template to start again."
        )
        context.user_data.clear()
        return ConversationHandler.END

    async with AsyncSessionLocal() as session:
        template = Template(name=name, user_id=user_id)
        session.add(template)
        await session.flush()

        for idx, ex_data in enumerate(exercises_data):
            ex = TemplateExercise(
                template_id=template.id,
                exercise_name=ex_data["name"],
                default_sets=ex_data["sets"],
                default_weight=ex_data["weight"],
                default_reps=ex_data["reps"],
                order=idx,
            )
            session.add(ex)

        try:
            await session.commit()
            logger.info(f"Template saved successfully: {name}")
            await update.message.reply_text(
                f"Template '{name}' saved with {len(exercises_data)} exercises! ✅"
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"Error saving template: {e}")
            await update.message.reply_text("Error saving template. Please try again.")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Action canceled.")
    context.user_data.clear()
    return ConversationHandler.END


async def done_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /done command during template creation."""
    logger.info(
        f"done_handler called: user_data keys = {list(context.user_data.keys())}"
    )
    return await save_template(update, context)


async def start_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"start_workout called by user {user_id}")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Template).where(Template.user_id == user_id)
        )
        templates = result.scalars().all()
        logger.info(f"Found {len(templates)} templates for user {user_id}")

    if not templates:
        await update.message.reply_text(
            "No templates found. Use /create_template to add one first!"
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(t.name, callback_data=f"tmpl_{t.id}")] for t in templates
    ]
    logger.info(f"Sending template selection keyboard with {len(keyboard)} options")
    await update.message.reply_text(
        "Select a workout template:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WORKOUT_TEMPLATE_SELECT


async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    template_id = int(query.data.split("_")[1])
    logger.info(f"Template selected: {template_id}")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Template)
            .where(Template.id == template_id)
            .options(selectinload(Template.exercises))
        )
        template = result.scalar_one()
        exercises = sorted(template.exercises, key=lambda x: x.order)
        logger.info(f"Template {template.name} has {len(exercises)} exercises")

    context.user_data["current_workout"] = {
        "exercises": [
            {
                "name": ex.exercise_name,
                "default_sets": ex.default_sets,
                "default_weight": ex.default_weight,
                "default_reps": ex.default_reps,
            }
            for ex in exercises
        ],
        "current_index": 0,
        "logged_sets": {},
    }

    await process_next_exercise(query.message, context, query.from_user.id)
    return WORKOUT_EXERCISE_CONFIRM


async def process_next_exercise(message, context, user_id):
    workout_data = context.user_data["current_workout"]
    idx = workout_data["current_index"]

    logger.info(f"process_next_exercise: index={idx}/{len(workout_data['exercises'])}")

    if idx >= len(workout_data["exercises"]):
        workout_data.clear()
        await message.reply_text("Workout complete! Great job! 🎉")
        return ConversationHandler.END

    ex_data = workout_data["exercises"][idx]
    logged_sets = workout_data["logged_sets"].get(idx, 0)

    prev_log_text = "No history"
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkoutLog)
            .where(
                WorkoutLog.user_id == user_id,
                WorkoutLog.exercise_name == ex_data["name"],
            )
            .order_by(desc(WorkoutLog.timestamp))
            .limit(1)
        )
        prev_log = result.scalar_one_or_none()
        if prev_log:
            prev_log_text = f"{prev_log.sets}s x {prev_log.weight}kg x {prev_log.reps}"

    text = (
        f"**Exercise {idx + 1}/{len(workout_data['exercises'])}: {ex_data['name']}**\n"
        f"Progress: {logged_sets}/{ex_data['default_sets']} sets completed\n"
        f"Previous: {prev_log_text}\n"
        f"Target: {ex_data['default_sets']}s x {ex_data['default_weight']}kg x {ex_data['default_reps']}"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm Set", callback_data="confirm"),
            InlineKeyboardButton("✏️ Log Set", callback_data="log_set"),
        ],
        [InlineKeyboardButton("⏰ Rest 60s", callback_data="rest")],
        [InlineKeyboardButton("Skip Exercise ➡️", callback_data="skip")],
    ]

    logger.info(f"Sending exercise keyboard for {ex_data['name']}")

    if hasattr(message, "edit_text"):
        await message.edit_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await message.reply_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_exercise_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    logger.info(f"handle_exercise_action: data={data}")

    if data == "rest":
        await query.message.reply_text("Rest timer started: 60 seconds. ⏳")
        context.job_queue.run_once(
            rest_timer_callback, 60, chat_id=query.message.chat_id
        )
        return WORKOUT_EXERCISE_CONFIRM

    if data == "skip":
        workout_data = context.user_data["current_workout"]
        workout_data["current_index"] += 1
        await process_next_exercise(query.message, context, user_id)
        return WORKOUT_EXERCISE_CONFIRM

    if data == "confirm":
        workout_data = context.user_data["current_workout"]
        idx = workout_data["current_index"]
        ex_data = workout_data["exercises"][idx]
        logged_sets = workout_data["logged_sets"].get(idx, 0)

        if logged_sets == 0:
            await query.message.reply_text(
                "Please log at least one set before confirming."
            )
            return WORKOUT_EXERCISE_CONFIRM

        for s in range(logged_sets):
            log = WorkoutLog(
                user_id=user_id,
                exercise_name=ex_data["name"],
                sets=1,
                weight=ex_data["default_weight"],
                reps=ex_data["default_reps"],
            )
            async with AsyncSessionLocal() as session:
                session.add(log)
                await session.commit()

        workout_data["current_index"] += 1
        workout_data["logged_sets"][idx] = 0
        await process_next_exercise(query.message, context, user_id)
        return WORKOUT_EXERCISE_CONFIRM

    if data == "log_set":
        context.user_data["pending_weight"] = None
        context.user_data["pending_reps"] = None
        await query.message.edit_text(
            "Select weight for this set:",
            reply_markup=WEIGHT_KEYBOARD,
        )
        return WORKOUT_EXERCISE_INPUT

    if data.startswith("w_"):
        return await handle_weight_select(update, context, user_id)

    if data.startswith("r_"):
        return await handle_reps_select(update, context, user_id)


async def handle_weight_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id
):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "w_back":
        await query.message.delete()
        await process_next_exercise(query.message, context, user_id)
        return WORKOUT_EXERCISE_CONFIRM

    if data == "w_custom":
        await query.message.edit_text(
            "Enter custom weight (kg):",
        )
        context.user_data["waiting_for_weight"] = True
        return WORKOUT_EXERCISE_INPUT

    weight = float(data.replace("w_", ""))
    context.user_data["pending_weight"] = weight

    await query.message.edit_text(
        f"Weight: {weight}kg\nSelect reps for this set:",
        reply_markup=REPS_KEYBOARD,
    )
    return WORKOUT_EXERCISE_INPUT


async def handle_reps_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id
):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "r_back":
        await query.message.edit_text(
            "Select weight for this set:",
            reply_markup=WEIGHT_KEYBOARD,
        )
        return WORKOUT_EXERCISE_INPUT

    reps = int(data.replace("r_", ""))
    weight = context.user_data.get("pending_weight")

    if weight is None:
        await query.message.delete()
        await process_next_exercise(query.message, context, user_id)
        return WORKOUT_EXERCISE_CONFIRM

    workout_data = context.user_data.get("current_workout", {})
    idx = workout_data.get("current_index", 0)
    ex_data = workout_data.get("exercises", [{}])[idx] if workout_data else {}

    log = WorkoutLog(
        user_id=user_id,
        exercise_name=ex_data["name"],
        sets=1,
        weight=weight,
        reps=reps,
    )
    async with AsyncSessionLocal() as session:
        session.add(log)
        await session.commit()

    logged_sets = workout_data["logged_sets"].get(idx, 0)
    workout_data["logged_sets"][idx] = logged_sets + 1
    context.user_data.pop("pending_weight", None)
    context.user_data.pop("pending_reps", None)

    await query.message.delete()
    await process_next_exercise(query.message, context, user_id)
    return WORKOUT_EXERCISE_CONFIRM


async def log_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual text input for weight/reps."""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if context.user_data.get("waiting_for_weight"):
        try:
            weight = float(text)
            context.user_data["pending_weight"] = weight
            context.user_data["waiting_for_weight"] = False
            await update.message.reply_text(
                f"Weight: {weight}kg\nSelect reps for this set:",
                reply_markup=REPS_KEYBOARD,
            )
            return WORKOUT_EXERCISE_INPUT
        except ValueError:
            await update.message.reply_text("Invalid weight. Enter a number:")
            return WORKOUT_EXERCISE_INPUT

    try:
        weight_str, reps_str = text.split()
        weight = float(weight_str)
        reps = int(reps_str)
    except ValueError:
        await update.message.reply_text("Invalid format. Try again (e.g., '55 8'):")
        return WORKOUT_EXERCISE_INPUT

    workout_data = context.user_data["current_workout"]
    idx = workout_data["current_index"]
    ex_data = workout_data["exercises"][idx]

    log = WorkoutLog(
        user_id=user_id, exercise_name=ex_data["name"], sets=1, weight=weight, reps=reps
    )
    async with AsyncSessionLocal() as session:
        session.add(log)
        await session.commit()

    logged_sets = workout_data["logged_sets"].get(idx, 0)
    workout_data["logged_sets"][idx] = logged_sets + 1

    await update.message.delete()
    await process_next_exercise(update.message, context, user_id)
    return WORKOUT_EXERCISE_CONFIRM


async def rest_timer_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        job.chat_id, text="Rest time over! 🔔 Get back to work!"
    )


async def log_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    try:
        text = update.message.text
        weight_str, reps_str = text.split()
        weight = float(weight_str)
        reps = int(reps_str)
    except ValueError:
        await update.message.reply_text("Invalid format. Try again (e.g., '55 8'):")
        return WORKOUT_EXERCISE_INPUT

    workout_data = context.user_data["current_workout"]
    idx = workout_data["current_index"]
    ex_data = workout_data["exercises"][idx]

    log = WorkoutLog(
        user_id=user_id, exercise_name=ex_data["name"], sets=1, weight=weight, reps=reps
    )
    async with AsyncSessionLocal() as session:
        session.add(log)
        await session.commit()

    logged_sets = workout_data["logged_sets"].get(idx, 0)
    workout_data["logged_sets"][idx] = logged_sets + 1

    await update.message.delete()
    await process_next_exercise(update.message, context, user_id)
    return WORKOUT_EXERCISE_CONFIRM


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
        if date_key not in workouts_by_date:
            workouts_by_date[date_key] = []
        workouts_by_date[date_key].append(log)

    keyboard = []
    for date in sorted(workouts_by_date.keys(), reverse=True):
        log_count = len(workouts_by_date[date])
        date_str = date.strftime("%b %d, %Y")
        callback_data = f"hist_{date.isoformat()}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📅 {date_str} ({log_count} exercises)",
                    callback_data=callback_data,
                )
            ]
        )

    text = "🏋️ Your workouts from the last 2 weeks:"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


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
        if date_key not in workouts_by_date:
            workouts_by_date[date_key] = []
        workouts_by_date[date_key].append(log)

    keyboard = []
    for date in sorted(workouts_by_date.keys(), reverse=True):
        log_count = len(workouts_by_date[date])
        date_str = date.strftime("%b %d, %Y")
        callback_data = f"hist_{date.isoformat()}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📅 {date_str} ({log_count} exercises)",
                    callback_data=callback_data,
                )
            ]
        )

    await update.message.reply_text(
        "🏋️ Your workouts from the last 2 weeks:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def history_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for viewing workout details."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if not data.startswith("hist_"):
        return

    date_str = data.replace("hist_", "")
    date = datetime.datetime.fromisoformat(date_str).date()
    user_id = update.effective_user.id

    next_day = date + datetime.timedelta(days=1)

    async with AsyncSessionLocal() as session:
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

    log_text = f"💪 Workout on {date.strftime('%B %d, %Y')}:\n\n"
    exercise_summary = {}
    for log in logs:
        key = f"{log.exercise_name}"
        if key not in exercise_summary:
            exercise_summary[key] = {"sets": 0, "weight": log.weight, "reps": log.reps}
        exercise_summary[key]["sets"] += 1

    for ex_name, ex_data in exercise_summary.items():
        log_text += f"• {ex_name}: {ex_data['sets']} set(s) @ {ex_data['weight']}kg x {ex_data['reps']}\n"

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
        if date_key not in workouts_by_date:
            workouts_by_date[date_key] = []
        workouts_by_date[date_key].append(log)

    keyboard = []
    for date in sorted(workouts_by_date.keys(), reverse=True):
        log_count = len(workouts_by_date[date])
        date_str = date.strftime("%b %d, %Y")
        callback_data = f"hist_{date.isoformat()}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📅 {date_str} ({log_count} exercises)",
                    callback_data=callback_data,
                )
            ]
        )

    await query.edit_message_text(
        "🏋️ Your workouts from the last 2 weeks:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
