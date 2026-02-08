import os
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    JobQueue,
)
from handlers import (
    start,
    create_template_start,
    template_name,
    exercise_name,
    exercise_details,
    save_template,
    cancel,
    done_handler,
    start_workout,
    select_template,
    select_exercise,
    end_workout_callback,
    handle_exercise_action,
    log_exercise,
    history,
    history_detail_callback,
    history_back_callback,
    TEMPLATE_NAME,
    EXERCISE_NAME,
    EXERCISE_DETAILS,
    WORKOUT_TEMPLATE_SELECT,
    WORKOUT_EXERCISE_SELECT,
    WORKOUT_EXERCISE_CONFIRM,
    WORKOUT_EXERCISE_INPUT,
    edit_template_start,
    select_template_to_edit,
    handle_edit_exercise_action,
    edit_exercise_name,
    edit_exercise_details,
    edit_template_name,
    cancel_edit,
    EDIT_TEMPLATE_SELECT,
    EDIT_TEMPLATE_EXERCISE,
    EDIT_TEMPLATE_NAME,
    EDIT_EXERCISE_NAME,
    EDIT_EXERCISE_DETAILS,
)
from database import init_db
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


def main():
    if not TOKEN:
        print("Error: BOT_TOKEN environment variable not set.")
        return

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .job_queue(JobQueue())
        .build()
    )

    create_template_conv = ConversationHandler(
        entry_points=[CommandHandler("create_template", create_template_start)],
        states={
            TEMPLATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, template_name)
            ],
            EXERCISE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, exercise_name)
            ],
            EXERCISE_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, exercise_details)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("done", done_handler),
        ],
    )

    workout_conv = ConversationHandler(
        entry_points=[CommandHandler("start_workout", start_workout)],
        states={
            WORKOUT_TEMPLATE_SELECT: [
                CallbackQueryHandler(select_template, pattern="^tmpl_"),
                CallbackQueryHandler(end_workout_callback, pattern="^end_workout$"),
            ],
            WORKOUT_EXERCISE_SELECT: [
                CallbackQueryHandler(select_exercise, pattern="^ex_"),
                CallbackQueryHandler(end_workout_callback, pattern="^end_workout$"),
                CallbackQueryHandler(handle_exercise_action, pattern="^add_exercise$"),
            ],
            WORKOUT_EXERCISE_CONFIRM: [CallbackQueryHandler(handle_exercise_action)],
            WORKOUT_EXERCISE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_exercise),
                CallbackQueryHandler(handle_exercise_action),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    edit_template_conv = ConversationHandler(
        entry_points=[CommandHandler("edit_template", edit_template_start)],
        states={
            EDIT_TEMPLATE_SELECT: [
                CallbackQueryHandler(select_template_to_edit, pattern="^etmpl_"),
            ],
            EDIT_TEMPLATE_EXERCISE: [
                CallbackQueryHandler(handle_edit_exercise_action),
            ],
            EDIT_TEMPLATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_template_name),
            ],
            EDIT_EXERCISE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_exercise_name),
            ],
            EDIT_EXERCISE_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_exercise_details),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_edit)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(create_template_conv)
    application.add_handler(edit_template_conv)
    application.add_handler(workout_conv)

    application.add_handler(
        CallbackQueryHandler(history_detail_callback, pattern="^hist_")
    )
    application.add_handler(
        CallbackQueryHandler(history_back_callback, pattern="^hist_back")
    )
    application.add_handler(
        CallbackQueryHandler(
            handle_exercise_action,
            pattern="^(skip|rest|back_to_exercise|confirm|cancel_rest|w_|r_)",
        )
    )
    
    application.run_webhook(
        listen="0.0.0.0",
        port=8080,
        url_path=f"{TOKEN}",
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
        ip_address="66.241.124.249",
    )


async def post_init(application):
    await init_db()


if __name__ == "__main__":
    main()
