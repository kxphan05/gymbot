import asyncio
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
from sqlalchemy import select, desc, update
from sqlalchemy.orm import selectinload
from database import AsyncSessionLocal, User, Template, TemplateExercise, WorkoutLog
import os
from openai import AsyncOpenAI

client = None


def get_client():
    global client
    if client is None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_TOKEN")
        if not api_key:
            # Fallback for testing or incomplete setup
            return AsyncOpenAI(api_key="sk-dummy")
        client = AsyncOpenAI(api_key=api_key, base_url="https://api.publicai.co/v1")
    return client


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
last_msg_id = None
last_chat_id = None


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
    ADD_TEMPLATE_AI_INPUT,
    DELETE_TEMPLATE_CONFIRM,
) = range(15)

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
            InlineKeyboardButton("Custom", callback_data="r_custom"),
            InlineKeyboardButton("⬅️ Back to Weight", callback_data="r_back"),
        ],
    ]
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_msg_id
    global last_chat_id
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
        if last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    last_msg_id = update.message.message_id


SETTINGS_REST, SETTINGS_REST_CONFIRM = range(20, 22)


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
    global last_msg_id
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Enter your default rest time in seconds (e.g., 90 for 1:30, 180 for 3m):"
    )
    if last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id, message_id=last_msg_id
            )
        except Exception as e:
            print(f"Could not delete: {e}")
    last_msg_id = query.message.message_id
    return SETTINGS_REST_CONFIRM


async def settings_rest_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the new rest time."""
    global last_msg_id
    text = update.message.text.strip()
    user_id = update.effective_user.id

    try:
        rest_seconds = int(text)
        if rest_seconds <= 0 or rest_seconds > 600:
            await update.message.reply_text(
                "Please enter between 1-600 seconds (10 minutes max)."
            )
            return SETTINGS_REST_CONFIRM
    except ValueError:
        await update.message.reply_text("Invalid number. Enter seconds (e.g., 90):")
        return SETTINGS_REST_CONFIRM

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
    if last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
        except Exception as e:
            print(f"Could not delete: {e}")
    last_msg_id = update.message.message_id
    return ConversationHandler.END


async def add_template_ai_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the AI template creation flow."""
    global last_msg_id
    await update.message.reply_text(
        "Please describe your workout template in natural language, or upload a file (CSV or photo).\n"
        "Example: 'Push Day: 3 sets of Bench Press 80kg for 5 reps, 3 sets of Overhead Press 40kg for 8 reps'\n\n"
        "You can also upload:\n"
        "• A CSV file with workout data\n"
        "• A photo of a workout plan (I'll read it with AI)"
    )
    if last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
        except Exception as e:
            print(f"Could not delete: {e}")
    last_msg_id = update.message.message_id
    return ADD_TEMPLATE_AI_INPUT


