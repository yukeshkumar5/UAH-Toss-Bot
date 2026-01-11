import logging
import random
import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# --- CONFIGURATION ---
# REPLACE WITH YOUR TOKEN (Ensure no "YOU" at start)
TOKEN = "8206877176:AAHSkf7uf9Qg-1Yo4IzQ_53Tc4_eGNMM8h4"

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# DICTIONARY TO STORE GAME STATE
games = {}

# --- BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I am ready! Admins can use /toss @Flipper @Caller to start.")

async def start_toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # 1. Check Admin
    member = await context.bot.get_chat_member(chat_id, user_id)
    if member.status not in ['administrator', 'creator']:
        await update.message.reply_text("❌ Permission Denied: Only Group Admins can start a toss.")
        return

    # 2. Check Tags
    mentions = update.message.parse_entities(types=["mention", "text_mention"])
    users = [u for _, u in mentions.items() if u and not u.is_bot]
            
    if len(users) < 2:
        await update.message.reply_text("⚠️ Please tag two different users.\nUsage: /toss @Flipper @Caller")
        return

    flipper, caller = users[0], users[1]

    # 3. Save State
    games[chat_id] = {'flipper': flipper, 'caller': caller, 'winner': None, 'step': 'call'}

    # 4. Buttons
    keyboard = [[InlineKeyboardButton("Heads 🗣️", callback_data='HEADS'), InlineKeyboardButton("Tails 🪙", callback_data='TAILS')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🏏 **Toss Time!**\n(Started by Admin {update.effective_user.first_name})\n\n"
        f"👤 **Flipper:** {flipper.first_name}\n🗣️ **Caller:** {caller.first_name}\n\n"
        f"@{caller.username or caller.first_name}, please call Heads or Tails:",
        reply_markup=reply_markup, parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user = query.from_user
    
    if chat_id not in games:
        await query.answer("No active toss found. Start one with /toss")
        return

    game = games[chat_id]
    
    if game['step'] == 'call':
        if user.id != game['caller'].id:
            await query.answer("It's not your turn to call!", show_alert=True)
            return

        await query.answer()
        choice = query.data 
        toss_result = random.choice(['HEADS', 'TAILS'])
        
        winner = game['caller'] if choice == toss_result else game['flipper']
        win_msg = f"The coin landed on **{toss_result}**! {'Correct' if choice == toss_result else 'Wrong'} call."

        game['winner'] = winner
        game['step'] = 'decision'
        
        keyboard = [[InlineKeyboardButton("Bat 🏏", callback_data='BAT'), InlineKeyboardButton("Bowl ⚾", callback_data='BOWL')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{win_msg}\n\n🎉 **{winner.first_name}** won the toss!\n\n@{winner.username or winner.first_name}, what do you want to do?",
            reply_markup=reply_markup, parse_mode='Markdown'
        )

    elif game['step'] == 'decision':
        if user.id != game['winner'].id:
            await query.answer("Only the toss winner can decide!", show_alert=True)
            return

        await query.answer()
        decision = query.data 
        winner_name = game['winner'].first_name
        
        final_text = f"📢 **OFFICIAL TOSS RESULT** 📢\n\n🏆 **{winner_name}** won the toss and elected to **{decision}** first!"
        await query.edit_message_text(text=final_text, parse_mode='Markdown')
        del games[chat_id]

# --- FLASK WEB SERVER (KEEPS BOT ALIVE ON RENDER) ---
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is Alive!"

def run_web_server():
    # Render assigns a port in the environment variable 'PORT'
    port = int(os.environ.get('PORT', 8080)) 
    app.run(host='0.0.0.0', port=port)

def start_web_server():
    t = Thread(target=run_web_server)
    t.start()

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # 1. Start the Fake Web Server
    start_web_server()
    
    # 2. Start the Bot
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("toss", start_toss))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    application.run_polling()