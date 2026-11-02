# 🤖 Telegram Bot with Admin Panel — Render Deploy Guide

## Features
- ✅ Channel membership verification
- 🔑 API key delivery via Telegram UID
- 📊 **Admin Panel** at `/admin` with:
  - Dashboard (stats overview)
  - Users table (block / unblock)
  - Broadcast to all users
  - Broadcast history log
- 📢 `/stats` and `/broadcast` Telegram commands for admin
- 🔄 Keep-alive web server (required for Render free tier)

---

## 🚀 Deploy on Render (Step-by-Step)

### 1. Push to GitHub
Upload this folder to a GitHub repo (public or private).

### 2. Create a new Web Service on Render
1. Go to https://dashboard.render.com
2. Click **New → Web Service**
3. Connect your GitHub repo
4. Fill in:
   - **Name**: `my-telegram-bot` (or anything)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Instance Type**: Free

### 3. Set Environment Variables
In Render → your service → **Environment**, add these:

| Key              | Value                          |
|------------------|--------------------------------|
| `BOT_TOKEN`      | Your bot token from @BotFather |
| `CHANNEL_ID`     | `@yourchannel` (with @)        |
| `CHANNEL_LINK`   | `https://t.me/yourchannel`     |
| `ADMIN_ID`       | Your Telegram numeric user ID  |
| `ADMIN_PASSWORD` | A strong password for /admin   |
| `SECRET_KEY`     | A random secret string         |

> **How to get your ADMIN_ID?** Message @userinfobot on Telegram — it will send you your numeric ID.

### 4. Deploy
Click **Create Web Service**. Render will build and start your bot.

---

## 🔗 Access the Admin Panel
Once deployed, go to:
```
https://your-render-url.onrender.com/admin
```
Login with the `ADMIN_PASSWORD` you set.

---

## ⚠️ Keep-Alive (Free Tier)
Render's free tier spins down after 15 minutes of inactivity.
To keep it alive, use a free uptime monitor like:
- https://uptimerobot.com — monitor your `/health` endpoint every 5 minutes

Add URL: `https://your-render-url.onrender.com/health`

---

## Telegram Admin Commands
| Command | Description |
|---------|-------------|
| `/stats` | View bot statistics |
| `/broadcast <message>` | Send message to all users |

These only work for the Telegram account whose ID is set as `ADMIN_ID`.
