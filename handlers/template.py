"""Handlers for manual template creation, editing, and deletion."""

import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from database import AsyncSessionLocal, Template, TemplateExercise
import handlers.common as common
from handlers.common import (
    logger,
    parse_exercise_details,
    TEMPLATE_NAME,
    EXERCISE_NAME,
    EXERCISE_DETAILS,
    EDIT_TEMPLATE_SELECT,
    EDIT_TEMPLATE_EXERCISE,
    EDIT_TEMPLATE_NAME,
    EDIT_EXERCISE_NAME,
    EDIT_EXERCISE_DETAILS,
    DELETE_TEMPLATE_CONFIRM,
    WEIGHT_KEYBOARD,
    REPS_KEYBOARD,
)


# --- Template Creation ---


async def create_template_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Let's create a workout template. What specific name would you like to give this routine? (e.g., 'Leg Day')"
    )
    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
        except Exception as e:
            print(f"Could not delete: {e}")
    common.last_msg_id = update.message.message_id
    return TEMPLATE_NAME


async def template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["template_name"] = name
    context.user_data["editing_template_name"] = name
    context.user_data["editing_exercises"] = []
    context.user_data["editing_template_id"] = None

    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=common.last_msg_id
            )
        except Exception:
            pass
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id, message_id=update.message.message_id
        )
    except Exception:
        pass

    return await show_edited_template(update, context)


async def exercise_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() == "/done":
        return await save_template(update, context)

    context.user_data["current_exercise_name"] = text.strip()
    sent = await update.message.reply_text(
        f"Enter sets config for {text} (e.g., '3 60x5 65x4 70x3'):\n"
        f"Format: <num_sets> <weight>x<reps> <weight>x<reps> ..."
    )
    try:
        if common.last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception as e:
        print(f"Could not delete user message: {e}")
    common.last_msg_id = sent.message_id
    return EXERCISE_DETAILS


async def exercise_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text.lower() == "/done":
        return await save_template(update, context)

    num_sets, sets_config, error = parse_exercise_details(text)
    if error:
        sent = await update.message.reply_text(error)
        try:
            if common.last_msg_id:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=common.last_msg_id
                )
        except Exception:
            pass
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=update.message.message_id
            )
        except Exception:
            pass
        common.last_msg_id = sent.message_id
        return EXERCISE_DETAILS

    exercises = context.user_data.get("exercises", [])
    exercises.append(
        {
            "name": context.user_data["current_exercise_name"],
            "sets": num_sets,
            "sets_config": sets_config,
        }
    )
    context.user_data["exercises"] = exercises

    sent = await update.message.reply_text(
        f"✅ {context.user_data['current_exercise_name']} added with {num_sets} sets.\n"
        f"Enter next exercise name (or /done to finish):"
    )
    try:
        if common.last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
    except Exception:
        pass
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception:
        pass
    common.last_msg_id = sent.message_id
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
                default_weight=ex_data["sets_config"][0]["weight"]
                if ex_data.get("sets_config")
                else 0,
                default_reps=ex_data["sets_config"][0]["reps"]
                if ex_data.get("sets_config")
                else 0,
                sets_config=json.dumps(ex_data.get("sets_config", [])),
                order=idx,
            )
            session.add(ex)

        try:
            await session.commit()
            logger.info(f"Template saved successfully: {name}")
            sent = await update.message.reply_text(
                f"Template '{name}' saved with {len(exercises_data)} exercises! ✅"
            )
        except IntegrityError:
            await session.rollback()
            sent = await update.message.reply_text(
                f"A template named '{name}' already exists. Please rename it and try again."
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"Error saving template: {e}")
            sent = await update.message.reply_text(
                "Error saving template. Please try again."
            )

    try:
        if common.last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception as e:
        print(f"Could not delete user message: {e}")
    common.last_msg_id = sent.message_id
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sent = await update.message.reply_text("Action canceled.")
    try:
        if common.last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception as e:
        print(f"Could not delete user message: {e}")
    common.last_msg_id = sent.message_id
    context.user_data.clear()
    return ConversationHandler.END


