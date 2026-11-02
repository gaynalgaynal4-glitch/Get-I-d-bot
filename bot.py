import os
import threading
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, session, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ.get("BOT_TOKEN")
CHANNEL_ID   = os.environ.get("CHANNEL_ID", "@jv_60fps")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/jv_60fps")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "0"))
ADMIN_PASS   = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY   = os.environ.get("SECRET_KEY", "jvsecret999")
PORT         = int(os.environ.get("PORT", 8080))

bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True)
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Allow only the JV-60FPS Netlify site to call the verification API.
# This does not change the bot logic or Telegram handlers.
CORS(app, resources={r"/verify/*": {"origins": "https://jv60fps.netlify.app"}})
CORS(app, resources={r"/verify/*": {"origins": "https://colab.research.google.com/drive/1SL_ellKIYUot7-GEUVzp2-dNzJNi9SK1?authuser=3#scrollTo=pewapDBngJsV"}})

# ── Database ─────────────────────────────────────────────────────────────────
db = {
    "users": {},        # uid → info
    "blocked": set(),   # blocked uids (strings)
    "broadcast_log": [],
    "stats": {
        "total_starts": 0,
        "total_verifications": 0,
        "total_denied": 0,
        "total_verify_calls": 0,
    }
}

def save_user(user, verified=False):
    uid = str(user.id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "id": user.id,
            "name": user.first_name + (" " + (user.last_name or "") if user.last_name else ""),
            "username": user.username or "N/A",
            "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "verified": False,
            "active_token": None,
            "api_calls": 0,
            "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    if verified:
        db["users"][uid]["verified"] = True
        db["users"][uid]["api_calls"] += 1
        db["users"][uid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")


# ── KEY API ENDPOINT — Extension calls this ───────────────────────────────────
@app.route("/verify/<uid>/<browser_token>")
def verify_user(uid, browser_token):
    db["stats"]["total_verify_calls"] += 1

    if uid in db["blocked"]:
        return jsonify({"allowed": False, "reason": "blocked"})

    try:
        m = bot.get_chat_member(CHANNEL_ID, int(uid))
        is_member = m.status in ["member", "administrator", "creator"]
    except:
        return jsonify({"allowed": False, "reason": "bot_error"})

    if not is_member:
        return jsonify({"allowed": False, "reason": "not_member"})

    user_data = db["users"].get(uid)
    stored_token = user_data["active_token"] if user_data else None

    if stored_token is None:
        if uid not in db["users"]:
            save_user(m.user)
        db["users"][uid]["active_token"] = browser_token
    elif stored_token != browser_token:
        return jsonify({"allowed": False, "reason": "session_taken"})

    try:
        user = m.user
        save_user(user, verified=True)
        db["stats"]["total_verifications"] += 1
        username = "@" + user.username if user.username else user.first_name
        photo_url = None
        try:
            photos = bot.get_user_profile_photos(int(uid), limit=1)
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id
                file_info = bot.get_file(file_id)
                photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        except:
            pass
        return jsonify({"allowed": True, "username": username, "first_name": user.first_name or "", "photo_url": photo_url})
    except:
        return jsonify({"allowed": True, "username": "User"})


# ── Helper: Main Menu Keyboard ────────────────────────────────────────────────
def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔑 Get ID", callback_data="get_api"))
    kb.add(InlineKeyboardButton("🔄 Reset Extension", callback_data="reset_key"))
    kb.row(
        InlineKeyboardButton("🩹 Patcher", url="https://restless-star-a7e9.gaynalgaynal4.workers.dev/"),
        InlineKeyboardButton("🌐 Website", url="https://frosty-paper-10d1.gaynalgaynal4.workers.dev/")
    )
    kb.add(InlineKeyboardButton("⚡ SAFE METHOD ", url="https://jv60fps.netlify.app/"))
    kb.add(InlineKeyboardButton("🔐 ALL Google colabe passwords", callback_data="show_password"))
    return kb


# ── Telegram Bot Handlers ─────────────────────────────────────────────────────
def is_member(uid):
    try:
        m = bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in ["member", "administrator", "creator"]
    except:
        return False

@bot.message_handler(commands=["start", "help"])
def start(m):
    db["stats"]["total_starts"] += 1
    save_user(m.from_user)
    if str(m.from_user.id) in db["blocked"]:
        bot.send_message(m.chat.id, "🚫 You have been blocked from using this service.")
        return
    bot.send_message(
        m.chat.id,
        f"👋 Welcome *{m.from_user.first_name}*!\n\n"
        "1️⃣ Join channel\n2️⃣ Click Get ID\n3️⃣ Paste in extension\n\n"
        "⚠️ Key stops if you leave!",
        parse_mode="Markdown", reply_markup=main_menu_kb()
    )

@bot.callback_query_handler(func=lambda c: c.data == "get_api")
def button(c):
    uid = c.from_user.id
    bot.answer_callback_query(c.id)
    if str(uid) in db["blocked"]:
        bot.answer_callback_query(c.id, "🚫 You are blocked.", show_alert=True)
        return
    kb = InlineKeyboardMarkup()
    if is_member(uid):
        save_user(c.from_user, verified=True)
        kb.add(InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
        bot.edit_message_text(
            f"✅ *Verified!*\n\n🔑 *Your ID:*\n`{uid}`\n\nPaste in extension!",
            c.message.chat.id, c.message.message_id,
            parse_mode="Markdown", reply_markup=kb
        )
    else:
        db["stats"]["total_denied"] += 1
        kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("🔄 Try Again", callback_data="get_api"))
        kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
        bot.edit_message_text(
            "❌ *Access Denied!*\n\nJoin our channel first!",
            c.message.chat.id, c.message.message_id,
            parse_mode="Markdown", reply_markup=kb
        )

@bot.callback_query_handler(func=lambda c: c.data == "reset_key")
def reset_key(c):
    uid = str(c.from_user.id)
    bot.answer_callback_query(c.id)
    if uid in db["blocked"]:
        bot.answer_callback_query(c.id, "🚫 You are blocked.", show_alert=True)
        return
    if uid in db["users"]:
        db["users"][uid]["active_token"] = None
        db["users"][uid]["verified"] = False
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔑 Get ID", callback_data="get_api"))
    kb.add(InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "🔄 *Reset Extension!*\n\n"
        "✅ You can use the extension now.\n"
        "Click below to claim the key on your new browser.",
        c.message.chat.id, c.message.message_id,
        parse_mode="Markdown", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "show_password")
def show_password(c):
    bot.answer_callback_query(c.id)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "🔐 *ALL Google colabe password*\n\n"
        "`7082829394`\n\n"
        "Copy and paste it in google colabe",
        c.message.chat.id, c.message.message_id,
        parse_mode="Markdown", reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def back_to_menu(c):
    bot.answer_callback_query(c.id)
    bot.edit_message_text(
        f"👋 Welcome *{c.from_user.first_name}*!\n\n"
        "1️⃣ Join channel\n2️⃣ Click Get ID\n3️⃣ Paste in extension\n\n"
        "⚠️ Key stops if you leave!",
        c.message.chat.id, c.message.message_id,
        parse_mode="Markdown", reply_markup=main_menu_kb()
    )

@bot.message_handler(commands=["stats"])
def tg_stats(m):
    if m.from_user.id != ADMIN_ID:
        return
    s = db["stats"]
    bot.send_message(
        m.chat.id,
        f"📊 *Bot Stats*\n\n"
        f"👥 Total Users: `{len(db['users'])}`\n"
        f"✅ Verifications: `{s['total_verifications']}`\n"
        f"🔍 Verify API Calls: `{s['total_verify_calls']}`\n"
        f"❌ Denied: `{s['total_denied']}`\n"
        f"🚫 Blocked: `{len(db['blocked'])}`",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["broadcast"])
def tg_broadcast(m):
    if m.from_user.id != ADMIN_ID:
        return
    text = m.text.replace("/broadcast", "").strip()
    if not text:
        bot.send_message(m.chat.id, "Usage: /broadcast <message>")
        return
    sent = 0
    for uid in db["users"]:
        try:
            bot.send_message(int(uid), f"📢 *Announcement*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except:
            pass
    db["broadcast_log"].append({"text": text, "sent_to": sent, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
    bot.send_message(m.chat.id, f"✅ Broadcast sent to {sent} users.")


# ── Flask health check ────────────────────────────────────────────────────────
@app.route('/')
def home():
    return "Bot is running!"


# ── Run ───────────────────────────────────────────────────────────────────────
def run_bot():
    bot.remove_webhook()
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
