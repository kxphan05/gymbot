"""AI Coach: personalized multi-template recommendation via CSCS-style LLM prompting."""

import json
import re
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from thefuzz import process as fuzz_process

from database import AsyncSessionLocal, Template, TemplateExercise
import handlers.common as common
from handlers.common import (
    logger,
    get_client,
    AI_COACH_BIO,
    AI_COACH_SBD,
    AI_COACH_SPLIT,
    AI_COACH_GOALS,
    AI_COACH_REVIEW,
    AI_COACH_REGEN_COMMENT,
)

VOLUME_GUARD_THRESHOLD = 8
FUZZY_MATCH_THRESHOLD = 70
MUSCLE_CORRECTION_THRESHOLD = 82  # higher bar — only override when very confident
AI_MODEL = "allenai/Molmo2-8B"

# Canonical exercise → primary muscle group lookup.
# Used to correct LLM hallucinations in muscle group assignments.
EXERCISE_MUSCLE_MAP: dict[str, str] = {
    # Chest
    "bench press": "chest", "barbell bench press": "chest",
    "dumbbell bench press": "chest", "incline bench press": "chest",
    "decline bench press": "chest", "incline dumbbell press": "chest",
    "decline dumbbell press": "chest", "chest fly": "chest",
    "dumbbell fly": "chest", "cable fly": "chest",
    "cable crossover": "chest", "push up": "chest", "pushup": "chest",
    "chest press": "chest", "pec deck": "chest",
    # Back
    "pull up": "back", "pullup": "back", "chin up": "back", "chinup": "back",
    "lat pulldown": "back", "barbell row": "back", "bent over row": "back",
    "dumbbell row": "back", "cable row": "back", "seated cable row": "back",
    "t-bar row": "back", "t bar row": "back", "deadlift": "back",
    "conventional deadlift": "back", "rack pull": "back",
    "single arm dumbbell row": "back", "meadows row": "back",
    # Shoulders
    "overhead press": "shoulders", "military press": "shoulders",
    "barbell overhead press": "shoulders", "dumbbell overhead press": "shoulders",
    "dumbbell shoulder press": "shoulders", "arnold press": "shoulders",
    "lateral raise": "shoulders", "dumbbell lateral raise": "shoulders",
    "cable lateral raise": "shoulders", "front raise": "shoulders",
    "rear delt fly": "shoulders", "rear delt raise": "shoulders",
    "reverse fly": "shoulders", "upright row": "shoulders",
    "face pull": "shoulders", "cable face pull": "shoulders",
    "landmine press": "shoulders",
    # Quads
    "squat": "quads", "back squat": "quads", "front squat": "quads",
    "goblet squat": "quads", "leg press": "quads", "leg extension": "quads",
    "hack squat": "quads", "bulgarian split squat": "quads",
    "split squat": "quads", "lunge": "quads", "lunges": "quads",
    "step up": "quads", "walking lunge": "quads", "reverse lunge": "quads",
    "sissy squat": "quads",
    # Hamstrings
    "romanian deadlift": "hamstrings", "rdl": "hamstrings",
    "leg curl": "hamstrings", "hamstring curl": "hamstrings",
    "lying leg curl": "hamstrings", "seated leg curl": "hamstrings",
    "nordic curl": "hamstrings", "good morning": "hamstrings",
    "stiff leg deadlift": "hamstrings", "straight leg deadlift": "hamstrings",
    "sumo deadlift": "hamstrings",
    # Glutes
    "hip thrust": "glutes", "barbell hip thrust": "glutes",
    "glute bridge": "glutes", "cable kickback": "glutes",
    "glute kickback": "glutes", "hip abduction": "glutes",
    "sumo squat": "glutes", "cable pull through": "glutes",
    # Biceps
    "bicep curl": "biceps", "biceps curl": "biceps",
    "barbell curl": "biceps", "dumbbell curl": "biceps",
    "hammer curl": "biceps", "preacher curl": "biceps",
    "cable curl": "biceps", "ez bar curl": "biceps",
    "incline curl": "biceps", "concentration curl": "biceps",
    "spider curl": "biceps",
    # Triceps
    "tricep extension": "triceps", "triceps extension": "triceps",
    "skull crusher": "triceps", "tricep pushdown": "triceps",
    "triceps pushdown": "triceps", "cable pushdown": "triceps",
    "close grip bench press": "triceps", "overhead tricep extension": "triceps",
    "tricep dips": "triceps", "tricep kickback": "triceps",
    "rope pushdown": "triceps",
    # Core
    "plank": "core", "crunch": "core", "sit up": "core", "situp": "core",
    "russian twist": "core", "ab wheel": "core", "leg raise": "core",
    "dead bug": "core", "cable crunch": "core", "hanging leg raise": "core",
    "hollow hold": "core",
    # Calves
    "calf raise": "calves", "standing calf raise": "calves",
    "seated calf raise": "calves", "donkey calf raise": "calves",
}

