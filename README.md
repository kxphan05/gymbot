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

### Docker Setup

1.  **Configure the bot**:
    Copy the example environment file and edit it with your credentials.
    ```bash
    cp .env-example .env
    ```
    Open `.env` and paste your `BOT_TOKEN`.

2.  **Start PostgreSQL**:
    ```bash
    docker run -d --name gymbot-db-1 \
        -e POSTGRES_PASSWORD=password \
        -e POSTGRES_DB=gymbot \
        postgres:15
    ```

3.  **Build the bot**:
    ```bash
    docker build --no-cache -t gymbot .
    ```

4.  **Run the bot** (connected to PostgreSQL network):
    ```bash
    docker run -d --name gymbot --network container:gymbot-db-1 gymbot
    ```

The bot should now be online and responsive.

### Stopping and Restarting

**Stop the bot**:
```bash
docker stop gymbot
```

**Remove the bot container**:
```bash
docker rm gymbot
```

**Restart the bot** (after code changes):
```bash
docker build --no-cache -t gymbot . && docker run -d --name gymbot --network container:gymbot-db-1 gymbot
```

### Rebuilding Database
To wipe the database and start fresh:
```bash
docker stop gymbot-db-1 && docker rm gymbot-db-1
docker volume rm gymbot_postgres_data 2>/dev/null
docker run -d --name gymbot-db-1 -e POSTGRES_PASSWORD=password -e POSTGRES_DB=gymbot postgres:15
docker stop gymbot && docker rm gymbot
docker build --no-cache -t gymbot . && docker run -d --name gymbot --network container:gymbot-db-1 gymbot
```

## 🧪 Testing

Run the unit tests using `pytest`:
```bash
uv run pytest
```
