"""Shared state, constants, keyboards, and utility functions for all handlers."""

import logging
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from openai import AsyncOpenAI

# --- OpenAI Client Singleton ---

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


# --- Logging ---

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Shared Mutable State ---

last_msg_id = None
last_chat_id = None


# --- Conversation State Constants ---

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

SETTINGS_REST, SETTINGS_REST_CONFIRM = range(20, 22)

AI_COACH_BIO, AI_COACH_SBD, AI_COACH_SPLIT, AI_COACH_GOALS, AI_COACH_REVIEW, AI_COACH_REGEN_COMMENT = range(30, 36)

# --- Inline Keyboard Constants ---

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


# --- Utility Functions ---


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