# Maps split key → ordered list of session names the LLM must generate
SPLIT_SESSIONS: dict[str, list[str]] = {
    "PPL":        ["Push Day", "Pull Day", "Legs Day"],
    "UpperLower": ["Upper Body", "Lower Body"],
    "FullBody":   ["Full Body"],
    "BroSplit":   ["Chest Day", "Back Day", "Shoulders Day", "Arms Day", "Legs Day"],
}

CSCS_SYSTEM_PROMPT = """\
You are a Certified Strength & Conditioning Specialist (CSCS) and expert program designer.
Your job is to design a complete training split — one template per session — based on the athlete profile.

You MUST respond with ONLY a valid JSON object. No explanation, no markdown, no text outside JSON.

JSON schema:
{
  "templates": [
    {
      "template_name": "string — concise name matching the requested session (e.g. 'PPL Push Day')",
      "notes": "string — 1 sentence rationale",
      "exercises": [
        {
          "name": "string — specific canonical name (e.g. 'Barbell Bench Press')",
          "muscle_group": "string — chest | back | shoulders | quads | hamstrings | glutes | biceps | triceps | core | calves",
          "sets": int,
          "sets_config": [{"weight": float, "reps": int}]
        }
      ]
    }
  ]
}

Programming rules:
- Generate exactly the sessions listed in the athlete's split — one object per session, in order.
- sets_config length MUST equal "sets" exactly.
- Base weights on the athlete's 1RM: ~70-80% for hypertrophy (6-12 reps), ~82-90% for strength (3-5 reps). Use beginner weights if 1RM is 0.
- Keep total sets per muscle group to 6-10 within each session.
- Do NOT repeat the same session type. Each template covers different muscle groups.
- muscle_group MUST reflect the PRIMARY mover of the exercise. Examples:
    Overhead Press → shoulders, Lateral Raise → shoulders, Front Raise → shoulders
    Squat / Leg Press / Leg Extension / Lunge → quads
    Romanian Deadlift / Leg Curl / Nordic Curl → hamstrings
    Hip Thrust / Glute Bridge → glutes
    Deadlift / Row / Pulldown / Pull Up → back
    Bench Press / Fly / Push Up → chest
    Curl (any) → biceps
    Pushdown / Skull Crusher / Tricep Extension → triceps
    Calf Raise → calves
    Plank / Crunch / Ab Wheel → core
- NEVER assign a muscle group that does not match the exercise (e.g. Overhead Press is NOT quads, Lateral Raise is NOT calves).
- Always assign a realistic weight > 0 unless the exercise is purely bodyweight with no added load.
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def ai_coach_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sent = await update.message.reply_text(
        "🤖 *AI Coach — Personalized Split*\n\n"
        "I'll design a full training split for you in 4 steps.\n\n"
        "*Step 1/4 — Bio*\n"
        "Enter your age, weight (kg), and height (cm) separated by spaces:\n"
        "Example: `25 80 180`",
        parse_mode="Markdown",
    )
    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id, message_id=common.last_msg_id
            )
        except Exception:
            pass
    common.last_msg_id = sent.message_id
    return AI_COACH_BIO


# ---------------------------------------------------------------------------
# Step 1: Bio
# ---------------------------------------------------------------------------


async def ai_coach_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nums = re.findall(r"[\d.]+", update.message.text)
    if len(nums) < 3:
        sent = await update.message.reply_text(
            "❌ Need three numbers: age, weight (kg), height (cm).\n"
            "Example: `25 80 180`",
            parse_mode="Markdown",
        )
        await _delete_user_msg(update)
        await _replace_last(context, update, sent)
        return AI_COACH_BIO

    try:
        age = int(float(nums[0]))
        weight = float(nums[1])
        height = float(nums[2])
    except ValueError:
        sent = await update.message.reply_text("❌ Could not parse numbers. Try again.")
        await _delete_user_msg(update)
        await _replace_last(context, update, sent)
        return AI_COACH_BIO

    context.user_data["coach_bio"] = {"age": age, "weight": weight, "height": height}
    await _delete_user_msg(update)

    sent = await update.message.reply_text(
        f"✅ *Bio saved:* {age} yrs, {weight} kg, {height} cm\n\n"
        "*Step 2/4 — Strength (SBD)*\n"
        "Enter your 1RM Bench, Squat, and Deadlift in kg separated by spaces:\n"
        "Example: `100 140 180`\n\n"
        "_(Enter 0 for any lift you want to skip)_",
        parse_mode="Markdown",
    )
    await _replace_last(context, update, sent)
    return AI_COACH_SBD


# ---------------------------------------------------------------------------
# Step 2: SBD maxes
# ---------------------------------------------------------------------------


async def ai_coach_sbd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nums = re.findall(r"[\d.]+", update.message.text)
    if len(nums) < 3:
        sent = await update.message.reply_text(
            "❌ Need three numbers: Bench, Squat, Deadlift (kg).\n"
            "Example: `100 140 180`",
            parse_mode="Markdown",
        )
        await _delete_user_msg(update)
        await _replace_last(context, update, sent)
        return AI_COACH_SBD

    try:
        bench = float(nums[0])
        squat = float(nums[1])
        deadlift = float(nums[2])
    except ValueError:
        sent = await update.message.reply_text("❌ Could not parse numbers. Try again.")
        await _delete_user_msg(update)
        await _replace_last(context, update, sent)
        return AI_COACH_SBD

    context.user_data["coach_sbd"] = {"bench": bench, "squat": squat, "deadlift": deadlift}
    await _delete_user_msg(update)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Push / Pull / Legs (PPL) — 3 templates", callback_data="split_PPL")],
        [InlineKeyboardButton("Upper / Lower — 2 templates", callback_data="split_UpperLower")],
        [InlineKeyboardButton("Full Body — 1 template", callback_data="split_FullBody")],
        [InlineKeyboardButton("Bro Split (body-part) — 5 templates", callback_data="split_BroSplit")],
    ])

    try:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=common.last_msg_id,
            text=(
                f"✅ *SBD saved:* Bench {bench} kg | Squat {squat} kg | Deadlift {deadlift} kg\n\n"
                "*Step 3/4 — Training Split*\n"
                "Select your preferred split:"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception:
        sent = await update.message.reply_text(
            "*Step 3/4 — Training Split*\nSelect your preferred split:",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        common.last_msg_id = sent.message_id

    return AI_COACH_SPLIT


# ---------------------------------------------------------------------------
# Step 3: Split selection (callback)
# ---------------------------------------------------------------------------


async def ai_coach_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    split = query.data.replace("split_", "")
    context.user_data["coach_split"] = split
    common.last_msg_id = query.message.message_id

    sessions = SPLIT_SESSIONS.get(split, ["Full Body"])
    session_list = ", ".join(sessions)

    await query.edit_message_text(
        f"✅ *Split selected:* {split} ({len(sessions)} session{'s' if len(sessions) > 1 else ''})\n"
        f"_Sessions: {session_list}_\n\n"
        "*Step 4/4 — Goals & Notes*\n"
        "Any specific goals or constraints for the AI coach?\n\n"
        "Examples: _'Focus on shoulders'_, _'Only 45 mins'_, _'No barbell'_\n\n"
        "_(Type `none` to skip)_",
        parse_mode="Markdown",
    )
    return AI_COACH_GOALS


# ---------------------------------------------------------------------------
# Step 4: Goals → trigger generation
# ---------------------------------------------------------------------------


async def ai_coach_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    goals = update.message.text.strip()
    if goals.lower() == "none":
        goals = "No specific goals or constraints."
    context.user_data["coach_goals"] = goals
    await _delete_user_msg(update)
    return await _generate_recommendation(update, context)


# ---------------------------------------------------------------------------
# AI generation
# ---------------------------------------------------------------------------


async def _generate_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Call the LLM for all sessions, apply volume guard + fuzzy match, show draft."""
    bio = context.user_data.get("coach_bio", {})
    sbd = context.user_data.get("coach_sbd", {})
    split = context.user_data.get("coach_split", "PPL")
    goals = context.user_data.get("coach_goals", "No specific goals.")

    sessions = SPLIT_SESSIONS.get(split, ["Full Body"])
    session_list = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sessions))

    try:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=common.last_msg_id,
            text=f"⚙️ Generating {len(sessions)} template{'s' if len(sessions) > 1 else ''} for *{split}*, please wait...",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    regen_comments: list[str] = context.user_data.get("coach_regen_comments", [])

    user_prompt = (
        f"Athlete Profile:\n"
        f"- Age: {bio.get('age')} years\n"
        f"- Weight: {bio.get('weight')} kg\n"
        f"- Height: {bio.get('height')} cm\n"
        f"- 1RM Bench Press: {sbd.get('bench')} kg\n"
        f"- 1RM Squat: {sbd.get('squat')} kg\n"
        f"- 1RM Deadlift: {sbd.get('deadlift')} kg\n"
        f"- Training Split: {split}\n"
        f"- Goals / Notes: {goals}\n"
    )
    if regen_comments:
        user_prompt += "\nRevision feedback to address (most recent last):\n"
        user_prompt += "\n".join(f"  {i+1}. {c}" for i, c in enumerate(regen_comments))
        user_prompt += "\n"
    user_prompt += (
        f"\nGenerate exactly {len(sessions)} workout session template(s) in this order:\n"
        f"{session_list}\n\n"
        f"Each session must target the appropriate muscle groups for its position in the {split} split."
    )

    try:
        ai_client = get_client()
        response = await ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": CSCS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=6000,
        )
        data = json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"AI Coach generation error: {e}")
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=common.last_msg_id,
                text="❌ Failed to generate templates. Try /recommend_template again or /cancel.",
            )
        except Exception:
            pass
        return ConversationHandler.END

    raw_templates = data.get("templates", [])

    # If the LLM returned a single-template format (no "templates" key), wrap it
    if not raw_templates and "exercises" in data:
        raw_templates = [data]

    canonical_names = await _fetch_canonical_names(update.effective_user.id)

    processed_templates = []
    for raw_tmpl in raw_templates:
        tmpl_name = raw_tmpl.get("template_name", "AI Coach Template")
        notes = raw_tmpl.get("notes", "")
        exercises = _process_exercises(raw_tmpl.get("exercises", []), canonical_names)
        volume_warnings = _check_volume(exercises)
        processed_templates.append({
            "template_name": tmpl_name,
            "notes": notes,
            "exercises": exercises,
            "volume_warnings": volume_warnings,
        })

    context.user_data["coach_templates"] = processed_templates

    draft_text = _build_draft_text(split, processed_templates)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"✅ Save {len(processed_templates)} Template{'s' if len(processed_templates) > 1 else ''}",
                callback_data="coach_save",
            ),
            InlineKeyboardButton("🔄 Regenerate", callback_data="coach_regen"),
        ]
    ])

    # Telegram message limit is 4096 chars; truncate gracefully if needed
    if len(draft_text) > 4000:
        draft_text = draft_text[:3970] + "\n\n_...truncated for display_"

    try:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=common.last_msg_id,
            text=draft_text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception:
        effective_message = update.message or update.callback_query.message
        sent = await effective_message.reply_text(
            draft_text, parse_mode="Markdown", reply_markup=keyboard
        )
        common.last_msg_id = sent.message_id

    return AI_COACH_REVIEW


