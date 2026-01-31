import logging
import random
import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.helpers import mention_html

# ================= CONFIG =================
TOKEN = "PASTE_YOUR_TOKEN_HERE"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ================ STORAGE =================
games = {}         # one active toss per group
group_admins = {}  # chat_id -> set(user_ids)

# ================ HELPERS =================

def is_toss_admin(chat_id, user_id):
    return chat_id in group_admins and user_id in group_admins[chat_id]

async def is_telegram_admin(update: Update):
    try:
        member = await update.effective_chat.get_member(update.effective_user.id)
        return member.status in ("administrator", "creator")
    except:
        return False

# ================ COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏏 <b>Cricket Toss Bot Ready</b>\n\n"
        "<code>/toss @Flipper @Caller</code>\n"
        "<code>/connect</code> (one-time)\n",
        parse_mode=ParseMode.HTML
    )

# ---- CONNECT GROUP ----
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id in group_admins:
        await update.message.reply_text("❌ Group already connected.")
        return

    if not await is_telegram_admin(update):
        await update.message.reply_text("⛔ Only Telegram admins can connect.")
        return

    group_admins[chat_id] = {user_id}
    await update.message.reply_text("✅ Group connected. You are Toss Admin.")

# ---- PROMOTE ADMIN ----
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in group_admins or user_id not in group_admins[chat_id]:
        await update.message.reply_text("❌ Only Toss Admin can promote.")
        return

    entities = update.message.parse_entities(["text_mention"])
    for ent in entities:
        group_admins[chat_id].add(ent.user.id)
        await update.message.reply_text(
            f"✅ Promoted {mention_html(ent.user.id, ent.user.first_name)}",
            parse_mode=ParseMode.HTML
        )

# ---- START TOSS ----
async def toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    entities = update.message.parse_entities(["text_mention"])

    users = [e.user for e in entities if not e.user.is_bot]
    if len(users) < 2:
        await update.message.reply_text(
            "⚠️ Use blue mentions:\n<code>/toss @Player1 @Player2</code>",
            parse_mode=ParseMode.HTML
        )
        return

    flipper, caller = users[0], users[1]

    games[chat_id] = {
        "flipper": flipper,
        "caller": caller,
        "call": None,
        "winner": None,
        "step": "CALL"
    }

    keyboard = [
        [InlineKeyboardButton("HEADS", callback_data="HEADS"),
         InlineKeyboardButton("TAILS", callback_data="TAILS")]
    ]

    await update.message.reply_text(
        f"🏏 <b>TOSS TIME</b>\n\n"
        f"👤 Flipper: {mention_html(flipper.id, flipper.first_name)}\n"
        f"🗣 Caller: {mention_html(caller.id, caller.first_name)}\n\n"
        f"{mention_html(caller.id, caller.first_name)}, call Heads or Tails",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

# ================ BUTTON HANDLER =================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat_id = q.message.chat.id
    user_id = q.from_user.id

    if chat_id not in games:
        await q.answer("No active toss", show_alert=True)
        return

    game = games[chat_id]

    # CALL
    if q.data in ("HEADS", "TAILS"):
        if game["step"] != "CALL":
            return
        if user_id != game["caller"].id:
            await q.answer("Only caller", show_alert=True)
            return

        game["call"] = q.data
        game["step"] = "FLIP"

        await q.edit_message_text(
            f"🗣 Call: <b>{q.data}</b>\n\n"
            f"👤 {mention_html(game['flipper'].id, game['flipper'].first_name)}, flip the coin",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("FLIP 🪙", callback_data="FLIP")]]
            ),
            parse_mode=ParseMode.HTML
        )

    # FLIP
    elif q.data == "FLIP":
        if game["step"] != "FLIP":
            return
        if user_id != game["flipper"].id:
            await q.answer("Only flipper", show_alert=True)
            return

        toss = random.choice(["HEADS", "TAILS"])
        game["winner"] = game["caller"] if toss == game["call"] else game["flipper"]
        game["step"] = "DECIDE"

        await q.edit_message_text(
            f"🪙 Coin: <b>{toss}</b>\n\n"
            f"🏆 Winner: {mention_html(game['winner'].id, game['winner'].first_name)}\n\n"
            "Choose:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("BAT", callback_data="BAT"),
                  InlineKeyboardButton("BOWL", callback_data="BOWL")]]
            ),
            parse_mode=ParseMode.HTML
        )

    # DECISION
    elif q.data in ("BAT", "BOWL"):
        if game["step"] != "DECIDE":
            return
        if user_id != game["winner"].id:
            await q.answer("Only winner", show_alert=True)
            return

        await q.edit_message_text(
            f"📢 <b>OFFICIAL RESULT</b>\n\n"
            f"{mention_html(game['winner'].id, game['winner'].first_name)} chose <b>{q.data}</b>",
            parse_mode=ParseMode.HTML
        )

        del games[chat_id]

# ================ ADMIN OVERRIDES =================

async def call_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        return
    if not is_toss_admin(chat_id, update.effective_user.id):
        return
    if context.args and context.args[0].upper() in ("H", "T"):
        games[chat_id]["call"] = "HEADS" if context.args[0].upper() == "H" else "TAILS"
        games[chat_id]["step"] = "FLIP"
        await update.message.reply_text("✅ Call set by admin")

async def flip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        return
    if not is_toss_admin(chat_id, update.effective_user.id):
        return
    game = games[chat_id]
    toss = random.choice(["HEADS", "TAILS"])
    game["winner"] = game["caller"] if toss == game["call"] else game["flipper"]
    game["step"] = "DECIDE"
    await update.message.reply_text(f"🪙 Coin: {toss}")

async def dec_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        return
    if not is_toss_admin(chat_id, update.effective_user.id):
        return
    if context.args:
        await update.message.reply_text(
            f"🏆 {mention_html(games[chat_id]['winner'].id, games[chat_id]['winner'].first_name)} chose {context.args[0].upper()}",
            parse_mode=ParseMode.HTML
        )
        del games[chat_id]

# ================ FLASK =================

app = Flask(__name__)
@app.route("/")
def home():
    return "Bot running"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ================ MAIN =================

if __name__ == "__main__":
    Thread(target=run_flask).start()

    app_bot = ApplicationBuilder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("connect", connect))
    app_bot.add_handler(CommandHandler("promote", promote))
    app_bot.add_handler(CommandHandler("toss", toss))

    app_bot.add_handler(CommandHandler("call", call_cmd))
    app_bot.add_handler(CommandHandler("flip", flip_cmd))
    app_bot.add_handler(CommandHandler("dec", dec_cmd))

    app_bot.add_handler(CallbackQueryHandler(buttons))

    print("Bot running...")
    app_bot.run_polling()