async def process_ai_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the natural language workout description using OpenAI."""
    global last_msg_id
    user_input = update.message.text

    # Show typing action to user
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Send transient processing message
    processing_msg = await update.message.reply_text(
        "Got it! Analyzing your workout routine... ⏳"
    )
    if last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
        except Exception:
            pass
    last_msg_id = processing_msg.message_id

    ai_client = get_client()
    system_prompt = (
        "You are a workout assistant. Your task is to parse a workout description into a detailed JSON format.\n"
        "The output MUST be a JSON object with two keys:\n"
        '1. "template_name": (string) A concise name for the workout.\n'
        '2. "exercises": (list of objects) Each object must have:\n'
        '   - "name": (string) Exercise name.\n'
        '   - "sets": (int) Total number of sets.\n'
        '   - "sets_config": (list of objects) Each object has "weight" (float) and "reps" (int).\n\n'
        "CRITICAL RULES:\n"
        '- Group ALL sets of the same exercise into a single entry in the "exercises" list.\n'
        "- DO NOT repeat the same exercise multiple times in the list.\n"
        "- Provide ONLY the JSON response, no other text.\n\n"
        "EXAMPLES:\n"
        'User: "Leg Day: 3 sets of Squats at 100kg for 5 reps"\n'
        'Assistant: {"template_name": "Leg Day", "exercises": [{"name": "Squats", "sets": 3, "sets_config": [{"weight": 100.0, "reps": 5}, {"weight": 100.0, "reps": 5}, {"weight": 100.0, "reps": 5}]}]}\n\n'
        'User: "Upper Body: Bench Press 2 sets 60kg x 10, then 1 set 65kg x 8"\n'
        'Assistant: {"template_name": "Upper Body", "exercises": [{"name": "Bench Press", "sets": 3, "sets_config": [{"weight": 60.0, "reps": 10}, {"weight": 60.0, "reps": 10}, {"weight": 65.0, "reps": 8}]}]}'
    )

    try:
        response = await ai_client.chat.completions.create(
            model="allenai/Molmo2-8B",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            response_format={"type": "json_object"},
            max_tokens=4000,
        )

        content = response.choices[0].message.content
        logger.info(f"AI Response length: {len(content)} characters")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as je:
            logger.warning(
                f"Initial JSON parsing failed: {je}. Attempting to fix truncated JSON."
            )
            # Attempt to fix truncated JSON by closing arrays and objects
            fixed_content = content.strip()
            # Simple heuristic: if it doesn't end with } or ] and looks like a JSON object
            if not fixed_content.endswith("}"):
                stack = []
                for char in fixed_content:
                    if char == "{":
                        stack.append("}")
                    elif char == "[":
                        stack.append("]")
                    elif char == "}":
                        if stack and stack[-1] == "}":
                            stack.pop()
                    elif char == "]":
                        if stack and stack[-1] == "]":
                            stack.pop()

                # Append missing closing brackets in reverse order (LIFO)
                while stack:
                    fixed_content += stack.pop()

                try:
                    data = json.loads(fixed_content)
                    logger.info("Successfully fixed truncated JSON.")
                except json.JSONDecodeError as je2:
                    logger.error(f"JSON parsing error after fix attempt: {je2}")
                    logger.error(
                        f"Raw content snippet: {content[:1000]}...{content[-500:]}"
                    )
                    await update.message.reply_text(
                        "The AI returned an invalid or truncated response. Please try again with a shorter description."
                    )
                    return ADD_TEMPLATE_AI_INPUT
            else:
                # Re-raise if it ends with } but still failed
                logger.error(f"JSON parsing error: {je}")
                logger.error(f"Raw content snippet: {content[:1000]}")
                await update.message.reply_text(
                    "The AI returned an invalid response. Please try again."
                )
                return ADD_TEMPLATE_AI_INPUT

        template_name = data.get("template_name", "AI Template")
        raw_exercises = data.get("exercises", [])

        exercises = []
        for ex in raw_exercises:
            name = ex.get("name", "Unknown Exercise")
            num_sets = ex.get("sets", 0)
            sets_config = ex.get("sets_config", [])

            # Simple validation
            if num_sets > 0 and len(sets_config) > 0:
                # Ensure weight and reps are valid
                valid_config = []
                for s in sets_config:
                    weight = float(s.get("weight", 0.0))
                    reps = int(s.get("reps", 0))
                    if reps > 0:
                        valid_config.append({"weight": weight, "reps": reps})

                if valid_config:
                    exercises.append(
                        {
                            "name": name,
                            "sets": len(valid_config),
                            "sets_config": valid_config,
                        }
                    )
            else:
                logger.warning(f"AI parsing skip exercise {name}: Invalid structure")

        if not exercises:
            await update.message.reply_text(
                "Could not parse any exercises correctly. Please try again with a clearer description."
            )
            return ADD_TEMPLATE_AI_INPUT

        context.user_data["template_name"] = template_name
        context.user_data["exercises"] = exercises

        # Redirect to editing UI for confirmation
        context.user_data["editing_template_id"] = None  # New template
        context.user_data["editing_template_name"] = template_name
        context.user_data["editing_exercises"] = [
            {
                "id": None,
                "name": ex["name"],
                "sets": ex["sets"],
                "weight": ex["sets_config"][0]["weight"] if ex["sets_config"] else 0,
                "reps": ex["sets_config"][0]["reps"] if ex["sets_config"] else 0,
                "sets_config": ex["sets_config"],
            }
            for ex in exercises
        ]

        # Confirmation message
        ex_list = "\n".join([f"- {ex['name']}: {ex['sets']} sets" for ex in exercises])
        sent = await update.message.reply_text(
            f"I've parsed your workout:\n\n"
            f"**Template Name:** {template_name}\n"
            f"**Exercises:**\n{ex_list}\n\n"
            f"Review and edit below:"
        )

        # Update last_msg_id so show_edited_template uses it
        if last_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=last_msg_id
                )
            except Exception:
                pass
        last_msg_id = sent.message_id

        # Pass the message object so show_edited_template can edit it
        return await show_edited_template(update, context, sent)

    except Exception as e:
        logger.error(f"AI parsing error: {e}")
        await update.message.reply_text(
            "Sorry, I had trouble understanding that. Please make sure the description is clear and try again, or use /cancel to stop."
        )
        return ADD_TEMPLATE_AI_INPUT


async def process_ai_template_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process file uploads (CSV or photos) for AI template creation."""
    global last_msg_id
    import tempfile
    import csv
    import io
    import base64

    # Show typing action
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    processing_msg = await update.message.reply_text("Processing your file... ⏳")
    if last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
        except Exception:
            pass
    last_msg_id = processing_msg.message_id

    try:
        # Check if it's a photo
        if update.message.photo:
            # Get the largest photo
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)

            # Download to memory
            image_bytes = io.BytesIO()
            await file.download_to_memory(image_bytes)
            image_bytes.seek(0)

            # Convert to base64 for AI vision
            image_base64 = base64.b64encode(image_bytes.read()).decode("utf-8")

            ai_client = get_client()
            system_prompt = (
                "You are a workout assistant. Your task is to analyze an image of a workout plan "
                "and parse it into a detailed JSON format.\n"
                "The output MUST be a JSON object with two keys:\n"
                '1. "template_name": (string) A concise name for the workout.\n'
                '2. "exercises": (list of objects) Each object must have:\n'
                '   - "name": (string) Exercise name.\n'
                '   - "sets": (int) Total number of sets.\n'
                '   - "sets_config": (list of objects) Each object has "weight" (float) and "reps" (int).\n\n'
                "CRITICAL RULES:\n"
                '- Group ALL sets of the same exercise into a single entry in the "exercises" list.\n'
                "- DO NOT repeat the same exercise multiple times in the list.\n"
                "- If weight is not specified, use 0.\n"
                "- Provide ONLY the JSON response, no other text."
            )

            response = await ai_client.chat.completions.create(
                model="allenai/Molmo2-8B",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Parse this workout image into JSON format.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=4000,
            )

            content = response.choices[0].message.content
            logger.info(f"AI Vision Response length: {len(content)} characters")

            try:
                data = json.loads(content)
            except json.JSONDecodeError as je:
                logger.error(f"JSON parsing error from image: {je}")
                await update.message.reply_text(
                    "Could not parse the workout from the image. Please try again with a clearer photo or use text input."
                )
                return ADD_TEMPLATE_AI_INPUT

            return await _process_parsed_workout(update, context, data)

        # Check if it's a document (CSV or other file)
        elif update.message.document:
            document = update.message.document
            file = await context.bot.get_file(document.file_id)

            # Download to memory
            file_bytes = io.BytesIO()
            await file.download_to_memory(file_bytes)
            file_bytes.seek(0)

            # Check if it's a CSV
            if document.mime_type == "text/csv" or document.file_name.endswith(".csv"):
                try:
                    # Parse CSV
                    content = file_bytes.read().decode("utf-8")
                    csv_reader = csv.DictReader(io.StringIO(content))

                    exercises = []
                    template_name = "CSV Import"

                    for row in csv_reader:
                        # Try to extract common CSV formats
                        name = row.get(
                            "exercise",
                            row.get(
                                "name", row.get("Exercise", row.get("Name", "Unknown"))
                            ),
                        )
                        sets = parse_reps(
                            row.get("sets", row.get("Sets", row.get("set", 1)))
                        )
                        reps = parse_reps(
                            row.get("reps", row.get("Reps", row.get("rep", 0)))
                        )
                        weight = float(
                            row.get("weight", row.get("Weight", row.get("kg", 0)))
                        )

                        if name and name != "Unknown":
                            sets_config = [
                                {"weight": weight, "reps": reps} for _ in range(sets)
                            ]
                            exercises.append(
                                {"name": name, "sets": sets, "sets_config": sets_config}
                            )

                    if not exercises:
                        await update.message.reply_text(
                            "Could not parse any exercises from the CSV. Please ensure it has columns like: name, sets, reps, weight"
                        )
                        return ADD_TEMPLATE_AI_INPUT

                    data = {"template_name": template_name, "exercises": exercises}
                    return await _process_parsed_workout(update, context, data)

                except Exception as e:
                    logger.error(f"CSV parsing error: {e}")
                    await update.message.reply_text(
                        f"Error parsing CSV: {e}. Please ensure the file is a valid CSV with proper columns (name, sets, reps, weight)."
                    )
                    return ADD_TEMPLATE_AI_INPUT

            else:
                # Non-CSV file - try to extract text and process with AI
                try:
                    content = file_bytes.read().decode("utf-8")

                    ai_client = get_client()
                    system_prompt = (
                        "You are a workout assistant. Your task is to parse a workout description into a detailed JSON format.\n"
                        "The output MUST be a JSON object with two keys:\n"
                        '1. "template_name": (string) A concise name for the workout.\n'
                        '2. "exercises": (list of objects) Each object must have:\n'
                        '   - "name": (string) Exercise name.\n'
                        '   - "sets": (int) Total number of sets.\n'
                        '   - "sets_config": (list of objects) Each object has "weight" (float) and "reps" (int).\n\n'
                        "Provide ONLY the JSON response, no other text."
                    )

                    response = await ai_client.chat.completions.create(
                        model="allenai/Molmo2-8B",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": content},
                        ],
                        response_format={"type": "json_object"},
                        max_tokens=4000,
                    )

                    data = json.loads(response.choices[0].message.content)
                    return await _process_parsed_workout(update, context, data)

                except Exception as e:
                    logger.error(f"File processing error: {e}")
                    await update.message.reply_text(
                        "Could not process this file type. Please upload a CSV file or photo of your workout plan."
                    )
                    return ADD_TEMPLATE_AI_INPUT

        else:
            await update.message.reply_text(
                "Unsupported file type. Please upload a CSV file or photo."
            )
            return ADD_TEMPLATE_AI_INPUT

    except Exception as e:
        logger.error(f"File processing error: {e}")
        await update.message.reply_text(
            f"Error processing file: {e}. Please try again or use text input."
        )
        return ADD_TEMPLATE_AI_INPUT