# ---------------------------------------------------------------------------
# Review callbacks: Save / Regenerate
# ---------------------------------------------------------------------------


async def ai_coach_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    common.last_msg_id = query.message.message_id

    if query.data == "coach_regen":
        await query.edit_message_text(
            "💬 *Regeneration Feedback*\n\n"
            "Any adjustments for the next attempt?\n"
            "Example: _'too many leg exercises'_, _'less overall volume'_, _'add more chest work'_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭ Skip — regenerate as-is", callback_data="coach_regen_skip")],
            ]),
        )
        return AI_COACH_REGEN_COMMENT

    if query.data == "coach_save":
        return await _save_coach_templates(update, context)

    return AI_COACH_REVIEW


async def ai_coach_regen_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the regeneration feedback step — text comment or skip."""
    # Skip button pressed
    if update.callback_query:
        await update.callback_query.answer()
        common.last_msg_id = update.callback_query.message.message_id
        return await _generate_recommendation(update, context)

    # Text comment provided — accumulate across regenerations
    comment = update.message.text.strip()
    await _delete_user_msg(update)
    comments: list[str] = context.user_data.get("coach_regen_comments", [])
    comments.append(comment)
    context.user_data["coach_regen_comments"] = comments
    return await _generate_recommendation(update, context)


async def _save_coach_templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    templates = context.user_data.get("coach_templates", [])

    if not templates:
        await query.edit_message_text("❌ No templates to save.")
        context.user_data.clear()
        return ConversationHandler.END

    saved_names: list[str] = []
    duplicate_names: list[str] = []

    try:
        async with AsyncSessionLocal() as session:
            for tmpl in templates:
                name = tmpl["template_name"]
                exercises = tmpl["exercises"]

                template = Template(name=name, user_id=user_id)
                session.add(template)
                try:
                    await session.flush()
                except IntegrityError:
                    await session.rollback()
                    duplicate_names.append(name)
                    continue

                for idx, ex in enumerate(exercises):
                    sc = ex.get("sets_config", [])
                    session.add(TemplateExercise(
                        template_id=template.id,
                        exercise_name=ex["name"],
                        default_sets=ex["sets"],
                        default_weight=sc[0]["weight"] if sc else 0,
                        default_reps=sc[0]["reps"] if sc else 0,
                        sets_config=json.dumps(sc),
                        order=idx,
                    ))
                await session.flush()
                saved_names.append(name)

            await session.commit()
    except Exception as e:
        logger.error(f"Error saving AI coach templates: {e}")
        await query.edit_message_text("❌ Error saving templates. Please try again.")
        context.user_data.clear()
        return ConversationHandler.END

    lines = []
    if saved_names:
        lines.append(f"✅ *{len(saved_names)} template{'s' if len(saved_names) > 1 else ''} saved:*")
        for name in saved_names:
            lines.append(f"  • {name}")
    if duplicate_names:
        lines.append(f"\n⚠️ *Skipped (already exist):*")
        for name in duplicate_names:
            lines.append(f"  • {name}")
        lines.append("Rename existing ones via /edit\\_template and try again._")
    if saved_names:
        lines.append("\nUse /start_workout to start a session.")

    await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _correct_muscle_group(exercise_name: str, llm_group: str) -> tuple[str, bool]:
    """
    Return (corrected_muscle_group, was_corrected).
    Checks the exercise name against EXERCISE_MUSCLE_MAP via exact then fuzzy match.
    Only overrides the LLM when confidence is >= MUSCLE_CORRECTION_THRESHOLD.
    """
    name_lower = exercise_name.lower().strip()

    # Exact match first
    if name_lower in EXERCISE_MUSCLE_MAP:
        correct = EXERCISE_MUSCLE_MAP[name_lower]
        if correct != llm_group:
            return correct, True
        return llm_group, False

    # Fuzzy match against map keys
    result = fuzz_process.extractOne(name_lower, EXERCISE_MUSCLE_MAP.keys())
    if result:
        match, score = result
        if score >= MUSCLE_CORRECTION_THRESHOLD:
            correct = EXERCISE_MUSCLE_MAP[match]
            if correct != llm_group:
                logger.info(
                    f"Muscle group corrected: '{exercise_name}' "
                    f"LLM='{llm_group}' → '{correct}' (via '{match}', score {score})"
                )
                return correct, True

    return llm_group, False


def _process_exercises(raw_exercises: list[dict], canonical_names: list[str]) -> list[dict]:
    """Fuzzy-match names, correct muscle groups, and normalise sets_config length."""
    exercises = []
    for ex in raw_exercises:
        name = ex.get("name", "Unknown Exercise")

        # Fuzzy-match exercise name to user's existing canonical names
        if canonical_names:
            match, score = fuzz_process.extractOne(name, canonical_names)
            if score >= FUZZY_MATCH_THRESHOLD:
                logger.info(f"Name fuzzy match: '{name}' → '{match}' (score {score})")
                name = match

        llm_group = ex.get("muscle_group", "unknown").lower()
        muscle_group, _ = _correct_muscle_group(name, llm_group)

        sets_config = ex.get("sets_config", [])
        sets = ex.get("sets", len(sets_config))
        while len(sets_config) < sets:
            sets_config.append(sets_config[-1] if sets_config else {"weight": 0, "reps": 8})
        sets_config = sets_config[:sets]

        exercises.append({
            "name": name,
            "muscle_group": muscle_group,
            "sets": sets,
            "sets_config": sets_config,
        })
    return exercises


async def _fetch_canonical_names(user_id: int) -> list[str]:
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TemplateExercise.exercise_name)
                .join(Template, TemplateExercise.template_id == Template.id)
                .where(Template.user_id == user_id)
                .distinct()
            )
            return [row[0] for row in result.fetchall()]
    except Exception as e:
        logger.warning(f"Could not fetch canonical exercise names: {e}")
        return []


def _check_volume(exercises: list[dict]) -> dict[str, int]:
    volume: dict[str, int] = defaultdict(int)
    for ex in exercises:
        volume[ex.get("muscle_group", "unknown")] += ex.get("sets", 0)
    return {mg: s for mg, s in volume.items() if s > VOLUME_GUARD_THRESHOLD}


_SESSION_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def _build_draft_text(split: str, templates: list[dict]) -> str:
    lines = [f"📋 *Draft: {split} Split — {len(templates)} template{'s' if len(templates) > 1 else ''}*\n"]

    for i, tmpl in enumerate(templates):
        emoji = _SESSION_EMOJI[i] if i < len(_SESSION_EMOJI) else f"{i+1}."
        lines.append(f"{emoji} *{tmpl['template_name']}*")
        if tmpl.get("notes"):
            lines.append(f"_{tmpl['notes']}_")

        for ex in tmpl["exercises"]:
            sc = ex.get("sets_config", [])
            sets_str = ", ".join(f"{s['weight']}×{s['reps']}" for s in sc)
            lines.append(f"  • *{ex['name']}* _{ex['muscle_group']}_\n    {sets_str}")

        warnings = tmpl.get("volume_warnings", {})
        if warnings:
            lines.append(f"  ⚠️ High volume: " + ", ".join(
                f"{mg} ({s} sets)" for mg, s in warnings.items()
            ))

        lines.append("")  # blank line between templates

    return "\n".join(lines)


async def _delete_user_msg(update: Update):
    try:
        await update.message.delete()
    except Exception:
        pass


async def _replace_last(context, update, sent):
    if common.last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=common.last_msg_id
            )
        except Exception:
            pass
    common.last_msg_id = sent.message_id
