import json
import logging
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from bs4 import BeautifulSoup
import os

# === CONFIG ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "123456789"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "webhooksecret")
QR_IMAGE_PATH = "qr.png"
UPI_ID = os.environ.get("UPI_ID", "yourupiid@upi")

bot = Bot(BOT_TOKEN)
app = FastAPI()

# === STORAGE ===
PREMIUM_FILE = "premium_users.json"
USAGE_FILE = "usage_tracker.json"

def load_json(file):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

def is_premium(user_id):
    users = load_json(PREMIUM_FILE)
    if str(user_id) in users:
        expiry = datetime.strptime(users[str(user_id)], "%Y-%m-%d")
        return datetime.now() <= expiry
    return False

def add_premium(user_id, days):
    users = load_json(PREMIUM_FILE)
    expiry = datetime.now() + timedelta(days=days)
    users[str(user_id)] = expiry.strftime("%Y-%m-%d")
    save_json(PREMIUM_FILE, users)

def can_use_free(user_id):
    usage = load_json(USAGE_FILE)
    last_used = usage.get(str(user_id))
    if not last_used:
        return True
    last_time = datetime.strptime(last_used, "%Y-%m-%d %H:%M:%S")
    return datetime.now() - last_time >= timedelta(hours=24)

def update_usage(user_id):
    usage = load_json(USAGE_FILE)
    usage[str(user_id)] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json(USAGE_FILE, usage)

def get_direct_link(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        video_tag = soup.find("video")
        if video_tag:
            source = video_tag.find("source")
            if source and source.get("src"):
                return source["src"]
        return None
    except Exception as e:
        return None

# === TELEGRAM BOT ===
application = Application.builder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton("💎 Buy Premium", callback_data="buy_premium")]]
    await update.message.reply_text(
        "👋 Welcome! Send me a Diskwala link to get the video.

Free users = 1 video / 24 hours.
Premium = unlimited access!",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if "diskwala" not in text:
        await update.message.reply_text("❌ Please send a valid Diskwala link.")
        return

    if is_premium(user_id):
        allowed = True
    else:
        allowed = can_use_free(user_id)

    if not allowed:
        await update.message.reply_text(
            "⚠️ Free users can only convert 1 video every 24 hours.

Upgrade to premium for unlimited access.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("💎 Buy Premium", callback_data="buy_premium")]]
            )
        )
        return

    await update.message.reply_text("🔄 Processing your link...")

    direct_link = get_direct_link(text)
    if direct_link:
        try:
            await update.message.reply_video(video=direct_link)
        except:
            await update.message.reply_text(f"✅ Direct link: {direct_link}")
        if not is_premium(user_id):
            update_usage(user_id)
    else:
        await update.message.reply_text("❌ Failed to extract video from link.")

async def add_premium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    try:
        target_id = int(context.args[0])
        days = int(context.args[1])
        add_premium(target_id, days)
        await update.message.reply_text(f"✅ User {target_id} upgraded for {days} days.")
    except:
        await update.message.reply_text("❌ Usage: /addpremium <user_id> <days>")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "buy_premium":
        await query.message.reply_photo(
            photo=InputFile(QR_IMAGE_PATH),
            caption=(
                "💎 *Premium Plans:*

"
                "• 7 Days = ₹29
"
                "• 30 Days = ₹79
"
                "• Lifetime = ₹149

"
                f"📲 Pay via UPI: `{UPI_ID}`
"
                "After payment, send screenshot to admin to activate premium.

"
                "👨‍💼 @YourAdminUsername"
            ),
            parse_mode="Markdown"
        )

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("addpremium", add_premium_cmd))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
application.add_handler(CallbackQueryHandler(button_callback))

@app.post("/webhook/{token}")
async def telegram_webhook(request: Request, token: str):
    if token != WEBHOOK_SECRET:
        return {"status": "unauthorized"}
    body = await request.json()
    update = Update.de_json(body, bot)
    await application.process_update(update)
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Diskwala Bot is Live"}
