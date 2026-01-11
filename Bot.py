import logging
import random
import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.helpers import mention_html

# --- CONFIGURATION ---
# REPLACE WITH YOUR TOKEN
TOKEN = "8206877176:AAHSkf7uf9Qg-1Yo4IzQ_53Tc4_eGNMM8h4"

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# DICTIONARY TO STORE GAME STATE
# This stays in memory as long as the bot runs (24/7)
games = {}

# --- PLAYER CLASS (Handles Names & Usernames) ---
class Player:
    def __init__(self, user_obj=None, username_text=None):
        if user_obj:
            self.id = user_obj.id
            self.username = user_obj.username
            self.first_name = user_obj.first_name
            # Creates a blue clickable link to the user
            self.mention = mention_html(user_obj.id, user_obj.first_name)
        else:
            # Fallback for text-only tags
            self.id = None
            self.username = username_text.replace("@", "") if username_text else None
            self.first_name = self.username or "Unknown"
            self.mention = f"@{self.username}"

    def is_match(self, telegram_user):
        # Checks if the person clicking is the correct player
        if self.id is not None:
            return self.id == telegram_user.id
        if self.username and telegram_user.username:
            return self.username.lower() == telegram_user.username.lower()
        return False

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "I am ready! 🏏\nUse: <code>/toss @Flipper @Caller</code>", 
        parse_mode='HTML'
    )

async def start_toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # 1. Parse Mentions
    mentions = update.message.parse_entities(types=["mention", "text_mention"])
    players = []
    
    for entity, text in mentions.items():
        if entity.type == 'text_mention' and entity.user:
             if not entity.user.is_bot:
                players.append(Player(user_obj=entity.user))
        elif entity.type == 'mention':
            players.append(Player(username_text=text))

    # Remove duplicates
    unique_players = []
    seen = set()
    for p in players:
        if p.first_name not in seen:
            unique_players.append(p)
            seen.add(p.first_name)

    if len(unique_players) < 2:
        await update.message.reply_text(
            "⚠️ <b>Error:</b> I need 2 players.\nPlease tag them: <code>/toss @Flipper @Caller</code>",
            parse_mode='HTML'
        )
        return

    flipper = unique_players[0]
    caller = unique_players[1]

    # 2. Save Game (Lasts forever until finished)
    games[chat_id] = {
        'flipper': flipper,
        'caller': caller,
        'call_choice': None,
        'winner': None,
        'step': 'caller_choice' 
    }

    # 3. Step 1: Ask Caller
    keyboard = [[InlineKeyboardButton("Heads 🗣️", callback_data='HEADS'), InlineKeyboardButton("Tails 🪙", callback_data='TAILS')]]
    
    await update.message.reply_text(
        f"🏏 <b>Toss Time!</b>\n\n"
        f"👤 <b>Flipper:</b> {flipper.mention}\n"
        f"🗣️ <b>Caller:</b> {caller.mention}\n\n"
        f"{caller.mention}, please call <b>Heads</b> or <b>Tails</b>:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user = query.from_user
    
    if chat_id not in games:
        await query.answer("No active toss found.", show_alert=True)
        return

    game = games[chat_id]
    
    # --- LOGIC: CALLER CHOOSES HEADS/TAILS ---
    if game['step'] == 'caller_choice':
        if not game['caller'].is_match(user):
            await query.answer(f"Wait! Only {game['caller'].first_name} can call.", show_alert=True)
            return

        await query.answer()
        game['call_choice'] = query.data 
        game['step'] = 'flipper_flip'
        
        keyboard = [[InlineKeyboardButton("Flip Coin 🪙", callback_data='FLIP_NOW')]]
        
        await query.edit_message_text(
            f"🗣️ {game['caller'].mention} called <b>{game['call_choice']}</b>.\n\n"
            f"👤 {game['flipper'].mention}, it is your turn to <b>Flip the Coin!</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    # --- LOGIC: FLIPPER FLIPS COIN ---
    elif game['step'] == 'flipper_flip':
        if not game['flipper'].is_match(user):
            await query.answer(f"Wait! Only {game['flipper'].first_name} can flip the coin.", show_alert=True)
            return

        await query.answer()
        
        toss_result = random.choice(['HEADS', 'TAILS'])
        call = game['call_choice']
        
        if call == toss_result:
            winner = game['caller']
            msg = f"The coin landed on <b>{toss_result}</b>! ✅ Correct call."
        else:
            winner = game['flipper']
            msg = f"The coin landed on <b>{toss_result}</b>! ❌ Wrong call."

        game['winner'] = winner
        game['step'] = 'winner_decision'
        
        keyboard = [[InlineKeyboardButton("Bat 🏏", callback_data='BAT'), InlineKeyboardButton("Bowl ⚾", callback_data='BOWL')]]
        
        await query.edit_message_text(
            f"{msg}\n\n"
            f"🎉 <b>{winner.mention} WON THE TOSS!</b>\n\n"
            f"{winner.mention}, do you want to Bat or Bowl?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    # --- LOGIC: WINNER DECIDES ---
    elif game['step'] == 'winner_decision':
        if not game['winner'].is_match(user):
            await query.answer("Only the winner can decide!", show_alert=True)
            return

        await query.answer()
        decision = query.data 
        
        final_text = (
            f"📢 <b>OFFICIAL TOSS RESULT</b> 📢\n\n"
            f"🏆 <b>{game['winner'].mention}</b> won the toss and elected to <b>{decision}</b> first!"
        )
        await query.edit_message_text(text=final_text, parse_mode='HTML')
        del games[chat_id]

# --- FLASK SERVER (KEEPS BOT ALIVE 24/7) ---
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running and waiting for players!"

def run_web_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def start_web_server():
    t = Thread(target=run_web_server)
    t.start()

if __name__ == '__main__':
    start_web_server()
    
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("toss", start_toss))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    application.run_polling()