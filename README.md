<div align="center">

# ☁️ TeraBox Telegram Bot (Docker/Heroku)

A fast, lightweight, and efficient **TeraBox Telegram Bot** built with **Python** and **Pyrogram**. Easily bypass Terabox pages and fetch direct files directly to Telegram.

---
</div>

## ✨ Features

- 🚀 **Asynchronous Downloading**: Avoid blocking loops.
- 🐳 **Docker Ready**: Easy deployment using Docker seamlessly.
- ☁️ **Heroku Ready**: Uses `heroku.yml` to automatically build the worker process.

## 🛠️ Prerequisites

Set the following Environment Variables in Heroku dashboard:
- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `NDUS_COOKIE`

## 🚀 Docker Deployment

Want to deploy it with Docker? Easy:

```bash
# Build the Docker image
docker build -t terabox-dl-bot .

# Run the container (pass env vars)
docker run -e API_ID="..." -e API_HASH="..." -e BOT_TOKEN="..." -e NDUS_COOKIE="..." terabox-dl-bot
```
