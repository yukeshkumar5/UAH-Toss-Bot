import logging
import random
import os
from threading import Thread
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)
from telegram.helpers import mention_html

# ================= CONFIG =================
TOKEN = "8206877176:AAHSkf7uf9Qg-1Yo4IzQ_53Tc4_eGNMM8h4"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ================= STORAGE =================
connected_groups = {}   # group_id -> owner_user_id
games = {}              # group_id -> game dict

# ================= PLAYER =================
class Player:
    def __init__(self, user=None, username=None):
        if user:
            self.id = user.id
            self.username = user.username
            self.name = user.first_name
            self.mention = mention_html(user.id, user.first_name)
        else:
            self.id = None
            self.username = username.lower() if username else None
            self.name = username
            self.mention = f"@{username}"

    def matches(self, tg_user):
        if self.id:
            return tg_user.id == self.id
        if self.username and tg_user.username:
            return tg_user.username.lower() == self.username
        return False

# ================= HELPERS =================
def get_game_by_reply(chat_id, reply_msg_id):
    game = games.get(chat_id)
    if not game:
        return None
    if game["message_id"] != reply_msg_id:
        return None
    return game

def is_owner(chat_id, user_id):
    return connected_groups.get(chat_id) == user_id

# ================= COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏏 <b>Toss Bot Ready</b>\n\n"
        "Group: /id\n"
        "Private: /connect <group_id>\n\n"
        "<code>/toss @Flipper @Caller</code>",
        parse_mode=ParseMode.HTML,
    )

# ---------- GROUP ID ----------
async def group_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        return
    await update.message.reply_text(
        f"📌 <b>Group ID</b>\n<code>{update.effective_chat.id}</code>",
        parse_mode=ParseMode.HTML,
    )

# ---------- CONNECT ----------
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    if not context.args:
        await update.message.reply_text("Usage: /connect <group_id>")
        return

    group_id = int(context.args[0])
    user_id = update.effective_user.id

    if group_id in connected_groups:
        await update.message.reply_text("❌ Group already connected.")
        return

    connected_groups[group_id] = user_id
    await update.message.reply_text("✅ Group connected successfully.")

# ---------- TOSS ----------
async def toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in connected_groups:
        await update.message.reply_text("❌ Group not connected.")
        return

    entities = update.message.parse_entities(
        types=["text_mention", "mention"]
    )

    players = []
    for ent, text in entities.items():
        if ent.type == "text_mention":
            players.append(Player(user=ent.user))
        elif ent.type == "mention":
            players.append(Player(username=text.replace("@", "")))

    if len(players) < 2:
        await update.message.reply_text(
            "Use: <code>/toss @Flipper @Caller</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    flipper, caller = players[0], players[1]

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("HEADS", callback_data="HEADS"),
            InlineKeyboardButton("TAILS", callback_data="TAILS"),
        ]
    ])

    msg = await update.message.reply_text(
        f"🏏 <b>TOSS TIME</b>\n\n"
        f"👤 Flipper: {flipper.mention}\n"
        f"🗣 Caller: {caller.mention}\n\n"
        f"{caller.mention}, call Heads or Tails",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )

    games[chat_id] = {
        "message_id": msg.message_id,
        "flipper": flipper,
        "caller": caller,
        "call": None,
        "winner": None,
        "step": "CALL",
    }