def parse_reps(reps_value):
    """Parse reps value that might be a range like '12-15' or a single number."""
    if reps_value is None:
        return 0
    if isinstance(reps_value, int):
        return reps_value
    if isinstance(reps_value, float):
        return int(reps_value)
    # Handle string values including ranges like "12-15"
    reps_str = str(reps_value).strip()
    if "-" in reps_str:
        # For ranges like "12-15", take the first value
        try:
            return int(reps_str.split("-")[0].strip())
        except ValueError:
            return 0
    try:
        return int(reps_str)
    except ValueError:
        return 0


async def _process_parsed_workout(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict
):
    """Helper function to process parsed workout data from any source."""
    global last_msg_id

    template_name = data.get("template_name", "AI Template")
    raw_exercises = data.get("exercises", [])

    exercises = []
    for ex in raw_exercises:
        name = ex.get("name", "Unknown Exercise")
        num_sets = ex.get("sets", 0)
        sets_config = ex.get("sets_config", [])

        # Simple validation
        if num_sets > 0 and len(sets_config) > 0:
            # Ensure weight and reps are valid
            valid_config = []
            for s in sets_config:
                weight = float(s.get("weight", 0.0))
                reps = parse_reps(s.get("reps", 0))
                if reps > 0:
                    valid_config.append({"weight": weight, "reps": reps})

            if valid_config:
                exercises.append(
                    {
                        "name": name,
                        "sets": len(valid_config),
                        "sets_config": valid_config,
                    }
                )
        else:
            logger.warning(f"AI parsing skip exercise {name}: Invalid structure")

    if not exercises:
        await update.message.reply_text(
            "Could not parse any exercises correctly. Please try again with a clearer description."
        )
        return ADD_TEMPLATE_AI_INPUT

    context.user_data["template_name"] = template_name
    context.user_data["exercises"] = exercises

    # Redirect to editing UI for confirmation
    context.user_data["editing_template_id"] = None  # New template
    context.user_data["editing_template_name"] = template_name
    context.user_data["editing_exercises"] = [
        {
            "id": None,
            "name": ex["name"],
            "sets": ex["sets"],
            "weight": ex["sets_config"][0]["weight"] if ex["sets_config"] else 0,
            "reps": ex["sets_config"][0]["reps"] if ex["sets_config"] else 0,
            "sets_config": ex["sets_config"],
        }
        for ex in exercises
    ]

    # Confirmation message
    ex_list = "\n".join([f"- {ex['name']}: {ex['sets']} sets" for ex in exercises])
    sent = await update.message.reply_text(
        f"I've parsed your workout:\n\n"
        f"**Template Name:** {template_name}\n"
        f"**Exercises:**\n{ex_list}\n\n"
        f"Review and edit below:"
    )

    # Update last_msg_id so show_edited_template uses it
    if last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
        except Exception:
            pass
    last_msg_id = sent.message_id

    # Pass the message object so show_edited_template can edit it
    return await show_edited_template(update, context, sent)


