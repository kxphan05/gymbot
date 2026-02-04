# GymBot - Telegram Workout Tracker

GymBot is an asynchronous Telegram bot designed to help users track their workouts, manage templates, and visualize their progress.

## 🏗 Architecture

The project is built with a modern Python stack and containerized for easy deployment.

### Tech Stack
-   **Language**: Python 3.11+
-   **Framework**: [python-telegram-bot](https://python-telegram-bot.org/) (v20+ Async)
-   **Database**: PostgreSQL 15
-   **ORM**: SQLAlchemy (Async / `asyncpg`)
-   **Package Manager**: [uv](https://github.com/astral-sh/uv)
-   **Infrastructure**: Docker & Docker Compose

### Database Schema
-   **Users**: Stores Telegram user ID and username.
-   **Templates**: Workout routines (e.g., "Leg Day") linked to a user.
-   **TemplateExercises**: Exercises within a template (includes default weight/reps).
-   **WorkoutLogs**: History of performed exercises with actual weight, reps, and timestamp.

### Project Structure
```
gymbot/
├── main.py             # Application entry point
├── handlers.py         # Bot commands and conversation logic
├── database.py         # Database models and session management
├── Dockerfile          # Python application container
├── docker-compose.yml  # Orchestration for Bot + PostgreSQL
├── pyproject.toml      # Dependency definitions
└── uv.lock             # Locked dependencies
```

## 🚀 Getting Started

### Prerequisites
-   Docker installed.
-   A Telegram Bot Token (get one from [@BotFather](https://t.me/BotFather)).

### Installation

1.  **Configure the bot**:
    Copy the example environment file and edit it with your credentials.
    ```bash
    cp .env-example .env
    ```
    Open `.env` and paste your `BOT_TOKEN`.

2.  **Start everything with Docker Compose**:
    ```bash
    docker compose up --build -d
    ```

That's it! The bot will automatically start once the database is healthy.

### Managing the Bot

**View logs**:
```bash
docker compose logs -f
```

**Stop the bot**:
```bash
docker compose down
```

**Restart after code changes**:
```bash
docker compose up --build -d
```

**Reset the database** (deletes all data):
```bash
docker compose down -v
docker compose up --build -d
```

## 🧪 Testing

Run the unit tests using `pytest`:
```bash
uv run pytest
```