# ================= BUTTONS =================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat_id = q.message.chat.id
    user = q.from_user

    game = games.get(chat_id)
    if not game:
        await q.answer("No active toss", show_alert=True)
        return

    # CALL
    if q.data in ("HEADS", "TAILS"):
        if game["step"] != "CALL":
            return
        if not game["caller"].matches(user):
            await q.answer("Only caller", show_alert=True)
            return

        game["call"] = q.data
        game["step"] = "FLIP"

        await q.edit_message_text(
            f"🗣 Call: <b>{q.data}</b>\n\n"
            f"{game['flipper'].mention}, flip the coin",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("FLIP 🪙", callback_data="FLIP")]]
            ),
            parse_mode=ParseMode.HTML,
        )

    # FLIP
    elif q.data == "FLIP":
        if game["step"] != "FLIP":
            return
        if not game["flipper"].matches(user):
            await q.answer("Only flipper", show_alert=True)
            return

        toss = random.choice(["HEADS", "TAILS"])
        game["winner"] = (
            game["caller"] if toss == game["call"] else game["flipper"]
        )
        game["step"] = "DECIDE"

        await q.edit_message_text(
            f"🪙 Coin: <b>{toss}</b>\n\n"
            f"🏆 Winner: {game['winner'].mention}\n\n"
            "Choose:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("BAT", callback_data="BAT"),
                        InlineKeyboardButton("BOWL", callback_data="BOWL"),
                    ]
                ]
            ),
            parse_mode=ParseMode.HTML,
        )

    # DECISION
    elif q.data in ("BAT", "BOWL"):
        if game["step"] != "DECIDE":
            return
        if not game["winner"].matches(user):
            await q.answer("Only winner", show_alert=True)
            return

        await q.edit_message_text(
            f"📢 <b>OFFICIAL RESULT</b>\n\n"
            f"{game['winner'].mention} choose to <b>{q.data} first </b>",
            parse_mode=ParseMode.HTML,
        )

        del games[chat_id]

# ================= OVERRIDE COMMANDS =================

async def call_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = msg.chat.id

    if not msg.reply_to_message:
        return
    if not is_owner(chat_id, msg.from_user.id):
        return

    game = get_game_by_reply(chat_id, msg.reply_to_message.message_id)
    if not game or game["step"] != "CALL":
        return

    if not context.args:
        return

    arg = context.args[0].upper()
    if arg not in ("H", "T"):
        return

    game["call"] = "HEADS" if arg == "H" else "TAILS"
    game["step"] = "FLIP"

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=game["message_id"],
        text=(
            f"🗣 Call: <b>{game['call']}</b>\n\n"
            f"{game['flipper'].mention}, flip the coin"
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("FLIP 🪙", callback_data="FLIP")]]
        ),
        parse_mode=ParseMode.HTML,
    )

async def flip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = msg.chat.id

    if not msg.reply_to_message:
        return
    if not is_owner(chat_id, msg.from_user.id):
        return

    game = get_game_by_reply(chat_id, msg.reply_to_message.message_id)
    if not game or game["step"] != "FLIP":
        return

    toss = random.choice(["HEADS", "TAILS"])
    game["winner"] = (
        game["caller"] if toss == game["call"] else game["flipper"]
    )
    game["step"] = "DECIDE"

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=game["message_id"],
        text=(
            f"🪙 Coin: <b>{toss}</b>\n\n"
            f"🏆 Winner: {game['winner'].mention}\n\n"
            "Choose:"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("BAT", callback_data="BAT"),
                    InlineKeyboardButton("BOWL", callback_data="BOWL"),
                ]
            ]
        ),
        parse_mode=ParseMode.HTML,
    )

async def dec_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = msg.chat.id

    if not msg.reply_to_message:
        return
    if not is_owner(chat_id, msg.from_user.id):
        return

    game = get_game_by_reply(chat_id, msg.reply_to_message.message_id)
    if not game or game["step"] != "DECIDE":
        return

    if not context.args:
        return

    decision = context.args[0].upper()
    if decision not in ("BAT", "BOWL"):
        return

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=game["message_id"],
        text=(
            f"📢 <b>OFFICIAL RESULT</b>\n\n"
            f"{game['winner'].mention} chose <b>{decision}</b>"
        ),
        parse_mode=ParseMode.HTML,
    )

    del games[chat_id]

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot running"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ================= MAIN =================
if __name__ == "__main__":
    Thread(target=run_flask).start()

    app_bot = ApplicationBuilder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("id", group_id))
    app_bot.add_handler(CommandHandler("connect", connect))
    app_bot.add_handler(CommandHandler("toss", toss))

    app_bot.add_handler(CommandHandler("call", call_cmd))
    app_bot.add_handler(CommandHandler("flip", flip_cmd))
    app_bot.add_handler(CommandHandler("dec", dec_cmd))

    app_bot.add_handler(CallbackQueryHandler(buttons))

    print("Bot running…")
    app_bot.run_polling()