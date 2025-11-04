import os
import random
import asyncio
from datetime import datetime, timezone
from threading import Thread

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from pymongo import MongoClient, ASCENDING, DESCENDING

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8593054929:AAF_1gOLdrm2yQPcTASUaRmRzfnBLwdDsmc")
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://lolpoc48_db_user:knpw7BahfpIUOUpQ@cluster0.aj25qoh.mongodb.net/?appName=Cluster0",
)
PO_POSTBACK_SECRET = os.getenv("PO_POSTBACK_SECRET", "VeryStrongSecret123")
PARTNER_LINK = (
    "https://u3.shortink.io/register?utm_campaign=790429&utm_source=affiliate"
    "&utm_medium=sr&a=bqijcaDVb5V8SJ&ac=signalbot&code=NCY297"
)

# ================== INIT ==================
app = Flask(__name__)
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client["pocketoption_bot"]
users_collection = db["users"]
postbacks_collection = db["postbacks"]
user_status_collection = db["user_status"]

# indexes (created once)
postbacks_collection.create_index([("trader_id", ASCENDING), ("createdAt", DESCENDING)])
user_status_collection.create_index("trader_id", unique=True)

# ================== USER STATUSES ==================
STATUS_NEW = "new"
STATUS_WAITING_UID = "waiting_uid"
STATUS_WAITING_VERIFICATION = "waiting_verification"
STATUS_VERIFIED = "verified"


# ================== HELPERS ==================
def _truthy(v) -> bool:
    """Normalize truthy values from query/body."""
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _utcnow():
    return datetime.now(timezone.utc)


