import os
import time
import utils
import config
import logging
from pyrogram.types import Message
from pyrogram import Client, filters

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Client
app = Client(
    "my_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# Auth Filter
async def is_admin(_, __, message: Message):
    if not config.ADMIN_IDS:
        return True # If no admins defined, allow everyone (or change to False for security)
    return message.from_user.id in config.ADMIN_IDS

admin_filter = filters.create(is_admin)

@app.on_message(filters.command("start") & admin_filter)
async def start(client, message):
    await message.reply_text(
        "Welcome to **Telegram File Manager Bot!**\n"
        "__Send me any file and reply `/upload` to upload it to the VPS.\n\n__"
        "Commands:\n"
        "/start - Start the bot\n"
        "/upload - Upload file\n"
        "/ls - List files\n"
        "/del <filename> - Delete file\n"
    )

@app.on_message(filters.command("ls") & admin_filter)
async def list_files(client, message):
    await utils.ensure_upload_dir(config.UPLOAD_DIR)
    files = await utils.get_files(config.UPLOAD_DIR)
    if not files:
        await message.reply_text("No files found.")
        return

    file_list_items = []
    for i, file in enumerate(files, 1):
        file_list_items.append(f"{i}. `{file}`")
    
    file_list = "\n".join(file_list_items)
    
    # Split if too long (Telegram limit is 4096 chars)
    if len(file_list) > 4000:
        file_list = file_list[:4000] + "\n... (truncated)"
    
    await message.reply_text(f"Files in `{config.UPLOAD_DIR}`:\n\n{file_list}")

@app.on_message(filters.command("del") & admin_filter)
async def delete_file(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /del <filename>")
        return
    
    filename = message.command[1]
    path = os.path.join(config.UPLOAD_DIR, filename)
    
    # Security check to prevent path traversal
    if not os.path.abspath(path).startswith(os.path.abspath(config.UPLOAD_DIR)):
        await message.reply_text("Invalid filename.")
        return

    if await utils.delete_file(path):
        await message.reply_text(f"Deleted `{filename}`")
    else:
        await message.reply_text(f"File not found: `{filename}`")


# Store last update time for progress
last_update_time = {}

@app.on_message(filters.command("upload") & admin_filter)
async def upload_command(client, message: Message):
    if not message.reply_to_message:
        await message.reply_text("Please reply to a file with /upload to upload it.")
        return

    media_msg = message.reply_to_message
    if not (media_msg.document or media_msg.video or media_msg.audio or media_msg.photo):
        await message.reply_text("The replied message does not contain a supported file.")
        return

    await utils.ensure_upload_dir(config.UPLOAD_DIR)
    
    status_msg = await message.reply_text("Downloading... 0%")
    
    try:
        # Determine file name
        if media_msg.document:
            file_name = media_msg.document.file_name
        elif media_msg.video:
            file_name = media_msg.video.file_name or "video.mp4"
        elif media_msg.audio:
            file_name = media_msg.audio.file_name or "audio.mp3"
        elif media_msg.photo:
            file_name = "photo.jpg" 
        else:
            file_name = "unknown_file"

        # Sanitize filename (basic)
        file_name = os.path.basename(file_name)

        save_path = os.path.join(config.UPLOAD_DIR, file_name)
        
        # Handle duplicates
        base, ext = os.path.splitext(file_name)
        counter = 1
        while os.path.exists(save_path):
            save_path = os.path.join(config.UPLOAD_DIR, f"{base}_{counter}{ext}")
            counter += 1
            
        logger.info(f"Attempting to save file to: {os.path.abspath(save_path)}")
        
        # Reset last update time for this message
        last_update_time[status_msg.id] = 0

        start_time = time.time()
        await media_msg.download(
            file_name=save_path,
            progress=progress_callback,
            progress_args=(status_msg,)
        )
        end_time = time.time()
        duration = end_time - start_time
        
        if os.path.exists(save_path):
            logger.info(f"File successfully saved to: {save_path}")
            await status_msg.edit_text(f"**Saved to:** `{save_path}` \n**Time taken:** __{duration:.2f} seconds__")
        else:
            logger.error(f"File not found after download at: {save_path}")
            await status_msg.edit_text(f"Error: File not found at {save_path} after download.")
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        await status_msg.edit_text(f"Upload failed: {str(e)}")
    finally:
        # Clean up memory
        if status_msg.id in last_update_time:
            del last_update_time[status_msg.id]

async def progress_callback(current, total, message):
    now = time.time()
    last_time = last_update_time.get(message.id, 0)
    
    # Update if 10 seconds passed or it's the very first update (to show immediate progress)
    if now - last_time >= 10 or last_time == 0:
        if total > 0:
            percent = current * 100 / total
            try:
                await message.edit_text(f"Downloading... {percent:.1f}%")
                last_update_time[message.id] = now
            except:
                pass

if __name__ == "__main__":
    print("Bot started...")
    app.run()
