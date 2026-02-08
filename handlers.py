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
    WORKOUT_EXERCISE_SELECT,
    WORKOUT_EXERCISE_CONFIRM,
    WORKOUT_EXERCISE_INPUT,
    EXERCISE_SETS_INPUT,
    EDIT_TEMPLATE_SELECT,
    EDIT_TEMPLATE_EXERCISE,
    EDIT_TEMPLATE_NAME,
    EDIT_EXERCISE_NAME,
    EDIT_EXERCISE_DETAILS,
) = range(13)

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
            InlineKeyboardButton("Custom", callback_data="r_custom"),
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
        "/edit_template - Edit an existing template\n"
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


async def edit_template_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start editing a template - list all templates for user to select."""
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Template).where(Template.user_id == user_id)
        )
        templates = result.scalars().all()

    if not templates:
        await update.message.reply_text(
            "No templates found. Use /create_template to add one first!"
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(t.name, callback_data=f"etmpl_{t.id}")] for t in templates
    ]
    await update.message.reply_text(
        "Select a template to edit:", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EDIT_TEMPLATE_SELECT


async def select_template_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template selection for editing."""
    query = update.callback_query
    await query.answer()

    template_id = int(query.data.split("_")[1])

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Template)
            .where(Template.id == template_id)
            .options(selectinload(Template.exercises))
        )
        template = result.scalar_one()
        exercises = sorted(template.exercises, key=lambda x: x.order)

    context.user_data["editing_template_id"] = template_id
    context.user_data["editing_template_name"] = template.name
    context.user_data["editing_exercises"] = [
        {
            "id": ex.id,
            "name": ex.exercise_name,
            "sets": ex.default_sets,
            "weight": ex.default_weight,
            "reps": ex.default_reps,
        }
        for ex in exercises
    ]

    keyboard = []
    for idx, ex in enumerate(context.user_data["editing_exercises"]):
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"✏️ {ex['name']} ({ex['sets']}x{ex['weight']}kgx{ex['reps']})",
                    callback_data=f"etedit_{idx}",
                ),
                InlineKeyboardButton("❌", callback_data=f"etrm_{idx}"),
            ]
        )
    keyboard.append([InlineKeyboardButton("➕ Add Exercise", callback_data="etadd")])
    keyboard.append(
        [InlineKeyboardButton("📝 Rename Template", callback_data="etrname")]
    )
    keyboard.append([InlineKeyboardButton("💾 Save & Exit", callback_data="etsave")])

    await query.edit_message_text(
        f"Editing: {template.name}\n\nSelect an exercise to edit or add new ones:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_TEMPLATE_EXERCISE


async def handle_edit_exercise_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle exercise editing actions."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "etadd":
        await query.message.reply_text(
            "Enter new exercise name (format: 'Name'):\nExample: 'Pushups 3 0 15'"
        )
        return EDIT_EXERCISE_NAME

    if data == "etrname":
        await query.message.reply_text("Enter new template name:")
        return EDIT_TEMPLATE_NAME

    if data == "etsave":
        return await save_edited_template(update, context)

    if data.startswith("etedit_"):
        idx = int(data.split("_")[1])
        ex = context.user_data["editing_exercises"][idx]
        context.user_data["editing_exercise_idx"] = idx
        await query.message.reply_text(
            f"Editing: {ex['name']}\n"
            f"Current: {ex['sets']} sets x {ex['weight']}kg x {ex['reps']} reps ({ex['sets'] * ex['weight'] * ex['reps']}kg vol)\n\n"
            f"Enter new details (sets weight reps) or /skip to keep current:"
        )
        return EDIT_EXERCISE_DETAILS

    if data.startswith("etrm_"):
        idx = int(data.split("_")[1])
        removed = context.user_data["editing_exercises"].pop(idx)
        await query.message.reply_text(f"Removed {removed['name']} from template.")
        return await show_edited_template(update, context, query.message)

    return EDIT_TEMPLATE_EXERCISE


async def edit_exercise_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding new exercise name during template editing."""
    text = update.message.text.strip()
    context.user_data["new_exercise_name"] = text
    await update.message.reply_text(
        f"Enter details for {text} (sets weight reps):\nExample: '3 50 10'"
    )
    return EDIT_EXERCISE_DETAILS


async def edit_exercise_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle exercise details during template editing."""
    text = update.message.text.strip()

    if text.lower() == "/skip":
        await update.message.reply_text("Exercise details unchanged.")
        return await show_edited_template(update, context, update.message)

    parts = text.split()

    if len(parts) != 3:
        await update.message.reply_text(
            "Invalid format. Please enter 'Sets Weight Reps':"
        )
        return EDIT_EXERCISE_DETAILS

    try:
        sets = int(parts[0])
        weight = float(parts[1])
        reps = int(parts[2])
        if sets <= 0 or reps <= 0:
            raise ValueError("Values must be positive")
    except ValueError:
        await update.message.reply_text(
            "Invalid format. Please enter positive numbers:"
        )
        return EDIT_EXERCISE_DETAILS

    exercise_idx = context.user_data.get("editing_exercise_idx")
    if exercise_idx is not None:
        context.user_data["editing_exercises"][exercise_idx].update(
            {
                "name": context.user_data.get(
                    "new_exercise_name",
                    context.user_data["editing_exercises"][exercise_idx]["name"],
                ),
                "sets": sets,
                "weight": weight,
                "reps": reps,
            }
        )
        context.user_data.pop("editing_exercise_idx", None)
        await update.message.reply_text("Exercise updated!")
    else:
        context.user_data["editing_exercises"].append(
            {
                "name": context.user_data["new_exercise_name"],
                "sets": sets,
                "weight": weight,
                "reps": reps,
            }
        )
        context.user_data.pop("new_exercise_name", None)
        await update.message.reply_text("Exercise added!")

    return await show_edited_template(update, context, update.message)


async def edit_template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template renaming."""
    context.user_data["editing_template_name"] = update.message.text.strip()
    await update.message.reply_text("Template renamed!")
    return await show_edited_template(update, context, update.message)


async def show_edited_template(update, context, message):
    """Show the current state of the edited template."""
    keyboard = []
    for idx, ex in enumerate(context.user_data["editing_exercises"]):
        volume = ex["sets"] * ex["weight"] * ex["reps"]
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"✏️ {ex['name']} ({ex['sets']}x{ex['weight']}kgx{ex['reps']}) - {volume}kg vol",
                    callback_data=f"etedit_{idx}",
                ),
                InlineKeyboardButton("❌", callback_data=f"etrm_{idx}"),
            ]
        )
    keyboard.append([InlineKeyboardButton("➕ Add Exercise", callback_data="etadd")])
    keyboard.append(
        [InlineKeyboardButton("📝 Rename Template", callback_data="etrname")]
    )
    keyboard.append([InlineKeyboardButton("💾 Save & Exit", callback_data="etsave")])

    await message.reply_text(
        f"Editing: {context.user_data['editing_template_name']}\n\n"
        f"Exercises: {len(context.user_data['editing_exercises'])}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return EDIT_TEMPLATE_EXERCISE


async def save_edited_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the edited template."""
    query = update.callback_query
    await query.answer()

    template_id = context.user_data.get("editing_template_id")
    name = context.user_data.get("editing_template_name", "Unnamed Template")
    exercises = context.user_data.get("editing_exercises", [])

    if not exercises:
        await query.message.reply_text("Cannot save template with no exercises.")
        context.user_data.clear()
        return ConversationHandler.END

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Template).where(Template.id == template_id)
            )
            template = result.scalar_one()

            template.name = name
            await session.flush()

            await session.execute(
                TemplateExercise.__table__.delete().where(
                    TemplateExercise.template_id == template_id
                )
            )
            await session.flush()

            for idx, ex_data in enumerate(exercises):
                ex = TemplateExercise(
                    template_id=template.id,
                    exercise_name=ex_data["name"],
                    default_sets=ex_data["sets"],
                    default_weight=ex_data["weight"],
                    default_reps=ex_data["reps"],
                    order=idx,
                )
                session.add(ex)

            await session.commit()
            await query.message.edit_text(
                f"Template '{name}' saved with {len(exercises)} exercises! ✅"
            )
    except Exception as e:
        logger.error(f"Error saving template: {e}")
        await query.message.reply_text("Error saving template. Please try again.")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel template editing."""
    context.user_data.clear()
    await update.message.reply_text("Template editing canceled.")
    return ConversationHandler.END


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
    await query.edit_message_text(
        "Workout ended. Great effort! 💪\n/start_workout to begin a new workout."
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
            }
            for ex in exercises
        ],
        "current_index": 0,
        "logged_sets": {},  # {exercise_idx: [{weight, reps, timestamp}]}
    }

    # Show all exercises for selection
    keyboard = []
    for idx, ex in enumerate(context.user_data["current_workout"]["exercises"]):
        volume = ex["default_sets"] * ex["default_weight"] * ex["default_reps"]
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{ex['name']} ({ex['default_sets']}x{ex['default_weight']}kgx{ex['default_reps']} reps) - {volume}kg vol",
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


def build_set_keyboard(exercise_idx, ex_data, logged_sets, is_completed=False):
    """Build keyboard with individual set buttons."""
    keyboard = []
    total_sets = ex_data["default_sets"]
    default_weight = ex_data["default_weight"]
    default_reps = ex_data["default_reps"]

    for set_num in range(1, total_sets + 1):
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
            [InlineKeyboardButton("⏰ Rest 5m", callback_data="rest")],
            [InlineKeyboardButton("⏰ Custom Rest", callback_data="custom_rest")],
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

    keyboard = build_set_keyboard(idx, ex_data, logged_sets, is_completed)

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
        rest_message = await query.message.reply_text(
            "Rest timer started: 5 minutes. ⏳\n\n"
            "Click 'Skip Rest' to cancel and continue.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Skip Rest ⏭️", callback_data="cancel_rest")]]
            ),
        )
        job = context.job_queue.run_once(
            rest_timer_callback, 300, chat_id=query.message.chat_id
        )
        context.user_data["rest_job"] = job
        context.user_data["rest_message_id"] = rest_message.message_id
        return WORKOUT_EXERCISE_CONFIRM

    if data == "custom_rest":
        await query.message.edit_text(
            "Enter custom rest time in seconds (e.g., 90 for 1:30):"
        )
        context.user_data["waiting_for_custom_rest"] = True
        return WORKOUT_EXERCISE_INPUT

    if data == "cancel_rest":
        job = context.user_data.pop("rest_job", None)
        if job:
            job.schedule_removal()
        rest_message_id = context.user_data.pop("rest_message_id", None)
        try:
            if rest_message_id:
                await context.bot.delete_message(query.message.chat_id, rest_message_id)
            else:
                await query.message.edit_text("Rest timer canceled. Let's go! 💪")
        except Exception:
            pass
        return WORKOUT_EXERCISE_CONFIRM

    if data == "skip":
        context.user_data.pop("rest_job", None)
        logger.info(f"Skip handler triggered for user {user_id}")
        workout_data = context.user_data.get("current_workout")
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
                completed_count >= ex_data["default_sets"],
            ),
        )
        return WORKOUT_EXERCISE_CONFIRM

    if data == "edit_weight":
        exercise_idx = context.user_data.get("pending_exercise_idx", 0)
        ex_data = context.user_data.get("current_workout", {}).get("exercises", [{}])[
            exercise_idx
        ]
        default_weight = ex_data.get("default_weight", 0)

        await query.message.edit_text(
            f"Set {context.user_data.get('pending_set_num', 1)}: Select weight (default: {default_weight}kg):",
            reply_markup=WEIGHT_KEYBOARD,
        )
        return WORKOUT_EXERCISE_INPUT

    if data == "edit_reps":
        exercise_idx = context.user_data.get("pending_exercise_idx", 0)
        ex_data = context.user_data.get("current_workout", {}).get("exercises", [{}])[
            exercise_idx
        ]
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
        return WORKOUT_EXERCISE_INPUT

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
    exercise_idx = context.user_data.get("pending_exercise_idx", 0)
    ex_data = context.user_data.get("current_workout", {}).get("exercises", [{}])[
        exercise_idx
    ]
    default_reps = ex_data.get("default_reps", 0)

    await query.message.edit_text(
        f"Weight: {weight}kg\nSelect reps (default: {default_reps}):",
        reply_markup=REPS_KEYBOARD,
    )
    return WORKOUT_EXERCISE_INPUT


async def handle_reps_select(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id
):
    query = update.callback_query
    data = query.data

    if data == "r_custom":
        exercise_idx = context.user_data.get("pending_exercise_idx", 0)
        ex_data = context.user_data.get("current_workout", {}).get("exercises", [{}])[
            exercise_idx
        ]
        default_reps = ex_data.get("default_reps", 0)

        await query.message.edit_text(
            f"Enter custom reps (default: {default_reps}):",
        )
        context.user_data["waiting_for_reps"] = True
        return WORKOUT_EXERCISE_INPUT

    if data == "r_back":
        exercise_idx = context.user_data.get("pending_exercise_idx", 0)
        ex_data = context.user_data.get("current_workout", {}).get("exercises", [{}])[
            exercise_idx
        ]
        default_weight = ex_data.get("default_weight", 0)

        await query.message.edit_text(
            f"Set {context.user_data.get('pending_set_num', 1)}: Select weight for this set (default: {default_weight}kg):",
            reply_markup=WEIGHT_KEYBOARD,
        )
        return WORKOUT_EXERCISE_INPUT

    reps = int(data.replace("r_", ""))
    weight = context.user_data.get("pending_weight")

    if weight is None:
        await process_next_exercise(query.message, context, user_id)
        return WORKOUT_EXERCISE_CONFIRM

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

    # Show updated exercise view without deleting message
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkoutLog)
            .where(
                WorkoutLog.user_id == user_id,
                WorkoutLog.exercise_name
                == workout_data["exercises"][exercise_idx]["name"],
            )
            .order_by(desc(WorkoutLog.timestamp))
            .limit(1)
        )
        prev_log = result.scalar_one_or_none()
        if prev_log:
            prev_log_text = f"{prev_log.sets}s x {prev_log.weight}kg x {prev_log.reps}"
        else:
            prev_log_text = "No history"

    completed_count = len(logged_sets)
    ex_data = workout_data["exercises"][exercise_idx]
    await query.message.edit_text(
        f"Set {set_num} logged: {weight}kg x {reps} reps\n\n"
        f"Progress: {completed_count}/{ex_data['default_sets']} sets completed\n"
        f"Previous: {prev_log_text}",
        parse_mode="Markdown",
        reply_markup=build_set_keyboard(
            exercise_idx,
            ex_data,
            logged_sets,
            completed_count >= ex_data["default_sets"],
        ),
    )
    return WORKOUT_EXERCISE_CONFIRM


async def log_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual text input for weight/reps."""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if context.user_data.get("waiting_for_add_exercise"):
        parts = text.split()
        if len(parts) != 4:
            await update.message.reply_text(
                "Invalid format. Enter: 'Name sets weight reps'\nExample: 'Pushups 3 0 15'"
            )
            return WORKOUT_EXERCISE_INPUT
        try:
            name = parts[0]
            sets = int(parts[1])
            weight = float(parts[2])
            reps = int(parts[3])
        except ValueError:
            await update.message.reply_text(
                "Invalid format. Enter: 'Name sets weight reps'\nExample: 'Pushups 3 0 15'"
            )
            return WORKOUT_EXERCISE_INPUT
        workout_data = context.user_data.get("current_workout")
        if workout_data and "exercises" in workout_data:
            workout_data["exercises"].append(
                {
                    "name": name,
                    "default_sets": sets,
                    "default_weight": weight,
                    "default_reps": reps,
                }
            )
            context.user_data.pop("waiting_for_add_exercise", None)
            exercises = workout_data["exercises"]
            keyboard = []
            for idx, ex in enumerate(exercises):
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"{idx + 1}. {ex['name']} ({ex['default_sets']} sets x {ex['default_weight']}kg x {ex['default_reps']} reps)",
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
            exercise_idx = context.user_data.get("pending_exercise_idx", 0)
            ex_data = context.user_data.get("current_workout", {}).get(
                "exercises", [{}]
            )[exercise_idx]
            default_reps = ex_data.get("default_reps", 0)

            await update.message.reply_text(
                f"Weight: {weight}kg\nSelect reps (default: {default_reps}):",
                reply_markup=REPS_KEYBOARD,
            )
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
                rest_timer_callback, rest_seconds, chat_id=update.message.chat_id
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
    job = context.job
    rest_message_id = context.user_data.pop("rest_message_id", None)
    context.user_data.pop("rest_job", None)
    if rest_message_id:
        try:
            await context.bot.delete_message(job.chat_id, rest_message_id)
        except Exception:
            pass


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