async def create_template_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_msg_id
    await update.message.reply_text(
        "Let's create a workout template. What specific name would you like to give this routine? (e.g., 'Leg Day')"
    )
    if last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
        except Exception as e:
            print(f"Could not delete: {e}")
    last_msg_id = update.message.message_id
    return TEMPLATE_NAME


async def template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_msg_id
    name = update.message.text.strip()
    context.user_data["template_name"] = name
    context.user_data["editing_exercises"] = []
    context.user_data["editing_template_id"] = None

    if last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=last_msg_id
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
    global last_msg_id
    text = update.message.text
    if text.lower() == "/done":
        return await save_template(update, context)

    context.user_data["current_exercise_name"] = text.strip()
    sent = await update.message.reply_text(
        f"Enter sets config for {text} (e.g., '3 60x5 65x4 70x3'):\n"
        f"Format: <num_sets> <weight>x<reps> <weight>x<reps> ..."
    )
    try:
        if last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception as e:
        print(f"Could not delete user message: {e}")
    last_msg_id = sent.message_id
    return EXERCISE_DETAILS


def parse_exercise_details(text: str):
    """Parse exercise details string into (num_sets, sets_config, error_message)."""
    parts = text.strip().split()
    if len(parts) < 2:
        return (
            None,
            None,
            (
                "Invalid format. Use: '3 60x5 65x4 70x3'\n"
                "Format: <num_sets> <weight>x<reps> <weight>x<reps> ..."
            ),
        )

    try:
        num_sets = int(parts[0])
        if num_sets <= 0:
            return (
                None,
                None,
                "First value must be a positive number of sets (e.g., '3').",
            )
    except ValueError:
        return None, None, "First value must be number of sets (e.g., '3')."

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
            return (
                None,
                None,
                f"Invalid format '{parts[i]}'. Use: '60x5' for 60kg x 5 reps",
            )

    if len(sets_config) != num_sets:
        return (
            None,
            None,
            (
                f"Mismatch: You said {num_sets} sets but provided {len(sets_config)} values.\n"
                f"Example for 3 sets: '3 60x5 65x4 70x3'"
            ),
        )

    return num_sets, sets_config, None


