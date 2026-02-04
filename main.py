import os
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
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
)
from database import init_db
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


def main():
    if not TOKEN:
        print("Error: BOT_TOKEN environment variable not set.")
        return

    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

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
                CallbackQueryHandler(select_template, pattern="^tmpl_")
            ],
            WORKOUT_EXERCISE_SELECT: [
                CallbackQueryHandler(select_exercise, pattern="^ex_")
            ],
            WORKOUT_EXERCISE_CONFIRM: [CallbackQueryHandler(handle_exercise_action)],
            WORKOUT_EXERCISE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_exercise)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(create_template_conv)
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
            pattern="^(confirm|rest|skip|log_set_|edit_set_|complete_|w_|r_)",
        )
    )

    application.run_polling()


async def post_init(application):
    await init_db()


if __name__ == "__main__":
    main()