async def done_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Redirect to editing UI for confirmation
    context.user_data["editing_template_id"] = None  # New template
    context.user_data["editing_template_name"] = context.user_data.get(
        "template_name", "Unnamed Template"
    )
    context.user_data["editing_exercises"] = [
        {
            "id": None,
            "name": ex["name"],
            "sets": ex["sets"],
            "weight": ex["sets_config"][0]["weight"] if ex["sets_config"] else 0,
            "reps": ex["sets_config"][0]["reps"] if ex["sets_config"] else 0,
            "sets_config": ex["sets_config"],
        }
        for ex in context.user_data.get("exercises", [])
    ]

    text = (
        f"Template '{context.user_data['editing_template_name']}' created.\n"
        "Review and edit below before saving:"
    )

    # Attempt to edit the last message sent by the bot
    if common.last_msg_id:
        try:
            sent = await context.bot.edit_message_text(
                chat_id=update.message.chat_id, message_id=common.last_msg_id, text=text
            )
            return await show_edited_template(update, context, sent)
        except Exception:
            pass

    sent = await update.message.reply_text(text)
    common.last_msg_id = sent.message_id
    return await show_edited_template(update, context, sent)


# --- Template Editing ---


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
            "sets_config": json.loads(ex.sets_config) if ex.sets_config else None,
        }
        for ex in exercises
    ]

    keyboard = []
    for idx, ex in enumerate(context.user_data["editing_exercises"]):
        sets_text = (
            ", ".join([f"{s['weight']}x{s['reps']}" for s in ex["sets_config"]])
            if ex.get("sets_config")
            else f"{ex['sets']}x{ex['weight']}kgx{ex['reps']}"
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"✏️ {ex['name']} ({sets_text})",
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
    keyboard.append(
        [InlineKeyboardButton("🗑️ Delete Template", callback_data="etdelete")]
    )

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
    common.last_msg_id = query.message.message_id

    if data == "etadd":
        await query.edit_message_text("Enter new exercise name:")
        context.user_data["is_template_add"] = True
        return EDIT_EXERCISE_NAME

    if data == "etrname":
        await query.edit_message_text("Enter new template name:")
        return EDIT_TEMPLATE_NAME

    if data == "etsave":
        return await save_edited_template(update, context)

    if data == "etdelete":
        return await confirm_delete_template(update, context)

    if data.startswith("etedit_"):
        idx = int(data.split("_")[1])
        context.user_data["editing_exercise_idx"] = idx
        return await show_template_exercise_sets(update, context, query.message)

    if data.startswith("etrm_"):
        idx = int(data.split("_")[1])
        removed = context.user_data["editing_exercises"].pop(idx)
        # We don't need a separate "Removed" message, the UI will reflect it
        return await show_edited_template(update, context, query.message)

    if data.startswith("etlog_set_"):
        parts = data.split("_")
        exercise_idx = int(parts[2])
        set_num = int(parts[3])
        context.user_data["pending_template_exercise_idx"] = exercise_idx
        context.user_data["pending_template_set_num"] = set_num
        context.user_data["is_template_edit"] = True

        ex = context.user_data["editing_exercises"][exercise_idx]
        sets_config = ex.get("sets_config", [])
        if set_num <= len(sets_config):
            existing = sets_config[set_num - 1]
            weight = existing["weight"]
            reps = existing["reps"]
        else:
            weight = ex.get("weight", 0)
            reps = ex.get("reps", 0)

        context.user_data["pending_weight"] = weight
        context.user_data["pending_reps"] = reps

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"✅ {weight}kg x {reps} reps", callback_data="etuse_current"
                    )
                ],
                [InlineKeyboardButton("Edit Weight", callback_data="edit_weight")],
                [InlineKeyboardButton("Edit Reps", callback_data="edit_reps")],
            ]
        )
        await query.edit_message_text(
            f"Set {set_num}: Use current values or edit:", reply_markup=keyboard
        )
        return EDIT_TEMPLATE_EXERCISE

    if data.startswith("etadd_set_"):
        idx = int(data.split("_")[1])
        context.user_data["editing_exercises"][idx]["sets"] += 1
        return await show_template_exercise_sets(update, context, query.message)

    if data.startswith("etrm_set_"):
        idx = int(data.split("_")[1])
        if context.user_data["editing_exercises"][idx]["sets"] > 1:
            context.user_data["editing_exercises"][idx]["sets"] -= 1
            if (
                "sets_config" in context.user_data["editing_exercises"][idx]
                and len(context.user_data["editing_exercises"][idx]["sets_config"])
                > context.user_data["editing_exercises"][idx]["sets"]
            ):
                context.user_data["editing_exercises"][idx]["sets_config"].pop()
        return await show_template_exercise_sets(update, context, query.message)

    if data == "back_to_template":
        context.user_data.pop("editing_exercise_idx", None)
        context.user_data.pop("is_template_edit", None)
        return await show_edited_template(update, context, query.message)

    if data == "edit_weight":
        exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
        ex_data = context.user_data["editing_exercises"][exercise_idx]
        default_weight = ex_data.get("weight", 0)
        set_num = context.user_data.get("pending_template_set_num", 1)

        await query.edit_message_text(
            f"Set {set_num}: Select weight (default: {default_weight}kg):",
            reply_markup=WEIGHT_KEYBOARD,
        )
        return EDIT_TEMPLATE_EXERCISE

    if data == "edit_reps":
        exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
        ex_data = context.user_data["editing_exercises"][exercise_idx]
        default_reps = ex_data.get("reps", 0)
        default_weight = ex_data.get("weight", 0)

        pending_weight = context.user_data.get("pending_weight")
        if pending_weight is None:
            context.user_data["pending_weight"] = default_weight
            pending_weight = default_weight

        await query.edit_message_text(
            f"Weight: {pending_weight}kg\nSelect reps (default: {default_reps}):",
            reply_markup=REPS_KEYBOARD,
        )
        return EDIT_TEMPLATE_EXERCISE

    if data.startswith("w_"):
        return await handle_template_weight_select(update, context)

    if data.startswith("r_"):
        return await handle_template_reps_select(update, context)

    if data == "etuse_current":
        weight = context.user_data.get("pending_weight")
        reps = context.user_data.get("pending_reps")
        return await handle_template_set_finish(update, context, weight, reps)

    return EDIT_TEMPLATE_EXERCISE


