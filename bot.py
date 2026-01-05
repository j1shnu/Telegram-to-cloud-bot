import os
import time
import utils
import config
import logging
from urllib.parse import urlparse
from pyrogram.types import Message
from pyrogram import Client, filters

import aria2p
import asyncio

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

# Initialize Aria2
# Fixed to Use localhost/port directly since config URL parsing might be brittle with aria2p

parsed_url = urlparse(config.ARIA2_RPC_URL)

aria2 = aria2p.API(
    aria2p.Client(
        host=f"{parsed_url.scheme}://{parsed_url.hostname}",
        port=parsed_url.port or 6800,
        secret=config.ARIA2_RPC_SECRET
    )
)

# Auth Filter
async def is_admin(_, __, message: Message):
    if not config.ADMIN_IDS:
        return True # If no admins defined, allow everyone (or change to False for security)
    return message.from_user.id in config.ADMIN_IDS

admin_filter = filters.create(is_admin)

@app.on_message(filters.command("torr") & admin_filter)
async def torr_command(client, message):
    if not message.reply_to_message:
        await message.reply_text("Please reply to a message containing the magnet link.")
        return

    magnet_link = message.reply_to_message.text or message.reply_to_message.caption
    
    if not magnet_link:
       await message.reply_text("No text found in the replied message.")
       return

    # Basic check for magnet link
    if not magnet_link.strip().startswith("magnet:?"):
        await message.reply_text("That doesn't look like a magnet link.")
        return

    status_msg = await message.reply_text("Adding to queue...")

    try:
        # Add to aria2 with specific download dir (internal to container)
        download = await asyncio.to_thread(
            aria2.add_magnet, 
            magnet_link, 
            {"dir": "/downloads"}
        )
    except Exception as e:
        await status_msg.edit_text(f"Error adding to aria2: {e}")
        return

    gid = download.gid
    previous_msg = ""
    
    while True:
        try:
            download = await asyncio.to_thread(aria2.get_download, gid)
            status = download.status
            
            # Handle Metadata -> Real Download transition
            if status == "complete" and download.followed_by:
                await status_msg.edit_text("Metadata acquired. Switching to file download...")
                new_gid = download.followed_by[0]
                logger.info(f"Metadata switch: raw new_gid type={type(new_gid)}")
                
                # STRICT extraction of GID string
                if isinstance(new_gid, str):
                    gid = new_gid
                elif hasattr(new_gid, 'gid'):
                    gid = str(new_gid.gid)
                else:
                    gid = str(new_gid)
                
                # Double check: Ensure it is a pure string
                if not isinstance(gid, str):
                    logger.error(f"CRITICAL: gid is after conversion is {type(gid)}")
                    gid = str(gid)

                logger.info(f"Metadata switch: FINAL Resolved gid='{gid}' (type={type(gid)})")
                    
                # Force refresh of variable for next loop
                continue

            if status == "active":
                update_text = (
                    f"Downloading: `{download.name}`\n"
                    f"Progress: {download.progress_string()}\n"
                    f"Speed: {download.download_speed_string()}\n"
                    f"ETA: {download.eta_string()}"
                )
                
                # Rate limit updates slightly/check for changes
                if update_text != previous_msg:
                    try:
                        await status_msg.edit_text(update_text)
                        previous_msg = update_text
                    except:
                        pass
            
            elif status == "complete":
                await status_msg.edit_text(f"Download Complete: `{download.name}`")
                
                # Optional: Force verify file existence in mapped dir
                # Filename might be slightly different on disk, but generally matches download.name
                # Note: utils.get_files checks config.UPLOAD_DIR which is mapped to local ./downloads
                break
                
            elif status == "error":
                await status_msg.edit_text(f"Download Error: {download.error_message}")
                break
            
            elif status == "removed":
                await status_msg.edit_text("Download Removed from Aria2.")
                break
            
            await asyncio.sleep(3)
        
        except asyncio.CancelledError:
            logger.info("Task Cancelled. Exiting loop.")
            raise
        except Exception as e:
            logger.error(f"Polling error details: {e}, GID type: {type(gid)}")
            await asyncio.sleep(3)

