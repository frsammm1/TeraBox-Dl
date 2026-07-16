import os
import re
import json
import logging
import asyncio
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import Message
from curl_cffi.requests import AsyncSession
from urllib.parse import urlparse
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot
app = Client(
    "terabox_bot",
    in_memory=True,
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

def extract_surl(url: str):
    parsed = urlparse(url)
    if "surl=" in parsed.query:
        return parsed.query.split("surl=")[1].split("&")[0]

    match = re.search(r'/s/([a-zA-Z0-9_-]+)', parsed.path)
    if match:
        return match.group(1)
    return None

async def get_terabox_data(surl: str):
    try:
        short_url = surl[1:] if surl.startswith("1") else surl

        session = AsyncSession(impersonate="chrome110")
        cookies = {"ndus": config.NDUS_COOKIE}
        session.cookies.update(cookies)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
        }

        first_url = f"https://dm.terabox.app/sharing/link?surl={surl}"
        response = await session.get(first_url, headers=headers)

        match = re.search(r'fn%28%22(.*?)%22%29', response.text)
        if not match:
            return None, "Failed to extract jsToken"

        jsToken = match.group(1)
        api_url = "https://dm.terabox.app/share/list"

        params = {
            "app_id": "250528",
            "jsToken": jsToken,
            "site_referer": "https://www.terabox.app/",
            "shorturl": short_url,
            "root": "1"
        }

        api_headers = {
            "Host": "dm.terabox.app",
            "User-Agent": headers["User-Agent"],
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://dm.terabox.app/sharing/link?surl={short_url}&clearCache=1",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://dm.terabox.app"
        }

        api_response = await session.get(api_url, params=params, headers=api_headers)
        data = api_response.json()
        return data, None
    except Exception as e:
        logger.error(f"Error fetching terabox data: {e}")
        return None, str(e)


@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    await message.reply_text("Hello! Send me a Terabox link and I will download it for you.")

@app.on_message(filters.text & filters.regex(r"https?://[^\s]+"))
async def handle_link(client: Client, message: Message):
    url = message.text.strip()

    # Check if it's a valid terabox domain
    allowed_domains = ["terabox.app", "teraboxshare.com", "terabox.com", "1024terabox.com", "teraboxlink.com"]
    is_terabox = any(domain in url for domain in allowed_domains)

    if not is_terabox:
        return

    surl = extract_surl(url)
    if not surl:
        await message.reply_text("Invalid Terabox URL or couldn't extract the file ID.")
        return

    status_msg = await message.reply_text("Processing your link...")

    data, err = await get_terabox_data(surl)

    if err or not data:
        await status_msg.edit_text(f"Error fetching data: {err}")
        return

    if "list" not in data or not data["list"]:
        await status_msg.edit_text("No files found in this link.")
        return

    first_item = data["list"][0]
    filename = first_item.get("server_filename", "downloaded_file")
    dlink = first_item.get("dlink")

    if not dlink:
        await status_msg.edit_text("Could not find direct download link.")
        return

    await status_msg.edit_text(f"Downloading {filename}...")

    # Download the file
    try:
        session = AsyncSession(impersonate="chrome110")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36",
            "Cookie": f"ndus={config.NDUS_COOKIE}"
        }

        # Download locally asynchronously
        response = await session.get(dlink, headers=headers, stream=True)
        if response.status_code != 200:
            await status_msg.edit_text(f"Download failed with status code {response.status_code}")
            return

        # Ensure unique file name to avoid collisions
        unique_id = message.id
        file_path = f"downloads/{unique_id}_{filename}"
        os.makedirs("downloads", exist_ok=True)

        async with aiofiles.open(file_path, "wb") as f:
            async for chunk in response.aiter_content():
                if chunk:
                    await f.write(chunk)

        await status_msg.edit_text("Uploading to Telegram...")

        # Upload to Telegram
        if filename.endswith((".mp4", ".mkv", ".webm")):
            await message.reply_video(video=file_path, caption=filename)
        else:
            await message.reply_document(document=file_path, caption=filename)

        # Clean up
        os.remove(file_path)
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error during download/upload: {e}")
        await status_msg.edit_text(f"An error occurred: {e}")

if __name__ == "__main__":
    logger.info("Starting bot...")
    app.run()