async def edit_exercise_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if (
        context.user_data.get("is_template_add")
        or context.user_data.get("editing_exercises") is not None
    ):
        # Initialize new exercise for template
        new_ex = {"name": text, "sets": 1, "weight": 0, "reps": 0, "sets_config": []}
        if "editing_exercises" not in context.user_data:
            context.user_data["editing_exercises"] = []

        context.user_data["editing_exercises"].append(new_ex)
        context.user_data["editing_exercise_idx"] = (
            len(context.user_data["editing_exercises"]) - 1
        )
        context.user_data.pop("is_template_add", None)

        # Cleanup messages
        if common.last_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=common.last_msg_id
                )
            except Exception:
                pass
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=update.message.message_id
            )
        except Exception:
            pass

        return await show_template_exercise_sets(update, context)

    context.user_data["new_exercise_name"] = text
    prompt_text = (
        f"Enter sets config for {text} (e.g., '3 60x5 65x4 70x3'):\n"
        f"Format: <num_sets> <weight>x<reps> <weight>x<reps> ..."
    )
    if common.last_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=common.last_msg_id,
                text=prompt_text,
            )
            return EDIT_EXERCISE_DETAILS
        except Exception:
            pass

    sent = await update.message.reply_text(prompt_text)
    common.last_msg_id = sent.message_id
    return EDIT_EXERCISE_DETAILS


