"""Handlers for live workout logging sessions."""

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from database import AsyncSessionLocal, Template, WorkoutLog
import handlers.common as common
from handlers.common import (
    logger,
    WORKOUT_TEMPLATE_SELECT,
    WORKOUT_EXERCISE_SELECT,
    WORKOUT_EXERCISE_CONFIRM,
    WORKOUT_EXERCISE_INPUT,
    EDIT_TEMPLATE_EXERCISE,
    WEIGHT_KEYBOARD,
    REPS_KEYBOARD,
)
from handlers.template import (
    show_template_exercise_sets,
    handle_template_set_finish,
)


async def end_workout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle end_workout callback from any state."""
    query = update.callback_query
    await query.answer()
    workout_data = context.user_data.get("current_workout", {})
    template_name = workout_data.get("template_name", "")
    logged_sets = workout_data.get("logged_sets", {})
    user_id = update.effective_user.id

    for exercise_idx, sets in logged_sets.items():
        ex_data = workout_data["exercises"][exercise_idx]
        for log_data in sets:
            if log_data.get("weight") is None or log_data.get("reps") is None:
                continue
            log = WorkoutLog(
                user_id=user_id,
                template_name=template_name,
                exercise_name=ex_data["name"],
                sets=1,
                weight=log_data["weight"],
                reps=log_data["reps"],
            )
            async with AsyncSessionLocal() as session:
                session.add(log)
                await session.commit()

    context.user_data.pop("current_workout", None)
    context.user_data.pop("selected_exercise", None)
    context.user_data.pop("exercise_history", None)
    context.user_data.pop("waiting_for_add_exercise", None)
    context.user_data.pop("rest_job", None)
    await query.edit_message_text("Workout ended. Great effort! 💪\n")
    await asyncio.sleep(1)
    await context.bot.delete_message(
        chat_id=query.message.chat_id, message_id=query.message.message_id
    )
    return ConversationHandler.END


async def start_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"start_workout called by user {user_id}")

    if context.user_data.get("current_workout"):
        logger.info(f"Clearing stale workout data for user {user_id}")
        context.user_data.pop("current_workout", None)
        context.user_data.pop("selected_exercise", None)
        context.user_data.pop("exercise_history", None)
        context.user_data.pop("waiting_for_add_exercise", None)

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
        "template_name": template.name,
        "exercises": [
            {
                "name": ex.exercise_name,
                "default_sets": ex.default_sets,
                "default_weight": ex.default_weight,
                "default_reps": ex.default_reps,
                "sets_config": ex.get_sets_config()
                if hasattr(ex, "get_sets_config")
                else None,
            }
            for ex in exercises
        ],
        "current_index": 0,
        "logged_sets": {},  # {exercise_idx: [{weight, reps, timestamp}]}
    }

    # Show all exercises for selection
    keyboard = []
    for idx, ex in enumerate(context.user_data["current_workout"]["exercises"]):
        sets_config = ex.get("sets_config")
        if sets_config:
            sets_text = ", ".join([f"{s['weight']}x{s['reps']}" for s in sets_config])
            volume = sum([s["weight"] * s["reps"] for s in sets_config])
        else:
            sets_text = (
                f"{ex['default_sets']}x{ex['default_weight']}kgx{ex['default_reps']}"
            )
            volume = ex["default_sets"] * ex["default_weight"] * ex["default_reps"]
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{ex['name']} ({sets_text}) - {volume}kg vol",
                    callback_data=f"ex_{idx}",
                ),
            ]
        )
    keyboard.append(
        [InlineKeyboardButton("🛑 End Workout", callback_data="end_workout")]
    )

    await query.edit_message_text(
        f"Template: {template.name}\n\nSelect an exercise to start:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WORKOUT_EXERCISE_SELECT


async def select_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    exercise_idx = int(query.data.split("_")[1])
    context.user_data["current_workout"]["current_index"] = exercise_idx

    await process_next_exercise(query.message, context, query.from_user.id)
    return WORKOUT_EXERCISE_CONFIRM


def build_set_keyboard(exercise_idx, ex_data, logged_sets, context, is_completed=False):
    """Build keyboard with individual set buttons."""
    rest_seconds = context.user_data.get("default_rest_seconds", 300)
    rest_seconds = 300 if rest_seconds is None else rest_seconds
    minutes = rest_seconds // 60
    seconds = rest_seconds % 60
    if seconds > 0:
        rest_text = f"{minutes}m{seconds}s"
    else:
        rest_text = f"{minutes}m"

    keyboard = []
    total_sets = ex_data["default_sets"]
    sets_config = ex_data.get("sets_config")

    for set_num in range(1, total_sets + 1):
        if sets_config and set_num <= len(sets_config):
            default_weight = sets_config[set_num - 1]["weight"]
            default_reps = sets_config[set_num - 1]["reps"]
        else:
            default_weight = ex_data["default_weight"]
            default_reps = ex_data["default_reps"]

        if set_num <= len(logged_sets):
            logged = logged_sets[set_num - 1]
            if logged.get("weight") is not None and logged.get("reps") is not None:
                button_text = (
                    f"Set {set_num}: {logged['weight']}kg x {logged['reps']} ✅"
                )
                callback_data = f"edit_set_{exercise_idx}_{set_num}"
            else:
                button_text = f"Set {set_num}: {default_weight}kg x {default_reps}"
                callback_data = f"log_set_{exercise_idx}_{set_num}"
        else:
            button_text = f"Set {set_num}: {default_weight}kg x {default_reps}"
            callback_data = f"log_set_{exercise_idx}_{set_num}"
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=callback_data)]
        )

    if logged_sets:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "✅ Complete Exercise", callback_data=f"complete_{exercise_idx}"
                )
            ]
        )

    keyboard.extend(
        [
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_exercise")],
            [InlineKeyboardButton(f"⏰ Rest {rest_text}", callback_data="rest")],
            [InlineKeyboardButton("Skip Exercise ➡️", callback_data="skip")],
        ]
    )

    return InlineKeyboardMarkup(keyboard)


async def process_next_exercise(message, context, user_id):
    workout_data = context.user_data["current_workout"]
    idx = workout_data["current_index"]

    logger.info(f"process_next_exercise: index={idx}/{len(workout_data['exercises'])}")

    if idx >= len(workout_data["exercises"]):
        context.user_data.clear()
        await message.reply_text("Workout complete! Great job! 🎉")
        return ConversationHandler.END

    ex_data = workout_data["exercises"][idx]
    logged_sets = workout_data["logged_sets"].get(idx, [])

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

    completed_count = len(logged_sets)
    is_completed = completed_count >= ex_data["default_sets"]

    text = (
        f"**Exercise {idx + 1}/{len(workout_data['exercises'])}: {ex_data['name']}**\n"
        f"Progress: {completed_count}/{ex_data['default_sets']} sets completed\n"
        f"Previous: {prev_log_text}"
    )

    keyboard = build_set_keyboard(idx, ex_data, logged_sets, context, is_completed)

    logger.info(f"Sending exercise keyboard for {ex_data['name']}")

    if hasattr(message, "edit_text"):
        try:
            await message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        except Exception:
            pass
    else:
        await message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    return WORKOUT_EXERCISE_CONFIRM


async def handle_exercise_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    logger.info(f"handle_exercise_action: data={data}")

    if data == "rest":
        rest_seconds = context.user_data.get("default_rest_seconds", 300)
        rest_seconds = 300 if rest_seconds is None else rest_seconds
        minutes = rest_seconds // 60
        seconds = rest_seconds % 60
        if seconds > 0:
            rest_text = f"{minutes}m{seconds}s"
        else:
            rest_text = f"{minutes}m"
        rest_message = await query.message.reply_text(
            f"Rest timer started: {rest_text}. ⏳\n\n"
            "Click 'Skip Rest' to cancel and continue.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Skip Rest ⏭️", callback_data="cancel_rest")]]
            ),
        )
        job = context.job_queue.run_once(
            rest_timer_callback,
            rest_seconds,
            chat_id=query.message.chat_id,
            user_id=update.effective_user.id,
        )
        context.user_data["rest_job"] = job
        context.user_data["rest_message_id"] = rest_message.message_id
        return WORKOUT_EXERCISE_CONFIRM

    if data == "cancel_rest":
        user_data = context.user_data
        if user_data is None:
            # Manually fetch the user_data from the application's storage
            user_id = update.effective_user.id
            user_data = context.application.user_data[user_id]
        job = user_data.pop("rest_job", None)
        if job:
            job.schedule_removal()
        rest_message_id = user_data.pop("rest_message_id", None)
        try:
            if rest_message_id:
                await context.bot.delete_message(query.message.chat_id, rest_message_id)
            else:
                await query.message.edit_text("Rest timer canceled. Let's go! 💪")
        except Exception:
            pass
        return WORKOUT_EXERCISE_CONFIRM

    if data == "skip":
        user_data = context.user_data
        if user_data is None:
            # Manually fetch the user_data from the application's storage
            user_id = update.effective_user.id
            user_data = context.application.user_data[user_id]
        user_data.pop("rest_job", None)
        logger.info(f"Skip handler triggered for user {user_id}")
        workout_data = user_data.get("current_workout")
        if (
            not workout_data
            or "exercises" not in workout_data
            or not workout_data["exercises"]
        ):
            logger.info(f"Skip aborted: no workout data")
            return WORKOUT_EXERCISE_CONFIRM
        logger.info(f"Skipping exercise at index {workout_data['current_index']}")
        current_idx = workout_data["current_index"]
        workout_data["exercises"].pop(current_idx)
        if "logged_sets" in workout_data:
            workout_data["logged_sets"].pop(current_idx, None)
            new_logged_sets = {}
            for old_idx, sets in workout_data["logged_sets"].items():
                if old_idx < current_idx:
                    new_logged_sets[old_idx] = sets
                elif old_idx > current_idx:
                    new_logged_sets[old_idx - 1] = sets
            workout_data["logged_sets"] = new_logged_sets
        num_exercises = len(workout_data["exercises"])
        if num_exercises == 0:
            context.user_data.clear()
            await query.message.edit_text("Workout complete! Great job! 🎉")
            return ConversationHandler.END
        if current_idx >= num_exercises:
            workout_data["current_index"] = num_exercises - 1
        else:
            workout_data["current_index"] = max(0, current_idx - 1)
        keyboard = []
        for idx, ex in enumerate(workout_data["exercises"]):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{idx + 1}. {ex['name']} ({ex['default_sets']} sets x {ex['default_weight']}kg x {ex['default_reps']} reps)",
                        callback_data=f"ex_{idx}",
                    ),
                    InlineKeyboardButton("❌", callback_data=f"remove_exercise_{idx}"),
                ]
            )
        keyboard.append(
            [InlineKeyboardButton("🛑 End Workout", callback_data="end_workout")]
        )
        keyboard.append(
            [InlineKeyboardButton("➕ Add Exercise", callback_data="add_exercise")]
        )
        await query.message.edit_text(
            "Select an exercise to continue:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return WORKOUT_EXERCISE_SELECT

    if data.startswith("log_set_"):
        context.user_data.pop("rest_job", None)
        parts = data.split("_")
        exercise_idx = int(parts[2])
        set_num = int(parts[3])
        context.user_data["pending_exercise_idx"] = exercise_idx
        context.user_data["pending_set_num"] = set_num
        context.user_data["pending_weight"] = None
        context.user_data["pending_reps"] = None

        workout_data = context.user_data.get("current_workout", {})
        ex_data = workout_data["exercises"][exercise_idx]
        default_weight = ex_data["default_weight"]
        default_reps = ex_data["default_reps"]

        context.user_data["default_weight"] = default_weight
        context.user_data["default_reps"] = default_reps

        default_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"✅ {default_weight}kg x {default_reps} reps",
                        callback_data="use_defaults",
                    )
                ],
                [InlineKeyboardButton("Edit Weight", callback_data="edit_weight")],
                [InlineKeyboardButton("Edit Reps", callback_data="edit_reps")],
            ]
        )

        await query.message.edit_text(
            f"Set {set_num}: Use defaults or edit:",
            reply_markup=default_keyboard,
        )
        return WORKOUT_EXERCISE_INPUT

    if data == "use_defaults":
        if context.user_data.get("is_template_edit"):
            exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
            set_num = context.user_data.get("pending_template_set_num", 1)
            weight = context.user_data.get("pending_weight", 0)
            reps = context.user_data.get("pending_reps", 0)
            return await handle_template_set_finish(update, context, weight, reps)

        exercise_idx = context.user_data.get("pending_exercise_idx", 0)
        set_num = context.user_data.get("pending_set_num", 1)
        default_weight = context.user_data.get("default_weight", 0)
        default_reps = context.user_data.get("default_reps", 0)

        workout_data = context.user_data.get("current_workout", {})
        if "logged_sets" not in workout_data:
            workout_data["logged_sets"] = {}
        if exercise_idx not in workout_data["logged_sets"]:
            workout_data["logged_sets"][exercise_idx] = []

        logged_sets = workout_data["logged_sets"][exercise_idx]
        while len(logged_sets) < set_num:
            logged_sets.append({"weight": None, "reps": None})

        logged_sets[set_num - 1] = {"weight": default_weight, "reps": default_reps}

        ex_data = workout_data["exercises"][exercise_idx]
        completed_count = len(logged_sets)

        context.user_data.pop("pending_weight", None)
        context.user_data.pop("pending_reps", None)
        context.user_data.pop("pending_exercise_idx", None)
        context.user_data.pop("pending_set_num", None)
        context.user_data.pop("default_weight", None)
        context.user_data.pop("default_reps", None)

        await query.message.edit_text(
            f"Set {set_num} logged: {default_weight}kg x {default_reps} reps\n\n"
            f"Progress: {completed_count}/{ex_data['default_sets']} sets completed",
            parse_mode="Markdown",
            reply_markup=build_set_keyboard(
                exercise_idx,
                ex_data,
                logged_sets,
                context,
                completed_count >= ex_data["default_sets"],
            ),
        )
        return WORKOUT_EXERCISE_CONFIRM

    if data == "edit_weight":
        if context.user_data.get("is_template_edit"):
            exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
            ex_data = context.user_data["editing_exercises"][exercise_idx]
            default_weight = ex_data.get("weight", 0)
            set_num = context.user_data.get("pending_template_set_num", 1)
        else:
            exercise_idx = context.user_data.get("pending_exercise_idx", 0)
            ex_data = context.user_data.get("current_workout", {}).get(
                "exercises", [{}]
            )[exercise_idx]
            default_weight = ex_data.get("default_weight", 0)
            set_num = context.user_data.get("pending_set_num", 1)

        await query.message.edit_text(
            f"Set {set_num}: Select weight (default: {default_weight}kg):",
            reply_markup=WEIGHT_KEYBOARD,
        )
        return (
            EDIT_TEMPLATE_EXERCISE
            if context.user_data.get("is_template_edit")
            else WORKOUT_EXERCISE_INPUT
        )

    if data == "edit_reps":
        if context.user_data.get("is_template_edit"):
            exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
            ex_data = context.user_data["editing_exercises"][exercise_idx]
            default_reps = ex_data.get("reps", 0)
            default_weight = ex_data.get("weight", 0)
        else:
            exercise_idx = context.user_data.get("pending_exercise_idx", 0)
            ex_data = context.user_data.get("current_workout", {}).get(
                "exercises", [{}]
            )[exercise_idx]
            default_reps = ex_data.get("default_reps", 0)
            default_weight = ex_data.get("default_weight", 0)

        pending_weight = context.user_data.get("pending_weight")

        if pending_weight is None:
            context.user_data["pending_weight"] = default_weight
            pending_weight = default_weight

        await query.message.edit_text(
            f"Weight: {pending_weight}kg\nSelect reps (default: {default_reps}):",
            reply_markup=REPS_KEYBOARD,
        )
        return (
            EDIT_TEMPLATE_EXERCISE
            if context.user_data.get("is_template_edit")
            else WORKOUT_EXERCISE_INPUT
        )

    if data.startswith("edit_set_"):
        context.user_data.pop("rest_job", None)
        parts = data.split("_")
        exercise_idx = int(parts[2])
        set_num = int(parts[3])
        context.user_data["pending_exercise_idx"] = exercise_idx
        context.user_data["pending_set_num"] = set_num
        workout_data = context.user_data["current_workout"]
        ex_data = workout_data["exercises"][exercise_idx]
        logged_sets = workout_data["logged_sets"].get(exercise_idx, [])

        context.user_data["default_weight"] = ex_data["default_weight"]
        context.user_data["default_reps"] = ex_data["default_reps"]

        if set_num <= len(logged_sets):
            existing = logged_sets[set_num - 1]
            context.user_data["pending_weight"] = existing["weight"]
            context.user_data["pending_reps"] = existing["reps"]
            context.user_data["editing_existing"] = True
            edit_keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"✅ {existing['weight']}kg x {existing['reps']} reps",
                            callback_data="use_existing_values",
                        )
                    ],
                    [InlineKeyboardButton("Edit Weight", callback_data="edit_weight")],
                    [InlineKeyboardButton("Edit Reps", callback_data="edit_reps")],
                ]
            )
            await query.message.edit_text(
                f"Set {set_num}: Use current values or edit:",
                reply_markup=edit_keyboard,
            )
        else:
            context.user_data["pending_weight"] = None
            context.user_data["pending_reps"] = None
            context.user_data["editing_existing"] = False
            default_keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"✅ {ex_data['default_weight']}kg x {ex_data['default_reps']} reps",
                            callback_data="use_defaults",
                        )
                    ],
                    [InlineKeyboardButton("Edit Weight", callback_data="edit_weight")],
                    [InlineKeyboardButton("Edit Reps", callback_data="edit_reps")],
                ]
            )
            await query.message.edit_text(
                f"Set {set_num}: Use defaults or edit:",
                reply_markup=default_keyboard,
            )
        return WORKOUT_EXERCISE_INPUT

    if data == "use_existing_values":
        exercise_idx = context.user_data.get("pending_exercise_idx", 0)
        set_num = context.user_data.get("pending_set_num", 1)
        existing_weight = context.user_data.get("pending_weight", 0)
        existing_reps = context.user_data.get("pending_reps", 0)

        workout_data = context.user_data.get("current_workout", {})
        logged_sets = workout_data["logged_sets"].get(exercise_idx, [])
        logged_sets[set_num - 1] = {"weight": existing_weight, "reps": existing_reps}

        ex_data = workout_data["exercises"][exercise_idx]
        completed_count = len(logged_sets)

        context.user_data.pop("pending_weight", None)
        context.user_data.pop("pending_reps", None)
        context.user_data.pop("pending_exercise_idx", None)
        context.user_data.pop("pending_set_num", None)
        context.user_data.pop("default_weight", None)
        context.user_data.pop("default_reps", None)
        context.user_data.pop("editing_existing", None)

        await query.message.edit_text(
            f"Set {set_num} updated: {existing_weight}kg x {existing_reps} reps\n\n"
            f"Progress: {completed_count}/{ex_data['default_sets']} sets completed",
            parse_mode="Markdown",
            reply_markup=build_set_keyboard(
                exercise_idx,
                ex_data,
                logged_sets,
                context,
                completed_count >= ex_data["default_sets"],
            ),
        )
        return WORKOUT_EXERCISE_CONFIRM

    if data.startswith("complete_"):
        context.user_data.pop("rest_job", None)
        exercise_idx = int(data.split("_")[1])
        workout_data = context.user_data["current_workout"]
        template_name = workout_data.get("template_name", "")
        ex_data = workout_data["exercises"][exercise_idx]
        logged_sets = workout_data["logged_sets"].get(exercise_idx, [])

        for log_data in logged_sets:
            if log_data.get("weight") is None or log_data.get("reps") is None:
                continue
            log = WorkoutLog(
                user_id=user_id,
                template_name=template_name,
                exercise_name=ex_data["name"],
                sets=1,
                weight=log_data["weight"],
                reps=log_data["reps"],
            )
            async with AsyncSessionLocal() as session:
                session.add(log)
                await session.commit()

        workout_data["exercises"].pop(exercise_idx)
        if "logged_sets" in workout_data:
            workout_data["logged_sets"].pop(exercise_idx, None)
            new_logged_sets = {}
            for old_idx, sets in workout_data["logged_sets"].items():
                if old_idx < exercise_idx:
                    new_logged_sets[old_idx] = sets
                elif old_idx > exercise_idx:
                    new_logged_sets[old_idx - 1] = sets
            workout_data["logged_sets"] = new_logged_sets

        num_exercises = len(workout_data["exercises"])
        if num_exercises == 0:
            context.user_data.clear()
            await query.message.edit_text("Workout complete! Great job! 🎉")
            return ConversationHandler.END

        if exercise_idx >= num_exercises:
            workout_data["current_index"] = num_exercises - 1
        else:
            workout_data["current_index"] = exercise_idx

        return await process_next_exercise(query.message, context, user_id)

    if data == "back_to_exercise":
        workout_data = context.user_data.get("current_workout")
        if workout_data:
            keyboard = []
            for idx, ex in enumerate(workout_data["exercises"]):
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"{idx + 1}. {ex['name']} ({ex['default_sets']} sets x {ex['default_weight']}kg x {ex['default_reps']} reps)",
                            callback_data=f"ex_{idx}",
                        ),
                        InlineKeyboardButton(
                            "❌", callback_data=f"remove_exercise_{idx}"
                        ),
                    ]
                )
            keyboard.append(
                [InlineKeyboardButton("🛑 End Workout", callback_data="end_workout")]
            )
            keyboard.append(
                [InlineKeyboardButton("➕ Add Exercise", callback_data="add_exercise")]
            )
            await query.message.edit_text(
                "Select an exercise to continue:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return WORKOUT_EXERCISE_SELECT
        return WORKOUT_EXERCISE_CONFIRM

    if data == "end_workout":
        context.user_data.pop("rest_job", None)
        context.user_data.pop("current_workout", None)
        context.user_data.pop("selected_exercise", None)
        context.user_data.pop("exercise_history", None)
        context.user_data.pop("waiting_for_add_exercise", None)
        await query.message.edit_text(
            "Workout ended. Great effort! 💪\n/start_workout to begin a new workout."
        )
        return ConversationHandler.END

    if data == "add_exercise":
        context.user_data["waiting_for_add_exercise"] = True
        await query.message.edit_text(
            "Enter exercise name to add (format: 'Name'):\nExample: 'Pushups 3 0 15'"
        )
        return WORKOUT_EXERCISE_INPUT

    if data.startswith("remove_exercise_"):
        exercise_idx = int(data.split("_")[2])
        workout_data = context.user_data["current_workout"]
        workout_data["exercises"].pop(exercise_idx)
        if "logged_sets" in workout_data:
            workout_data["logged_sets"].pop(exercise_idx, None)
            new_logged_sets = {}
            for old_idx, sets in workout_data["logged_sets"].items():
                if old_idx < exercise_idx:
                    new_logged_sets[old_idx] = sets
                elif old_idx > exercise_idx:
                    new_logged_sets[old_idx - 1] = sets
            workout_data["logged_sets"] = new_logged_sets
        num_exercises = len(workout_data["exercises"])
        if num_exercises == 0:
            await query.answer()
            context.user_data.clear()
            await query.message.edit_text("Workout complete! Great job! 🎉")
            return ConversationHandler.END
        if workout_data["current_index"] >= num_exercises:
            workout_data["current_index"] = num_exercises - 1
        keyboard = []
        for idx, ex in enumerate(workout_data["exercises"]):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{idx + 1}. {ex['name']} ({ex['default_sets']} sets x {ex['default_weight']}kg x {ex['default_reps']} reps)",
                        callback_data=f"ex_{idx}",
                    ),
                    InlineKeyboardButton("❌", callback_data=f"remove_exercise_{idx}"),
                ]
            )
        keyboard.append(
            [InlineKeyboardButton("🛑 End Workout", callback_data="end_workout")]
        )
        keyboard.append(
            [InlineKeyboardButton("➕ Add Exercise", callback_data="add_exercise")]
        )
        await query.message.edit_text(
            "Select an exercise to continue:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return WORKOUT_EXERCISE_SELECT

    if data == "etuse_current":
        weight = context.user_data.get("pending_weight")
        reps = context.user_data.get("pending_reps")
        return await handle_template_set_finish(update, context, weight, reps)

    if data.startswith("w_"):
        return await handle_weight_select(update, context, user_id)

    if data.startswith("r_"):
        return await handle_reps_select(update, context, user_id)


async def handle_weight_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id
):
    query = update.callback_query
    data = query.data

    if data == "w_back":
        if context.user_data.get("is_template_edit"):
            return await show_template_exercise_sets(update, context, query.message)
        else:
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

    # Show template default for reps
    if context.user_data.get("is_template_edit"):
        exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
        ex_data = context.user_data["editing_exercises"][exercise_idx]
        default_reps = ex_data.get("reps", 0)
    else:
        exercise_idx = context.user_data.get("pending_exercise_idx", 0)
        ex_data = context.user_data.get("current_workout", {}).get("exercises", [{}])[
            exercise_idx
        ]
        default_reps = ex_data.get("default_reps", 0)

    await query.message.edit_text(
        f"Weight: {weight}kg\nSelect reps (default: {default_reps}):",
        reply_markup=REPS_KEYBOARD,
    )
    if context.user_data.get("is_template_edit"):
        return EDIT_TEMPLATE_EXERCISE
    return WORKOUT_EXERCISE_INPUT


async def handle_reps_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id
):
    query = update.callback_query
    data = query.data

    if data == "r_custom":
        if context.user_data.get("is_template_edit"):
            exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
            ex_data = context.user_data["editing_exercises"][exercise_idx]
            default_reps = ex_data.get("reps", 0)
        else:
            exercise_idx = context.user_data.get("pending_exercise_idx", 0)
            ex_data = context.user_data.get("current_workout", {}).get(
                "exercises", [{}]
            )[exercise_idx]
            default_reps = ex_data.get("default_reps", 0)

        await query.message.edit_text(
            f"Enter custom reps (default: {default_reps}):",
        )
        context.user_data["waiting_for_reps"] = True
        return WORKOUT_EXERCISE_INPUT

    if data == "r_back":
        if context.user_data.get("is_template_edit"):
            exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
            ex_data = context.user_data["editing_exercises"][exercise_idx]
            default_weight = ex_data.get("weight", 0)
            set_num = context.user_data.get("pending_template_set_num", 1)
        else:
            exercise_idx = context.user_data.get("pending_exercise_idx", 0)
            ex_data = context.user_data.get("current_workout", {}).get(
                "exercises", [{}]
            )[exercise_idx]
            default_weight = ex_data.get("default_weight", 0)
            set_num = context.user_data.get("pending_set_num", 1)

        await query.message.edit_text(
            f"Set {set_num}: Select weight for this set (default: {default_weight}kg):",
            reply_markup=WEIGHT_KEYBOARD,
        )
        return WORKOUT_EXERCISE_INPUT

    reps = int(data.replace("r_", ""))
    weight = context.user_data.get("pending_weight")

    if weight is None:
        if context.user_data.get("is_template_edit"):
            return await show_template_exercise_sets(update, context, query.message)
        else:
            await process_next_exercise(query.message, context, user_id)
            return WORKOUT_EXERCISE_CONFIRM

    if context.user_data.get("is_template_edit"):
        return await handle_template_set_finish(update, context, weight, reps)

    exercise_idx = context.user_data.get("pending_exercise_idx", 0)
    set_num = context.user_data.get("pending_set_num", 1)

    workout_data = context.user_data.get("current_workout", {})
    if "logged_sets" not in workout_data:
        workout_data["logged_sets"] = {}

    if exercise_idx not in workout_data["logged_sets"]:
        workout_data["logged_sets"][exercise_idx] = []

    logged_sets = workout_data["logged_sets"][exercise_idx]

    while len(logged_sets) < set_num:
        logged_sets.append({"weight": None, "reps": None})

    logged_sets[set_num - 1] = {"weight": weight, "reps": reps}

    context.user_data.pop("pending_weight", None)
    context.user_data.pop("pending_reps", None)
    context.user_data.pop("pending_exercise_idx", None)
    context.user_data.pop("pending_set_num", None)
    context.user_data.pop("default_weight", None)
    context.user_data.pop("default_reps", None)
    context.user_data.pop("editing_existing", None)

    ex_data = workout_data["exercises"][exercise_idx]
    completed_count = len(logged_sets)

    await query.message.edit_text(
        f"Set {set_num} logged: {weight}kg x {reps} reps\n\n"
        f"Progress: {completed_count}/{ex_data['default_sets']} sets completed",
        parse_mode="Markdown",
        reply_markup=build_set_keyboard(
            exercise_idx,
            ex_data,
            logged_sets,
            context,
            completed_count >= ex_data["default_sets"],
        ),
    )
    return WORKOUT_EXERCISE_CONFIRM


async def log_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual text input for weight/reps."""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if context.user_data.get("waiting_for_add_exercise"):
        text = update.message.text.strip()
        parts = text.split()

        if len(parts) < 3:
            await update.message.reply_text(
                "Invalid format. Use: 'Name 3 60x5 65x4'\nExample: 'Bench Press 3 60x5 65x4'"
            )
            return WORKOUT_EXERCISE_INPUT

        try:
            num_sets = int(parts[0])
            if num_sets <= 0:
                raise ValueError("Sets must be positive")
        except ValueError:
            await update.message.reply_text(
                "First value must be number of sets (e.g., '3')."
            )
            return WORKOUT_EXERCISE_INPUT

        weight_reps_parts = parts[-num_sets:] if len(parts) >= num_sets + 1 else []

        if len(weight_reps_parts) < num_sets:
            await update.message.reply_text(
                f"Please provide {num_sets} weight x reps values (e.g., '60x5')."
            )
            return WORKOUT_EXERCISE_INPUT

        name_parts = parts[1:-num_sets] if len(parts) > num_sets + 1 else []
        name = " ".join(name_parts) if name_parts else parts[1]
        name = name.strip()

        sets_config = []
        for pr in weight_reps_parts:
            try:
                wr = pr.split("x")
                if len(wr) != 2:
                    raise ValueError
                weight = float(wr[0])
                reps = int(wr[1])
                if reps <= 0 or weight < 0:
                    raise ValueError
                sets_config.append({"weight": weight, "reps": reps})
            except (ValueError, IndexError):
                await update.message.reply_text(
                    f"Invalid format '{pr}'. Use: '60x5' for 60kg x 5 reps"
                )
                return WORKOUT_EXERCISE_INPUT

        workout_data = context.user_data.get("current_workout")
        if workout_data and "exercises" in workout_data:
            workout_data["exercises"].append(
                {
                    "name": name,
                    "default_sets": num_sets,
                    "default_weight": sets_config[0]["weight"],
                    "default_reps": sets_config[0]["reps"],
                    "sets_config": sets_config,
                }
            )
            context.user_data.pop("waiting_for_add_exercise", None)
            exercises = workout_data["exercises"]
            keyboard = []
            for idx, ex in enumerate(exercises):
                sets_text = (
                    ", ".join(
                        [
                            f"{s['weight']}x{s['reps']}"
                            for s in ex.get("sets_config", [])
                        ]
                    )
                    if ex.get("sets_config")
                    else f"{ex['default_sets']}x{ex['default_weight']}kgx{ex['default_reps']}"
                )
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"{idx + 1}. {ex['name']} ({sets_text})",
                            callback_data=f"ex_{idx}",
                        )
                    ]
                )
            keyboard.append(
                [InlineKeyboardButton("🛑 End Workout", callback_data="end_workout")]
            )
            keyboard.append(
                [InlineKeyboardButton("➕ Add Exercise", callback_data="add_exercise")]
            )
            await update.message.reply_text(
                f"Exercise '{name}' added! Select an exercise to continue:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return WORKOUT_EXERCISE_SELECT
        await update.message.reply_text(
            "No active workout. Use /start_workout to begin."
        )
        return ConversationHandler.END

    if context.user_data.get("waiting_for_weight"):
        try:
            weight = float(text)
            context.user_data["pending_weight"] = weight
            context.user_data["waiting_for_weight"] = False

            # Show template default for reps
            if context.user_data.get("is_template_edit"):
                exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
                ex_data = context.user_data["editing_exercises"][exercise_idx]
                default_reps = ex_data.get("reps", 0)
            else:
                exercise_idx = context.user_data.get("pending_exercise_idx", 0)
                ex_data = context.user_data.get("current_workout", {}).get(
                    "exercises", [{}]
                )[exercise_idx]
                default_reps = ex_data.get("default_reps", 0)

            await update.message.reply_text(
                f"Weight: {weight}kg\nSelect reps (default: {default_reps}):",
                reply_markup=REPS_KEYBOARD,
            )
            if context.user_data.get("is_template_edit"):
                return EDIT_TEMPLATE_EXERCISE
            return WORKOUT_EXERCISE_INPUT
        except ValueError:
            await update.message.reply_text("Invalid weight. Enter a number:")
            return WORKOUT_EXERCISE_INPUT

    if context.user_data.get("waiting_for_custom_rest"):
        try:
            rest_seconds = int(text)
            if rest_seconds <= 0:
                raise ValueError
            context.user_data.pop("waiting_for_custom_rest", None)

            rest_message = await update.message.reply_text(
                f"Rest timer started: {rest_seconds} seconds. ⏳\n\n"
                "Click 'Skip Rest' to cancel and continue.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Skip Rest ⏭️", callback_data="cancel_rest")]]
                ),
            )
            job = context.job_queue.run_once(
                rest_timer_callback,
                rest_seconds,
                chat_id=update.message.chat_id,
                user_id=update.effective_user.id,
            )
            context.user_data["rest_job"] = job
            context.user_data["rest_message_id"] = rest_message.message_id
            return WORKOUT_EXERCISE_CONFIRM
        except ValueError:
            await update.message.reply_text(
                "Invalid duration. Enter seconds (e.g., 90):"
            )
            return WORKOUT_EXERCISE_INPUT

    if context.user_data.get("waiting_for_reps"):
        try:
            reps = int(text)
            context.user_data["pending_reps"] = reps
            context.user_data["waiting_for_reps"] = False

            # Log the set with custom reps
            weight = context.user_data.get("pending_weight")

            if context.user_data.get("is_template_edit"):
                return await handle_template_set_finish(update, context, weight, reps)

            exercise_idx = context.user_data.get("pending_exercise_idx", 0)
            set_num = context.user_data.get("pending_set_num", 1)

            if weight is None:
                await update.message.delete()
                await process_next_exercise(update.message, context, user_id)
                return WORKOUT_EXERCISE_CONFIRM

            workout_data = context.user_data.get("current_workout", {})
            if "logged_sets" not in workout_data:
                workout_data["logged_sets"] = {}
            if exercise_idx not in workout_data["logged_sets"]:
                workout_data["logged_sets"][exercise_idx] = []

            logged_sets = workout_data["logged_sets"][exercise_idx]
            while len(logged_sets) < set_num:
                logged_sets.append({"weight": None, "reps": None})

            logged_sets[set_num - 1] = {"weight": weight, "reps": reps}

            ex_data = workout_data["exercises"][exercise_idx]
            await update.message.edit_text(
                f"Set {set_num} logged: {weight}kg x {reps} reps\n\n"
                f"Progress: {len(logged_sets)}/{ex_data['default_sets']} sets completed",
                reply_markup=build_set_keyboard(
                    exercise_idx,
                    ex_data,
                    logged_sets,
                    context,
                    len(logged_sets) >= ex_data["default_sets"],
                ),
            )
            return WORKOUT_EXERCISE_CONFIRM
        except ValueError:
            await update.message.reply_text("Invalid reps. Enter a number:")
            return WORKOUT_EXERCISE_INPUT

    try:
        weight_str, reps_str = text.split()
        weight = float(weight_str)
        reps = int(reps_str)
    except ValueError:
        await update.message.reply_text("Invalid format. Try again (e.g., '55 8'):")
        return WORKOUT_EXERCISE_INPUT

    if context.user_data.get("is_template_edit"):
        return await handle_template_set_finish(update, context, weight, reps)

    exercise_idx = context.user_data.get("pending_exercise_idx", 0)
    set_num = context.user_data.get("pending_set_num", 1)

    workout_data = context.user_data.get("current_workout", {})
    if "logged_sets" not in workout_data:
        workout_data["logged_sets"] = {}

    if exercise_idx not in workout_data["logged_sets"]:
        workout_data["logged_sets"][exercise_idx] = []

    logged_sets = workout_data["logged_sets"][exercise_idx]

    while len(logged_sets) < set_num:
        logged_sets.append({"weight": None, "reps": None})

    logged_sets[set_num - 1] = {"weight": weight, "reps": reps}

    context.user_data.pop("pending_weight", None)
    context.user_data.pop("pending_reps", None)
    context.user_data.pop("pending_exercise_idx", None)
    context.user_data.pop("pending_set_num", None)

    await update.message.delete()
    await process_next_exercise(update.message, context, user_id)
    return WORKOUT_EXERCISE_CONFIRM


async def rest_timer_callback(context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    rest_message_id = user_data.pop("rest_message_id", None)
    job = context.job
    if rest_message_id:
        try:
            await context.bot.delete_message(job.chat_id, rest_message_id)
        except Exception:
            pass
    msg = await context.bot.send_message(
        chat_id=job.chat_id,
        text="⏰ **Rest is over!** Get back to work uwu! 💪",
        parse_mode="Markdown",
    )
    await asyncio.sleep(5)
    await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
