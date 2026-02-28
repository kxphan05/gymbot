"""Handlers package — re-exports all public symbols for backward compatibility."""

# --- Constants ---
from handlers.common import (
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
    SETTINGS_REST,
    SETTINGS_REST_CONFIRM,
    WEIGHT_KEYBOARD,
    REPS_KEYBOARD,
    get_client,
    logger,
)

# --- Start ---
from handlers.start import start

# --- Settings ---
from handlers.settings import settings, settings_rest, settings_rest_confirm

# --- AI Template ---
from handlers.ai_template import (
    add_template_ai_start,
    process_ai_template,
    process_ai_template_file,
)

# --- Template CRUD ---
from handlers.template import (
    create_template_start,
    template_name,
    exercise_name,
    exercise_details,
    save_template,
    cancel,
    done_handler,
    edit_template_start,
    select_template_to_edit,
    handle_edit_exercise_action,
    edit_exercise_name,
    edit_exercise_details,
    edit_template_name,
    show_edited_template,
    build_template_set_keyboard,
    show_template_exercise_sets,
    save_edited_template,
    cancel_edit,
    confirm_delete_template,
    handle_delete_template_confirm,
    handle_template_weight_select,
    handle_template_reps_select,
    handle_template_set_finish,
)

# --- Workout ---
from handlers.workout import (
    start_workout,
    select_template,
    select_exercise,
    build_set_keyboard,
    process_next_exercise,
    handle_exercise_action,
    handle_weight_select,
    handle_reps_select,
    end_workout_callback,
    log_exercise,
    rest_timer_callback,
)

# --- History ---
from handlers.history import (
    history,
    history_detail_callback,
    history_back_callback,
)
