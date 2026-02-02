# WebUpdateBot

A simple Telegram bot that monitors a webpage for updates and sends notifications.

## Features
- Monitors a specific URL for changes.
- Sends Telegram notifications upon detection.
- Auto-configures Telegram Chat ID so you don't have to find it manually.

## Prerequisites
- **Python 3.12+**
- **uv** (recommended for dependency management)

## Setup

1.  **Clone the repository** (if you haven't already).

2.  **Environment Configuration**
    Copy the example environment file:
    ```bash
    cp .env.example .env
    ```

    Open `.env` and add your **Telegram Bot Token** (from BotFather):
    ```ini
    TELEGRAM_BOT_TOKEN=your_token_here
    ```
    *Note: You do NOT need to set `TELEGRAM_CHAT_ID` manually. The bot will configure it for you.*

3.  **Install Dependencies**
    ```bash
    uv sync
    ```

## Usage

Run the bot:
```bash
uv run python bot.py
```

### First Run Configuration
If you haven't set `TELEGRAM_CHAT_ID` in your `.env` file, the bot will pause and ask you to send a message to it on Telegram.
1.  Run the bot.
2.  Open your bot in Telegram.
3.  Send any message (e.g., "Hello").
4.  The bot will detect your Chat ID, save it to `.env`, and start monitoring.