async def exercise_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_msg_id
    text = update.message.text

    if text.lower() == "/done":
        return await save_template(update, context)

    num_sets, sets_config, error = parse_exercise_details(text)
    if error:
        sent = await update.message.reply_text(error)
        try:
            if last_msg_id:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=last_msg_id
                )
        except Exception:
            pass
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=update.message.message_id
            )
        except Exception:
            pass
        last_msg_id = sent.message_id
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
        if last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
    except Exception:
        pass
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception:
        pass
    last_msg_id = sent.message_id
    return EXERCISE_NAME


async def save_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_msg_id
    import json

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
        except Exception as e:
            await session.rollback()
            logger.error(f"Error saving template: {e}")
            sent = await update.message.reply_text(
                "Error saving template. Please try again."
            )

    try:
        if last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception as e:
        print(f"Could not delete user message: {e}")
    last_msg_id = sent.message_id
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_msg_id
    sent = await update.message.reply_text("Action canceled.")
    try:
        if last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception as e:
        print(f"Could not delete user message: {e}")
    last_msg_id = sent.message_id
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

    global last_msg_id
    # We want to edit the LAST message if possible, or send a new one and then edit it
    text = (
        f"Template '{context.user_data['editing_template_name']}' created.\n"
        "Review and edit below before saving:"
    )

    # Attempt to edit the last message sent by the bot
    if last_msg_id:
        try:
            sent = await context.bot.edit_message_text(
                chat_id=update.message.chat_id, message_id=last_msg_id, text=text
            )
            return await show_edited_template(update, context, sent)
        except Exception:
            pass

    sent = await update.message.reply_text(text)
    last_msg_id = sent.message_id
    return await show_edited_template(update, context, sent)


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
    import json

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
    global last_msg_id
    last_msg_id = query.message.message_id

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
    global last_msg_id
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
        if last_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=last_msg_id
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
    if last_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=last_msg_id,
                text=prompt_text,
            )
            return EDIT_EXERCISE_DETAILS
        except Exception:
            pass

    sent = await update.message.reply_text(prompt_text)
    last_msg_id = sent.message_id
    return EDIT_EXERCISE_DETAILS