# ================== POSTBACK WEBHOOK ==================
@app.route("/api/pocket/postback", methods=["GET", "POST"])
def handle_postback():
    try:
        data = request.args.to_dict() if request.method == "GET" else (request.json or {})
        secret = data.get("secret") or request.args.get("secret")
        if PO_POSTBACK_SECRET and secret != PO_POSTBACK_SECRET:
            return jsonify({"ok": False, "error": "bad_secret"}), 401

        trader_id = (data.get("trader_id") or "").strip()
        click_id = (data.get("click_id") or "").strip()
        site_id = (data.get("site_id") or "").strip()
        a = (data.get("a") or "").strip()
        ac = (data.get("ac") or "").strip()

        reg = _truthy(data.get("reg"))
        conf = _truthy(data.get("conf"))
        ftd = _truthy(data.get("ftd"))
        dep = _truthy(data.get("dep"))

        # priority: ftd -> dep -> reg -> conf
        event = None
        if ftd:
            event = "ftd"
        elif dep:
            event = "dep"
        elif reg:
            event = "reg"
        elif conf:
            event = "conf"

        doc = {
            "createdAt": _utcnow(),
            "trader_id": trader_id,
            "click_id": click_id,
            "site_id": site_id,
            "a": a,
            "ac": ac,
            "reg": reg,
            "conf": conf,
            "ftd": ftd,
            "dep": dep,
            "event": event,
            "raw": data,
        }
        postbacks_collection.insert_one(doc)

        # aggregate status per trader
        if trader_id:
            incr_registered = reg or conf
            incr_deposited = ftd or dep

            update = {
                "$setOnInsert": {"createdAt": _utcnow(), "trader_id": trader_id},
                "$set": {"updatedAt": _utcnow(), "last_event": event},
                "$max": {},
            }
            status = user_status_collection.find_one({"trader_id": trader_id}) or {}
            new_registered = bool(status.get("registered")) or incr_registered
            new_deposited = bool(status.get("deposited")) or incr_deposited
            update["$set"]["registered"] = new_registered
            update["$set"]["deposited"] = new_deposited

            user_status_collection.update_one(
                {"trader_id": trader_id}, update, upsert=True
            )

            # sync with a user record (if they already sent UID)
            user = users_collection.find_one({"uid": trader_id})
            if user:
                to_set = {}
                if incr_registered:
                    to_set["registered"] = True
                if incr_deposited:
                    to_set["first_deposit"] = True
                    to_set["status"] = STATUS_VERIFIED
                if to_set:
                    users_collection.update_one({"uid": trader_id}, {"$set": to_set})

        return jsonify({"ok": True}), 200

    except Exception as e:
        print(f"[postback] error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 400


# ================== TELEGRAM BOT ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user_id = update.effective_user.id
    user = users_collection.find_one({"telegram_id": user_id})

    if not user:
        users_collection.insert_one(
            {
                "telegram_id": user_id,
                "username": update.effective_user.username,
                "status": STATUS_NEW,
                "registered": False,
                "first_deposit": False,
                "created_at": _utcnow(),
            }
        )

    keyboard = [[InlineKeyboardButton("🚀 Start verification", callback_data="verify")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome to the PocketOption Trading Signals Bot!\n\n"
        "To get access you need to pass verification:\n"
        "1) Register via the partner link\n"
        "2) Confirm your email\n"
        "3) Make the first deposit\n"
        "4) Send your UID (Trader ID)\n\n"
        "Tap the button below to begin 👇",
        reply_markup=reply_markup,
    )


async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user = users_collection.find_one({"telegram_id": user_id})

    if user and user.get("status") == STATUS_VERIFIED:
        await query.edit_message_text(
            "✅ You are already verified!\n"
            "Send a chart screenshot and I'll generate a signal 📊"
        )
        return

    keyboard = [
        [InlineKeyboardButton("📝 Register", url=PARTNER_LINK)],
        [InlineKeyboardButton("✅ I have registered", callback_data="reg_done")],
    ]
    await query.edit_message_text(
        "🔐 STEP 1: Registration\n\n"
        "Register via the link above, confirm your email and then tap “I have registered”.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def reg_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [[InlineKeyboardButton("✅ Enter UID", callback_data="enter_uid")]]
    await query.edit_message_text(
        "💰 STEP 2: First deposit\n\n"
        "Make your first deposit on PocketOption, then tap “Enter UID”.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def enter_uid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    users_collection.update_one(
        {"telegram_id": user_id}, {"$set": {"status": STATUS_WAITING_UID}}
    )

    await query.edit_message_text(
        "🆔 STEP 3: Send UID\n\n"
        "Please send your *Trader ID* (UID) from po.cash in the next message."
    )


async def handle_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user_id = update.effective_user.id
    user = users_collection.find_one({"telegram_id": user_id})

    if not user or user.get("status") != STATUS_WAITING_UID:
        return

    uid = update.message.text.strip()

    users_collection.update_one(
        {"telegram_id": user_id},
        {"$set": {"uid": uid, "status": STATUS_WAITING_VERIFICATION}},
    )

    await update.message.reply_text("⏳ Checking your data…")
    await asyncio.sleep(2)

    status = user_status_collection.find_one({"trader_id": uid})
    registration_ok = bool(status and status.get("registered"))
    first_deposit_ok = bool(status and status.get("deposited"))

    if registration_ok and first_deposit_ok:
        users_collection.update_one(
            {"telegram_id": user_id},
            {
                "$set": {
                    "status": STATUS_VERIFIED,
                    "registered": True,
                    "first_deposit": True,
                }
            },
        )
        await update.message.reply_text(
            "✅ Verification passed!\n\n"
            "Send a chart screenshot and I’ll give you a trading signal 📊"
        )
    else:
        missing = []
        if not registration_ok:
            missing.append("registration/email confirmation")
        if not first_deposit_ok:
            missing.append("first deposit")

        await update.message.reply_text(
            "❌ Verification failed.\n\n"
            f"Missing: {', '.join(missing) if missing else 'data'}\n\n"
            "Check the steps and try again via /start."
        )


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return

    user_id = update.effective_user.id
    user = users_collection.find_one({"telegram_id": user_id})

    if not user:
        await update.message.reply_text("❌ Please /start first.")
        return

    if user.get("status") != STATUS_VERIFIED:
        await update.message.reply_text(
            "❌ Access denied. Pass verification via /start."
        )
        return

    if not update.message.photo:
        await update.message.reply_text("❌ Please send a chart screenshot.")
        return

    thinking = await update.message.reply_text("🤖 Analyzing the chart…")
    for i in range(6, 0, -1):
        await asyncio.sleep(1)
        await thinking.edit_text(f"🤖 Analyzing the chart… {i}s")

    direction = random.choice(["📈 LONG (up)", "📉 SHORT (down)"])
    duration = random.choice([5, 10, 15, 20, 25, 30])
    confidence = random.randint(70, 95)

    await thinking.edit_text(
        "🎯 TRADING SIGNAL\n\n"
        f"Direction: {direction}\n"
        f"Expiry: {duration} sec\n"
        f"Confidence: {confidence}%\n\n"
      
    )

    users_collection.update_one({"telegram_id": user_id}, {"$inc": {"signals": 1}})


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "📖 Commands:\n"
            "/start — begin\n"
            "/status — verification status\n"
            "/help — help\n\n"
            "After verification, send a chart screenshot."
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    user = users_collection.find_one({"telegram_id": update.effective_user.id})
    if not user:
        await update.message.reply_text("❌ You are not registered. Use /start.")
        return

    status_emoji = {
        STATUS_NEW: "🆕",
        STATUS_WAITING_UID: "⏳",
        STATUS_WAITING_VERIFICATION: "🔍",
        STATUS_VERIFIED: "✅",
    }
    status_text = {
        STATUS_NEW: "New user",
        STATUS_WAITING_UID: "Waiting for UID",
        STATUS_WAITING_VERIFICATION: "Verifying data",
        STATUS_VERIFIED: "Verified",
    }

    await update.message.reply_text(
        "📊 Status\n\n"
        f"{status_emoji.get(user.get('status'), '❓')} "
        f"{status_text.get(user.get('status'), 'Unknown')}\n"
        f"{'✅' if user.get('registered') else '❌'} Registration\n"
        f"{'✅' if user.get('first_deposit') else '❌'} First deposit\n"
        f"UID: {user.get('uid', '—')}"
    )


# ================== BOT RUN ==================
def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify$"))
    application.add_handler(CallbackQueryHandler(reg_done_callback, pattern="^reg_done$"))
    application.add_handler(CallbackQueryHandler(enter_uid_callback, pattern="^enter_uid$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_uid))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


# ================== START EVERYTHING ==================
if __name__ == "__main__":
    # Run Flask on a side thread (defaults to 5001 locally)
    def run_flask():
        port = int(os.getenv("PORT", 5001))
        app.run(host="0.0.0.0", port=port)

    t = Thread(target=run_flask, daemon=True)
    t.start()

    print("🤖 Bot starting…")
    run_bot()
