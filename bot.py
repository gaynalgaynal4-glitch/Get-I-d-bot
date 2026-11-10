import os
import threading
from datetime import datetime
from io import BytesIO

from flask import (
    Flask,
    render_template_string,
    request,
    redirect,
    session,
    jsonify,
    send_file,
)
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ── Configuration ────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required.")

CHANNEL_ID = os.environ.get("CHANNEL_ID", "@jv_60fps")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/jv_60fps")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "change-this-password")
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Set a strong SECRET_KEY environment variable before deployment.")

PORT = int(os.environ.get("PORT", 8080))

bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True)
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Allow the website to call the verification API.
# Add other trusted origins through CORS_ORIGINS, comma-separated.
allowed_origins = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS", "https://jv-studio1.netlify.app"
    ).split(",")
    if origin.strip()
]
CORS(app, resources={r"/verify/*": {"origins": allowed_origins}})


# ── In-memory database ───────────────────────────────────────────────────────
db = {
    "users": {},        # uid -> user information
    "blocked": set(),   # blocked Telegram user IDs as strings
    "broadcast_log": [],
    "stats": {
        "total_starts": 0,
        "total_verifications": 0,
        "total_denied": 0,
        "total_verify_calls": 0,
    },
}


def save_user(user, verified=False):
    uid = str(user.id)

    if uid not in db["users"]:
        db["users"][uid] = {
            "id": user.id,
            "name": user.first_name
            + (" " + user.last_name if user.last_name else ""),
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


def is_active_member(uid):
    member = bot.get_chat_member(CHANNEL_ID, int(uid))
    return member.status in ("member", "administrator", "creator")


# ── Verification API ─────────────────────────────────────────────────────────
@app.route("/verify/<uid>/<browser_token>")
def verify_user(uid, browser_token):
    db["stats"]["total_verify_calls"] += 1

    if not uid.isdigit() or not browser_token:
        return jsonify({"allowed": False, "reason": "invalid_request"}), 400

    if uid in db["blocked"]:
        return jsonify({"allowed": False, "reason": "blocked"})

    try:
        member = bot.get_chat_member(CHANNEL_ID, int(uid))
        if member.status not in ("member", "administrator", "creator"):
            return jsonify({"allowed": False, "reason": "not_member"})
    except Exception:
        app.logger.exception("Telegram membership check failed for uid=%s", uid)
        return jsonify({"allowed": False, "reason": "bot_error"}), 502

    user_data = db["users"].get(uid)
    stored_token = user_data.get("active_token") if user_data else None

    if stored_token is None:
        if uid not in db["users"]:
            save_user(member.user)
        db["users"][uid]["active_token"] = browser_token
    elif stored_token != browser_token:
        return jsonify({"allowed": False, "reason": "session_taken"})

    try:
        user = member.user
        save_user(user, verified=True)
        db["stats"]["total_verifications"] += 1

        username = "@" + user.username if user.username else (user.first_name or "User")
        photo_url = None

        try:
            photos = bot.get_user_profile_photos(int(uid), limit=1)
            if photos.total_count > 0 and photos.photos:
                # The browser receives only our proxy URL, never the Telegram bot token.
                photo_url = (
                    request.url_root.rstrip("/")
                    + f"/profile-photo/{uid}/{browser_token}"
                )
        except Exception:
            app.logger.exception("Telegram profile photo lookup failed for uid=%s", uid)

        return jsonify({
            "allowed": True,
            "username": username,
            "first_name": user.first_name or "",
            "photo_url": photo_url,
        })

    except Exception:
        app.logger.exception("Verification response failed for uid=%s", uid)
        return jsonify({"allowed": True, "username": "User", "photo_url": None})


@app.route("/profile-photo/<uid>/<browser_token>")
def profile_photo(uid, browser_token):
    """Serve the verified user's Telegram photo without exposing BOT_TOKEN."""
    if not uid.isdigit() or not browser_token:
        return jsonify({"error": "invalid_request"}), 400

    user_data = db["users"].get(uid)
    if not user_data or user_data.get("active_token") != browser_token:
        return jsonify({"error": "unauthorized"}), 403

    if uid in db["blocked"]:
        return jsonify({"error": "blocked"}), 403

    try:
        member = bot.get_chat_member(CHANNEL_ID, int(uid))
        if member.status not in ("member", "administrator", "creator"):
            return jsonify({"error": "not_member"}), 403

        photos = bot.get_user_profile_photos(int(uid), limit=1)
        if not photos.total_count or not photos.photos:
            return jsonify({"error": "no_profile_photo"}), 404

        # Telegram returns photo sizes from small to large.
        largest_photo = max(
            photos.photos[0],
            key=lambda photo: photo.width * photo.height,
        )
        file_info = bot.get_file(largest_photo.file_id)
        image_bytes = bot.download_file(file_info.file_path)

        response = send_file(
            BytesIO(image_bytes),
            mimetype="image/jpeg",
            max_age=300,
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "private, max-age=300"
        return response

    except Exception:
        app.logger.exception("Telegram profile photo delivery failed for uid=%s", uid)
        return jsonify({"error": "photo_unavailable"}), 502


# ── Helper: Main Menu Keyboard ───────────────────────────────────────────────
def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔑 Get ID", callback_data="get_api"))
    kb.add(InlineKeyboardButton("🔄 Reset Extension", callback_data="reset_key"))
    kb.row(
        InlineKeyboardButton(
            "🩹 Patcher",
            url="https://restless-star-a7e9.gaynalgaynal4.workers.dev/",
        ),
        InlineKeyboardButton(
            "🌐 Website",
            url="https://frosty-paper-10d1.gaynalgaynal4.workers.dev/",
        ),
    )
    kb.add(InlineKeyboardButton("⚡ SAFE METHOD", url="https://jv60fps.netlify.app/"))
    kb.add(
        InlineKeyboardButton(
            "🔐 ALL Google colabe passwords",
            callback_data="show_password",
        )
    )
    return kb


# ── Telegram Bot Handlers ────────────────────────────────────────────────────
def is_member(uid):
    try:
        return is_active_member(uid)
    except Exception:
        app.logger.exception("Membership check failed for uid=%s", uid)
        return False


@bot.message_handler(commands=["start", "help"])
def start(message):
    db["stats"]["total_starts"] += 1
    save_user(message.from_user)

    if str(message.from_user.id) in db["blocked"]:
        bot.send_message(
            message.chat.id,
            "🚫 You have been blocked from using this service.",
        )
        return

    bot.send_message(
        message.chat.id,
        f"👋 Welcome *{message.from_user.first_name}*!\n\n"
        "1️⃣ Join channel\n2️⃣ Click Get ID\n3️⃣ Paste in extension\n\n"
        "⚠️ Key stops if you leave!",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


@bot.callback_query_handler(func=lambda call: call.data == "get_api")
def button(call):
    uid = call.from_user.id
    bot.answer_callback_query(call.id)

    if str(uid) in db["blocked"]:
        bot.answer_callback_query(call.id, "🚫 You are blocked.", show_alert=True)
        return

    kb = InlineKeyboardMarkup()
    if is_member(uid):
        save_user(call.from_user, verified=True)
        kb.add(InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
        bot.edit_message_text(
            f"✅ *Verified!*\n\n🔑 *Your ID:*\n`{uid}`\n\nPaste in extension!",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    else:
        db["stats"]["total_denied"] += 1
        kb.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("🔄 Try Again", callback_data="get_api"))
        kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
        bot.edit_message_text(
            "❌ *Access Denied!*\n\nJoin our channel first!",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )


@bot.callback_query_handler(func=lambda call: call.data == "reset_key")
def reset_key(call):
    uid = str(call.from_user.id)
    bot.answer_callback_query(call.id)

    if uid in db["blocked"]:
        bot.answer_callback_query(call.id, "🚫 You are blocked.", show_alert=True)
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
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda call: call.data == "show_password")
def show_password(call):
    bot.answer_callback_query(call.id)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🏠 Menu", callback_data="main_menu"))
    bot.edit_message_text(
        "🔐 *ALL Google colabe password*\n\n"
        "`7082829394`\n\n"
        "Copy and paste it in google colabe",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def back_to_menu(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"👋 Welcome *{call.from_user.first_name}*!\n\n"
        "1️⃣ Join channel\n2️⃣ Click Get ID\n3️⃣ Paste in extension\n\n"
        "⚠️ Key stops if you leave!",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


@bot.message_handler(commands=["stats"])
def tg_stats(message):
    if message.from_user.id != ADMIN_ID:
        return

    stats = db["stats"]
    bot.send_message(
        message.chat.id,
        f"📊 *Bot Stats*\n\n"
        f"👥 Total Users: `{len(db['users'])}`\n"
        f"✅ Verifications: `{stats['total_verifications']}`\n"
        f"🔍 Verify API Calls: `{stats['total_verify_calls']}`\n"
        f"❌ Denied: `{stats['total_denied']}`\n"
        f"🚫 Blocked: `{len(db['blocked'])}`",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["broadcast"])
def tg_broadcast(message):
    if message.from_user.id != ADMIN_ID:
        return

    broadcast_text = message.text.replace("/broadcast", "", 1).strip()
    if not broadcast_text:
        bot.send_message(message.chat.id, "Usage: /broadcast <message>")
        return

    sent = 0
    for uid in list(db["users"]):
        try:
            bot.send_message(
                int(uid),
                f"📢 *Announcement*\n\n{broadcast_text}",
                parse_mode="Markdown",
            )
            sent += 1
        except Exception:
            app.logger.exception("Broadcast failed for uid=%s", uid)

    db["broadcast_log"].append({
        "text": broadcast_text,
        "sent_to": sent,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    bot.send_message(message.chat.id, f"✅ Broadcast sent to {sent} users.")


# ── Health Check ─────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return "Bot is running!", 200


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


# ── Run ──────────────────────────────────────────────────────────────────────
def run_bot():
    bot.remove_webhook()
    bot.infinity_polling()


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