async def edit_exercise_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text.lower() == "/skip":
        return await show_edited_template(update, context, None)

    parts = text.strip().split()

    if len(parts) < 2:
        sent = await update.message.reply_text(
            "Invalid format. Use: '3 60x5 65x4 70x3'\n"
            "Format: <num_sets> <weight>x<reps> <weight>x<reps> ..."
        )
        common.last_msg_id = sent.message_id
        return EDIT_EXERCISE_DETAILS

    try:
        num_sets = int(parts[0])
        if num_sets <= 0:
            raise ValueError("Sets must be positive")
    except ValueError:
        sent = await update.message.reply_text(
            "First value must be number of sets (e.g., '3')."
        )
        common.last_msg_id = sent.message_id
        return EDIT_EXERCISE_DETAILS

    sets_config = []
    for i in range(1, len(parts)):
        try:
            weight_reps = parts[i].split("x")
            if len(weight_reps) != 2:
                raise ValueError
            weight = float(weight_reps[0])
            reps = int(weight_reps[1])
            if reps <= 0 or weight < 0:
                raise ValueError
            sets_config.append({"weight": weight, "reps": reps})
        except (ValueError, IndexError):
            sent = await update.message.reply_text(
                f"Invalid format '{parts[i]}'. Use: '60x5' for 60kg x 5 reps"
            )
            try:
                if common.last_msg_id:
                    await context.bot.delete_message(
                        chat_id=update.message.chat_id, message_id=common.last_msg_id
                    )
            except Exception as e:
                print(f"Could not delete: {e}")
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=update.message.message_id
                )
            except Exception as e:
                print(f"Could not delete user message: {e}")
            common.last_msg_id = sent.message_id
            return EDIT_EXERCISE_DETAILS

    if len(sets_config) != num_sets:
        sent = await update.message.reply_text(
            f"Mismatch: You said {num_sets} sets but provided {len(sets_config)} weight x reps values."
        )
        try:
            if common.last_msg_id:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=common.last_msg_id
                )
        except Exception as e:
            print(f"Could not delete: {e}")
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=update.message.message_id
            )
        except Exception as e:
            print(f"Could not delete user message: {e}")
        common.last_msg_id = sent.message_id
        return EDIT_EXERCISE_DETAILS

    exercise_idx = context.user_data.get("editing_exercise_idx")
    if exercise_idx is not None:
        context.user_data["editing_exercises"][exercise_idx].update(
            {
                "name": context.user_data.get(
                    "new_exercise_name",
                    context.user_data["editing_exercises"][exercise_idx]["name"],
                ),
                "sets": num_sets,
                "weight": sets_config[0]["weight"],
                "reps": sets_config[0]["reps"],
                "sets_config": sets_config,
            }
        )
        context.user_data.pop("editing_exercise_idx", None)
    else:
        context.user_data["editing_exercises"].append(
            {
                "name": context.user_data["new_exercise_name"],
                "sets": num_sets,
                "weight": sets_config[0]["weight"],
                "reps": sets_config[0]["reps"],
                "sets_config": sets_config,
            }
        )
        context.user_data.pop("new_exercise_name", None)

    return await show_edited_template(update, context, None)


