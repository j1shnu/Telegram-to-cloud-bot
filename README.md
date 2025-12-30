# Telegram File Manager Bot

A simple Telegram bot to upload files to your VPS/cloud instances and manage them.

## Features
- **Upload**: Reply to any file (Photo, Video, Audio, Document) with `/upload` to save it to the server.
- **Management**: List (`/ls`) and delete (`/del`) files.
- **Progress**: Real-time download progress updates.
- **Security**: Restricted to admin users only.

## Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (for dependency management)
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- API ID and Hash (from [my.telegram.org](https://my.telegram.org))

## Setup

1.  **Clone the repository**
    ```bash
    git clone <your-repo-url>
    cd Telegram-to-cloud-bot
    ```

2.  **Configure Environment**
    Copy the example environment file (or create one):
    ```bash
    cp .env.example .env  # If you have an example, otherwise create .env
    ```
    
    Edit `.env` and fill in your details:
    ```env
    API_ID=12345
    API_HASH=your_api_hash
    BOT_TOKEN=your_bot_token
    UPLOAD_DIR=downloads
    ADMIN_IDS=123456789,987654321
    ```

3.  **Install Dependencies**
    ```bash
    uv sync
    ```

## Running the Bot

Run the bot using `uv`:
```bash
uv run bot.py
```

## Usage Commands

- **/start**: Check if the bot is running and you are authorized.
- **/ls**: List all files in the upload directory.
- **/del <filename>**: Delete a specific file.
- **Upload**: Send a file, then **reply** to it with `/upload`.
