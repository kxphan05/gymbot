"""Handlers for AI-powered template creation (text, photo, CSV)."""

import json
import io
import base64
import csv

from telegram import Update
from telegram.ext import ContextTypes
import handlers.common as common
from handlers.common import (
    logger,
    get_client,
    parse_reps,
    ADD_TEMPLATE_AI_INPUT,
    EDIT_TEMPLATE_EXERCISE,
)
from handlers.template import show_edited_template


async def add_template_ai_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the AI template creation flow."""
    await update.message.reply_text(
        "Please describe your workout template in natural language, or upload a file (CSV or photo).\n"
        "Example: 'Push Day: 3 sets of Bench Press 80kg for 5 reps, 3 sets of Overhead Press 40kg for 8 reps'\n\n"
        "You can also upload:\n"
        "• A CSV file with workout data\n"
        "• A photo of a workout plan (I'll read it with AI)"
    )
    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
        except Exception as e:
            print(f"Could not delete: {e}")
    common.last_msg_id = update.message.message_id
    return ADD_TEMPLATE_AI_INPUT


async def process_ai_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the natural language workout description using OpenAI."""
    user_input = update.message.text

    # Show typing action to user
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Send transient processing message
    processing_msg = await update.message.reply_text(
        "Got it! Analyzing your workout routine... ⏳"
    )
    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
        except Exception:
            pass
    common.last_msg_id = processing_msg.message_id

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
        if common.last_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=common.last_msg_id
                )
            except Exception:
                pass
        common.last_msg_id = sent.message_id

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
    # Show typing action
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    processing_msg = await update.message.reply_text("Processing your file... ⏳")
    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
        except Exception:
            pass
    common.last_msg_id = processing_msg.message_id

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


async def _process_parsed_workout(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict
):
    """Helper function to process parsed workout data from any source."""
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
    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
        except Exception:
            pass
    common.last_msg_id = sent.message_id

    # Pass the message object so show_edited_template can edit it
    return await show_edited_template(update, context, sent)