async def edit_template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template renaming."""
    context.user_data["editing_template_name"] = update.message.text.strip()
    try:
        if common.last_msg_id:
            # Will be edited by show_edited_template
            pass
    except Exception as e:
        print(f"Could not delete: {e}")
    return await show_edited_template(update, context, None)


# --- Template Display/UI ---


async def show_edited_template(update, context, message=None):
    """Show the current state of the edited template by editing a message."""
    keyboard = []
    for idx, ex in enumerate(context.user_data["editing_exercises"]):
        sets_text = (
            ", ".join([f"{s['weight']}x{s['reps']}" for s in ex["sets_config"]])
            if ex.get("sets_config")
            else f"{ex['sets']}x{ex['weight']}kgx{ex['reps']}"
        )
        # Calculate volume
        if ex.get("sets_config"):
            volume = sum(s["weight"] * s["reps"] for s in ex["sets_config"])
        else:
            volume = ex["sets"] * ex.get("weight", 0) * ex.get("reps", 0)
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"✏️ {ex['name']} ({ex['sets']}x{ex.get('weight', 0)}kgx{ex.get('reps', 0)}) - {volume}kg vol",
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
    keyboard.append(
        [InlineKeyboardButton("🗑️ Delete Template", callback_data="etdelete")]
    )

    name = context.user_data["editing_template_name"]
    text = (
        f"**Template: {name}**\n\n"
        "Review your exercises and settings below. Tap to edit or remove.\n\n"
        f"Exercises: {len(context.user_data['editing_exercises'])}"
    )

    if message and hasattr(message, "edit_text"):
        try:
            await message.edit_text(
                text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return EDIT_TEMPLATE_EXERCISE
        except Exception:
            pass

    if common.last_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=common.last_msg_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return EDIT_TEMPLATE_EXERCISE
        except Exception:
            pass

    sent = await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    common.last_msg_id = sent.message_id
    return EDIT_TEMPLATE_EXERCISE


def build_template_set_keyboard(exercise_idx, ex_data, context):
    """Build keyboard for editing sets in a template."""
    keyboard = []
    sets_config = ex_data.get("sets_config", [])
    total_sets = ex_data["sets"]

    for set_num in range(1, total_sets + 1):
        if set_num <= len(sets_config):
            weight = sets_config[set_num - 1]["weight"]
            reps = sets_config[set_num - 1]["reps"]
        else:
            weight = ex_data.get("weight", 0)
            reps = ex_data.get("reps", 0)

        button_text = f"Set {set_num}: {weight}kg x {reps}"
        callback_data = f"etlog_set_{exercise_idx}_{set_num}"
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=callback_data)]
        )

    keyboard.append(
        [InlineKeyboardButton("➕ Add Set", callback_data=f"etadd_set_{exercise_idx}")]
    )
    if total_sets > 1:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "➖ Remove Set", callback_data=f"etrm_set_{exercise_idx}"
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("⬅️ Back to Exercises", callback_data="back_to_template")]
    )
    return InlineKeyboardMarkup(keyboard)


async def show_template_exercise_sets(update, context, message=None):
    """Show the sets of an exercise being edited in a template."""
    idx = context.user_data.get("editing_exercise_idx")
    ex = context.user_data["editing_exercises"][idx]

    text = (
        f"**Editing Exercise: {ex['name']}**\nSelect a set to edit its weight and reps:"
    )
    keyboard = build_template_set_keyboard(idx, ex, context)

    if message and hasattr(message, "edit_text"):
        await message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        sent = await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=keyboard
        )
        common.last_msg_id = sent.message_id

    return EDIT_TEMPLATE_EXERCISE


# --- Template Save/Delete ---


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
            if template_id:
                result = await session.execute(
                    select(Template).where(Template.id == template_id)
                )
                template = result.scalar_one()
                template.name = name
                await session.flush()

                # Clear existing exercises if editing an existing template
                await session.execute(
                    TemplateExercise.__table__.delete().where(
                        TemplateExercise.template_id == template_id
                    )
                )
                await session.flush()
            else:
                user_id = update.effective_user.id
                template = Template(name=name, user_id=user_id)
                session.add(template)
                await session.flush()

            for idx, ex_data in enumerate(exercises):
                ex = TemplateExercise(
                    template_id=template.id,
                    exercise_name=ex_data["name"],
                    default_sets=ex_data["sets"],
                    default_weight=ex_data["sets_config"][0]["weight"]
                    if ex_data.get("sets_config")
                    else 0,
                    default_reps=ex_data["sets_config"][0]["reps"]
                    if ex_data.get("sets_config")
                    else 0,
                    sets_config=json.dumps(ex_data.get("sets_config", [])),
                    order=idx,
                )
                session.add(ex)

            await session.commit()
            if query:
                await query.message.edit_text(
                    f"Template '{name}' saved with {len(exercises)} exercises! ✅"
                )
            else:
                await update.message.reply_text(
                    f"Template '{name}' saved with {len(exercises)} exercises! ✅"
                )
    except IntegrityError:
        await query.message.reply_text(
            f"A template named '{name}' already exists. Please rename it and try again."
        )
        return EDIT_TEMPLATE_EXERCISE
    except Exception as e:
        logger.error(f"Error saving template: {e}")
        await query.message.reply_text("Error saving template. Please try again.")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel template editing."""
    context.user_data.clear()
    sent = await update.message.reply_text("Template editing canceled.")
    try:
        if common.last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception as e:
        print(f"Could not delete user message: {e}")
    common.last_msg_id = sent.message_id
    return ConversationHandler.END