async def edit_exercise_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_msg_id
    text = update.message.text.strip()

    if text.lower() == "/skip":
        return await show_edited_template(update, context, None)

    parts = text.strip().split()

    if len(parts) < 2:
        sent = await update.message.reply_text(
            "Invalid format. Use: '3 60x5 65x4 70x3'\n"
            "Format: <num_sets> <weight>x<reps> <weight>x<reps> ..."
        )
        last_msg_id = sent.message_id
        return EDIT_EXERCISE_DETAILS

    try:
        num_sets = int(parts[0])
        if num_sets <= 0:
            raise ValueError("Sets must be positive")
    except ValueError:
        sent = await update.message.reply_text(
            "First value must be number of sets (e.g., '3')."
        )
        last_msg_id = sent.message_id
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
                if last_msg_id:
                    await context.bot.delete_message(
                        chat_id=update.message.chat_id, message_id=last_msg_id
                    )
            except Exception as e:
                print(f"Could not delete: {e}")
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=update.message.message_id
                )
            except Exception as e:
                print(f"Could not delete user message: {e}")
            last_msg_id = sent.message_id
            return EDIT_EXERCISE_DETAILS

    if len(sets_config) != num_sets:
        sent = await update.message.reply_text(
            f"Mismatch: You said {num_sets} sets but provided {len(sets_config)} weight x reps values."
        )
        try:
            if last_msg_id:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=last_msg_id
                )
        except Exception as e:
            print(f"Could not delete: {e}")
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=update.message.message_id
            )
        except Exception as e:
            print(f"Could not delete user message: {e}")
        last_msg_id = sent.message_id
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

    try:
        if last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    last_msg_id = update.message.message_id
    return await show_edited_template(update, context, update.message)


async def edit_template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template renaming."""
    global last_msg_id
    context.user_data["editing_template_name"] = update.message.text.strip()
    try:
        if last_msg_id:
            # Will be edited by show_edited_template
            pass
    except Exception as e:
        print(f"Could not delete: {e}")
    return await show_edited_template(update, context, None)


async def show_edited_template(update, context, message=None):
    """Show the current state of the edited template by editing a message."""
    global last_msg_id
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

    if last_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=last_msg_id,
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
    last_msg_id = sent.message_id
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
        global last_msg_id
        last_msg_id = sent.message_id

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
    except Exception as e:
        logger.error(f"Error saving template: {e}")
        await query.message.reply_text("Error saving template. Please try again.")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel template editing."""
    global last_msg_id
    context.user_data.clear()
    sent = await update.message.reply_text("Template editing canceled.")
    try:
        if last_msg_id:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=last_msg_id
            )
    except Exception as e:
        print(f"Could not delete: {e}")
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id, message_id=update.message.message_id
        )
    except Exception as e:
        print(f"Could not delete user message: {e}")
    last_msg_id = sent.message_id
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
            await query.edit_message_text("No template selected for deletion.")

        context.user_data.clear()
        return ConversationHandler.END

    return DELETE_TEMPLATE_CONFIRM


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
