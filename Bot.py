import logging
import random
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

# --- 1. KEEP-ALIVE WEB SERVER (REQUIRED FOR CLOUD) ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active and running!")

def run_server():
    # Render provides a port via environment variable, default to 8080
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"🌐 Web server started on port {port}")
    server.serve_forever()

# Start the web server in a background thread
threading.Thread(target=run_server, daemon=True).start()

# --- 2. LOGGING & CONFIG ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "8206877176:AAHSkf7uf9Qg-1Yo4IzQ_53Tc4_eGNMM8h4"  # YOUR TOKEN
DB_FILE = "toss_data.json"
games = {}

# --- 3. DATABASE FUNCTIONS ---
def load_games():
    global games
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                games = json.load(f)
            print(f"✅ Loaded {len(games)} active games.")
        except Exception as e:
            print(f"⚠️ DB Error: {e}")
            games = {}

def save_games():
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(games, f, indent=4)
    except Exception as e:
        print(f"⚠️ Save Error: {e}")

load_games()

# --- 4. GAME LOGIC ---
def is_same_user(player_data, telegram_user):
    if player_data.get('id'):
        return player_data['id'] == telegram_user.id
    if player_data.get('username') and telegram_user.username:
        return player_data['username'].lower() == telegram_user.username.lower()
    return False

async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("toss", "Start Match: /toss @Flipper @Caller")
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is Online & Cloud Ready!")

async def start_toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id
    
    # Admin Check
    member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
    if member.status not in ['administrator', 'creator']:
        await update.message.reply_text("❌ Permission Denied: Only Admins can start.")
        return

    # Extract Players
    entities = update.message.parse_entities(types=["mention", "text_mention"])
    players = []
    
    for entity, text in entities.items():
        if entity.type == 'text_mention':
            user = entity.user
            if not user.is_bot:
                players.append({
                    'id': user.id,
                    'username': user.username, 
                    'tag': f'<a href="tg://user?id={user.id}">{user.first_name}</a>',
                    'name': user.first_name
                })
        elif entity.type == 'mention':
            clean = text.strip().replace("@", "")
            players.append({'id': None, 'username': clean, 'tag': text.strip(), 'name': clean})

    if len(players) < 2:
        await update.message.reply_text("⚠️ Tag 2 users: `/toss @Flipper @Caller`", parse_mode=ParseMode.MARKDOWN)
        return

    flipper = players[0]
    caller = players[1]

    # Save Initial State
    games[chat_id] = {
        'flipper': flipper, 'caller': caller,
        'call_choice': None, 'winner': None, 'step': 'waiting_for_call'
    }
    save_games()

    keyboard = [[InlineKeyboardButton("Heads 🗣️", callback_data='HEADS'), InlineKeyboardButton("Tails 🪙", callback_data='TAILS')]]
    
    await update.message.reply_text(
        f"🏏 <b>Match Started!</b>\n\n👤 <b>Flipper:</b> {flipper['tag']}\n🗣️ <b>Caller:</b> {caller['tag']}\n\n👇 {caller['tag']}, make your call:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    user = query.from_user
    
    if chat_id not in games:
        await query.answer("⚠️ Game expired or not found.")
        return

    game = games[chat_id]
    
    # Step 1: Caller Chooses
    if game['step'] == 'waiting_for_call':
        if not is_same_user(game['caller'], user):
            await query.answer(f"Only {game['caller']['name']} can call!", show_alert=True)
            return
        
        game['call_choice'] = query.data
        game['step'] = 'waiting_for_flip'
        save_games()
        
        await query.answer()
        await query.edit_message_text(
            f"🗣️ <b>{game['caller']['name']}</b> called <b>{query.data}</b>!\n👇 {game['flipper']['tag']}, click below to flip!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Flip Coin 🪙", callback_data='FLIP')]]),
            parse_mode=ParseMode.HTML
        )

    # Step 2: Flipper Flips
    elif game['step'] == 'waiting_for_flip':
        if not is_same_user(game['flipper'], user):
            await query.answer(f"Only {game['flipper']['name']} can flip!", show_alert=True)
            return

        toss_result = random.choice(['HEADS', 'TAILS'])
        is_correct = (game['call_choice'] == toss_result)
        winner = game['caller'] if is_correct else game['flipper']
        
        game['winner'] = winner
        game['step'] = 'waiting_for_decision'
        save_games()

        win_msg = f"Coin landed on <b>{toss_result}</b>! {'✅ Correct call' if is_correct else '❌ Wrong call'}."
        
        await query.answer()
        await query.edit_message_text(
            f"{win_msg}\n\n🎉 <b>{winner['tag']} WON THE TOSS!</b>\n👇 {winner['tag']}, Bat or Bowl?",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Bat 🏏", callback_data='Bat'), InlineKeyboardButton("Bowl ⚾", callback_data='Bowl')]]),
            parse_mode=ParseMode.HTML
        )

    # Step 3: Decision
    elif game['step'] == 'waiting_for_decision':
        if not is_same_user(game['winner'], user):
            await query.answer("Only the winner decides!", show_alert=True)
            return

        await query.answer()
        await query.edit_message_text(
            f"📢 <b>OFFICIAL RESULT</b>\n\n🏆 <b>{game['winner']['tag']}</b> won and elected to <b>{query.data.upper()}</b>!",
            parse_mode=ParseMode.HTML
        )
        del games[chat_id]
        save_games()

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("toss", start_toss))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot is running...")
    application.run_polling()