@app.on_message(filters.command("kill") & admin_filter)
async def kill_bot(client, message):
    await message.reply_text("Stopping bot...")
    os._exit(0) # Force exit to ensure process death

# Global cache for torrent list index -> GID
TORRENT_LIST_CACHE = {}

# Helper to update cache and get list
async def get_torrent_list_text():
    try:
        downloads = await asyncio.to_thread(aria2.get_downloads)
        
        if not downloads:
            TORRENT_LIST_CACHE.clear()
            return "No active or pending downloads."
            
        response_lines = ["**Active Downloads:**"]
        TORRENT_LIST_CACHE.clear()
        
        for i, download in enumerate(downloads, 1):
            TORRENT_LIST_CACHE[i] = download.gid
            name = download.name or "Metadata"
            status = download.status
            progress = download.progress_string()
            speed = download.download_speed_string()
            
            line = f"{i}. `{name}` [{status}] - {progress} ({speed})"
            response_lines.append(line)
            
        return "\n".join(response_lines)
    except Exception as e:
        return f"Error fetching downloads: {e}"

@app.on_message(filters.command("lstorr") & admin_filter)
async def list_torrents(client, message):
    text = await get_torrent_list_text()
    await message.reply_text(text)

@app.on_message(filters.command("stoptorr") & admin_filter)
async def stop_torrent(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /stoptorr <index>")
        return
        
    try:
        index = int(message.command[1])
        gid = TORRENT_LIST_CACHE.get(index)
        
        if not gid:
            await message.reply_text("Invalid index. Please run /lstorr first.")
            return
            
        await asyncio.to_thread(aria2.client.pause, gid)
        await message.reply_text(f"Paused torrent #{index}")
        
    except ValueError:
        await message.reply_text("Invalid index format.")
    except Exception as e:
        await message.reply_text(f"Error stopping torrent: {e}")

@app.on_message(filters.command("deltorr") & admin_filter)
async def delete_torrent(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /deltorr <index>")
        return
        
    try:
        index = int(message.command[1])
        gid = TORRENT_LIST_CACHE.get(index)
        
        if not gid:
            await message.reply_text("Invalid index. Please run /lstorr first.")
            return
            
        # Try to remove. If it fails (e.g. already complete), try removing the result.
        try:
            await asyncio.to_thread(aria2.client.force_remove, gid)
            await message.reply_text(f"Removed active torrent #{index}")
        except Exception as e:
            if "Active Download not found" in str(e):
                # Likely complete or error, try removing result
                await asyncio.to_thread(aria2.client.remove_download_result, gid)
                await message.reply_text(f"Removed completed/stopped torrent #{index}")
            else:
                raise e
        
        # Show updated list
        text = await get_torrent_list_text()
        await message.reply_text(text)
        
    except ValueError:
        await message.reply_text("Invalid index format.")
    except Exception as e:
        await message.reply_text(f"Error removing torrent: {e}")

@app.on_message(filters.command("start") & admin_filter)
async def start(client, message):
    await message.reply_text(
        "Welcome to **Telegram File Manager Bot!**\n"
        "__I can handle file uploads and torrent downloads.\n\n__"
        "**Commands:**\n"
        "/start - Start the bot\n"
        "/upload - Upload file (reply to file)\n"
        "/ls - List files\n"
        "/del <filename> - Delete file\n"
        "\n**Torrent Commands:**\n"
        "/torr - Download torrent (reply to magnet)\n"
        "/lstorr - List torrents\n"
        "/stoptorr <index> - Stop torrent\n"
        "/deltorr <index> - Delete torrent\n"
        "/kill - Force stop bot\n"
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
        await message.reply_text("Usage: /del filename")
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