async def confirm_delete_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user to confirm template deletion."""
    query = update.callback_query
    await query.answer()

    template_name = context.user_data.get("editing_template_name", "this template")

    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Delete", callback_data="etdel_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="etdel_cancel"),
        ]
    ]

    await query.edit_message_text(
        f"Are you sure you want to delete template '{template_name}'?\n\nThis action cannot be undone!",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return DELETE_TEMPLATE_CONFIRM


async def handle_delete_template_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle the user's confirmation to delete a template."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "etdel_cancel":
        # Return to editing
        return await show_edited_template(update, context, query.message)

    if data == "etdel_confirm":
        template_id = context.user_data.get("editing_template_id")
        template_name = context.user_data.get("editing_template_name", "Template")

        if template_id:
            try:
                async with AsyncSessionLocal() as session:
                    # Delete associated exercises first
                    await session.execute(
                        TemplateExercise.__table__.delete().where(
                            TemplateExercise.template_id == template_id
                        )
                    )
                    await session.flush()

                    # Delete the template
                    await session.execute(
                        Template.__table__.delete().where(Template.id == template_id)
                    )
                    await session.commit()

                await query.edit_message_text(
                    f"Template '{template_name}' has been deleted. ✅"
                )
            except Exception as e:
                logger.error(f"Error deleting template: {e}")
                await query.edit_message_text(
                    "Error deleting template. Please try again."
                )
        else:
            # Template hasn't been saved yet — just discard it
            await query.edit_message_text(
                f"Template '{template_name}' discarded. ✅"
            )

        context.user_data.clear()
        return ConversationHandler.END

    return DELETE_TEMPLATE_CONFIRM


# --- Template Weight/Reps Selection ---


async def handle_template_weight_select(update, context):
    """Handle weight selection when editing template sets."""
    query = update.callback_query
    data = query.data

    if data == "w_back":
        return await show_template_exercise_sets(update, context, query.message)

    if data == "w_custom":
        await query.edit_message_text("Enter custom weight (kg):")
        context.user_data["waiting_for_weight"] = True
        return EDIT_TEMPLATE_EXERCISE

    weight = float(data.replace("w_", ""))
    context.user_data["pending_weight"] = weight

    exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
    ex_data = context.user_data["editing_exercises"][exercise_idx]
    default_reps = ex_data.get("reps", 0)

    await query.edit_message_text(
        f"Weight: {weight}kg\nSelect reps (default: {default_reps}):",
        reply_markup=REPS_KEYBOARD,
    )
    return EDIT_TEMPLATE_EXERCISE


async def handle_template_reps_select(update, context):
    """Handle reps selection when editing template sets."""
    query = update.callback_query
    data = query.data

    if data == "r_back":
        exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
        ex_data = context.user_data["editing_exercises"][exercise_idx]
        default_weight = ex_data.get("weight", 0)
        set_num = context.user_data.get("pending_template_set_num", 1)

        await query.edit_message_text(
            f"Set {set_num}: Select weight (default: {default_weight}kg):",
            reply_markup=WEIGHT_KEYBOARD,
        )
        return EDIT_TEMPLATE_EXERCISE

    if data == "r_custom":
        exercise_idx = context.user_data.get("pending_template_exercise_idx", 0)
        ex_data = context.user_data["editing_exercises"][exercise_idx]
        default_reps = ex_data.get("reps", 0)

        await query.edit_message_text(f"Enter custom reps (default: {default_reps}):")
        context.user_data["waiting_for_reps"] = True
        return EDIT_TEMPLATE_EXERCISE

    reps = int(data.replace("r_", ""))
    weight = context.user_data.get("pending_weight")

    return await handle_template_set_finish(update, context, weight, reps)


async def handle_template_set_finish(update, context, weight, reps):
    """Finalize a set edit in a template."""
    query = update.callback_query
    exercise_idx = context.user_data.get("pending_template_exercise_idx")
    set_num = context.user_data.get("pending_template_set_num")

    ex = context.user_data["editing_exercises"][exercise_idx]
    if "sets_config" not in ex:
        ex["sets_config"] = []

    while len(ex["sets_config"]) < set_num:
        ex["sets_config"].append(
            {"weight": ex.get("weight", 0), "reps": ex.get("reps", 0)}
        )

    ex["sets_config"][set_num - 1] = {"weight": weight, "reps": reps}

    # Update default weight/reps if it's the first set or if they were 0
    if set_num == 1 or ex.get("weight", 0) == 0:
        ex["weight"] = weight
        ex["reps"] = reps

    context.user_data.pop("pending_weight", None)
    context.user_data.pop("pending_reps", None)
    context.user_data.pop("pending_template_exercise_idx", None)
    context.user_data.pop("pending_template_set_num", None)

    return await show_template_exercise_sets(update, context, query.message)
