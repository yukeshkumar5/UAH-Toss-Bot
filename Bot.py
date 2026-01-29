import logging
import random
import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.helpers import mention_html

# --- CONFIGURATION ---
# REPLACE THIS WITH YOUR REAL TOKEN
TOKEN = "8206877176:AAHSkf7uf9Qg-1Yo4IzQ_53Tc4_eGNMM8h4" 

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- GLOBAL DATA STORE ---
# games[chat_id] = { ... game data ... }
games = {}

# team_data[chat_id] = { user_id: "Team Name" }
team_data = {}

# --- HELPER FUNCTIONS ---

def get_display_name(chat_id, user):
    """Returns 'Team Name (User)' if registered, else 'User'."""
    user_id = user.id
    first_name = user.first_name
    
    # Check if this group has team data and if user is in it
    if chat_id in team_data and user_id in team_data[chat_id]:
        team_name = team_data[chat_id][user_id]
        # Return: Chennai Super Kings (Yukeag)
        return f"<b>{team_name}</b> ({mention_html(user_id, first_name)})"
    
    return mention_html(user_id, first_name)

async def is_admin(update: Update):
    """Checks if the user is an Admin or Creator of the group."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        member = await update.effective_chat.get_member(user_id)
        return member.status in ['administrator', 'creator']
    except:
        # Fallback if bot is not admin or can't check
        return False

# --- LOGIC HANDLERS (Shared by Button & Command) ---

async def process_call(chat_id, user_id, choice, context):
    """Handles logic when someone picks Heads/Tails"""
    if chat_id not in games: return "No game"
    game = games[chat_id]
    
    # Check Step
    if game['step'] != 'caller_choice': return "Wrong step"

    # Check Permission (Caller OR Creator)
    if user_id != game['caller'].id and user_id != game['creator_id']:
        return "Not authorized"

    game['call_choice'] = choice
    game['step'] = 'flipper_flip'

    flipper_name = get_display_name(chat_id, game['flipper'])
    caller_name = get_display_name(chat_id, game['caller'])
    
    keyboard = [[InlineKeyboardButton("Flip Coin 🪙", callback_data='FLIP_NOW')]]
    
    text = (f"🗣️ {caller_name} called <b>{choice}</b>.\n\n"
            f"👤 {flipper_name}, it is your turn to <b>Flip the Coin!</b>")
            
    # Edit the existing game message
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game['message_id'],
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Error editing message: {e}")
        
    return "Success"

async def process_decision(chat_id, user_id, decision, context):
    """Handles logic when winner picks Bat/Bowl"""
    if chat_id not in games: return "No game"
    game = games[chat_id]
    
    if game['step'] != 'winner_decision': return "Wrong step"

    # Check Permission (Winner OR Creator)
    if user_id != game['winner'].id and user_id != game['creator_id']:
        return "Not authorized"

    winner_name = get_display_name(chat_id, game['winner'])
    
    final_text = (
        f"📢 <b>OFFICIAL TOSS RESULT</b> 📢\n\n"
        f"🏆 <b>{winner_name}</b> won the toss and elected to <b>{decision}</b> first!"
    )
    
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game['message_id'],
            text=final_text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Error editing message: {e}")
    
    # End Game
    if chat_id in games:
        del games[chat_id]
    return "Success"

# --- BOT COMMANDS ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /help command """
    help_text = (
        "🏏 <b>CRICKET TOSS BOT HELP</b>\n\n"
        "<b>Basic Commands:</b>\n"
        "• <code>/toss @Flipper @Caller</code> - Start a toss\n"
        "• <code>/reg @User Team Name</code> - Register a team name (Admins only)\n\n"
        "<b>Override Commands (For Captain/Owner):</b>\n"
        "<i>Use these if buttons are not working or player is offline.</i>\n"
        "• <code>/call H</code> or <code>/call T</code> - Call Heads/Tails\n"
        "• <code>/decision bat</code> or <code>/decision bowl</code> - Choose Bat/Bowl"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def register_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /reg @User Team Name (Admins Only) """
    chat_id = update.effective_chat.id
    
    # 1. Check Admin Permissions
    if not await is_admin(update):
        await update.message.reply_text("⛔ Only Group Admins can register teams.")
        return

    # 2. Find the "Blue Name" (Text Mention)
    target_user = None
    target_entity = None
    
    entities = update.message.parse_entities(types=["text_mention", "mention"])
    
    for entity, text in entities.items():
        if entity.type == 'text_mention':
            target_user = entity.user
            target_entity = entity
            break
        elif entity.type == 'mention':
            await update.message.reply_text(
                "⚠️ <b>I cannot identify that user.</b>\n\n"
                "Please type @ and <b>select their name from the list</b> so it becomes a blue link.",
                parse_mode=ParseMode.HTML
            )
            return

    if not target_user:
        await update.message.reply_text("⚠️ Usage: <code>/reg @User Team Name</code>\n(Make sure to use a blue mention!)", parse_mode=ParseMode.HTML)
        return

    # 3. Extract the Team Name
    full_text = update.message.text
    mention_end_index = target_entity.offset + target_entity.length
    team_name_raw = full_text[mention_end_index:].strip()
    
    if not team_name_raw:
        await update.message.reply_text("⚠️ You forgot to type the Team Name!")
        return

    # 4. Save to Memory
    if chat_id not in team_data:
        team_data[chat_id] = {}
    
    team_data[chat_id][target_user.id] = team_name_raw
    
    await update.message.reply_text(
        f"✅ <b>Registered Successfully!</b>\n"
        f"👤 Player: {mention_html(target_user.id, target_user.first_name)}\n"
        f"🛡️ Team: <b>{team_name_raw}</b>",
        parse_mode=ParseMode.HTML
    )

async def start_toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # 1. Parse Players (Prefer Blue Mentions)
    entities = update.message.parse_entities(types=["text_mention", "mention"])
    players = []
    
    for entity, text in entities.items():
        if entity.type == 'text_mention':
            if not entity.user.is_bot:
                players.append(entity.user)
    
    # Remove duplicates
    unique_players = []
    seen_ids = set()
    for p in players:
        if p.id not in seen_ids:
            unique_players.append(p)
            seen_ids.add(p.id)

    if len(unique_players) < 2:
        await update.message.reply_text(
            "⚠️ <b>I need 2 players with Blue Mentions.</b>\n"
            "Use: <code>/toss @Player1 @Player2</code>", 
            parse_mode=ParseMode.HTML
        )
        return

    flipper = unique_players[0]
    caller = unique_players[1]
    
    # 2. Save Game State
    games[chat_id] = {
        'creator_id': user.id,
        'flipper': flipper,
        'caller': caller,
        'call_choice': None,
        'winner': None,
        'step': 'caller_choice',
        'message_id': None 
    }

    flipper_name = get_display_name(chat_id, flipper)
    caller_name = get_display_name(chat_id, caller)

    keyboard = [[InlineKeyboardButton("Heads 🗣️", callback_data='HEADS'), InlineKeyboardButton("Tails 🪙", callback_data='TAILS')]]
    
    sent_msg = await update.message.reply_text(
        f"🏏 <b>Toss Time!</b>\n\n"
        f"👤 <b>Flipper:</b> {flipper_name}\n"
        f"🗣️ <b>Caller:</b> {caller_name}\n\n"
        f"{caller_name}, please call <b>Heads</b> or <b>Tails</b>:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    games[chat_id]['message_id'] = sent_msg.message_id

# --- COMMAND OVERRIDES (/call & /decision) ---

async def command_call(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if chat_id not in games:
        await update.message.reply_text("❌ No active toss.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/call H` or `/call T`", parse_mode=ParseMode.MARKDOWN)
        return

    choice_letter = context.args[0].upper()
    if choice_letter.startswith('H'): choice = 'HEADS'
    elif choice_letter.startswith('T'): choice = 'TAILS'
    else: return

    result = await process_call(chat_id, user_id, choice, context)
    
    if result == "Not authorized":
        await update.message.reply_text("⛔ You are not the Caller or the Creator.", quote=True)
    elif result == "Success":
        # Try delete command to keep chat clean
        try: await update.message.delete()
        except: pass

async def command_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if chat_id not in games: return

    if not context.args:
        await update.message.reply_text("Usage: `/decision bat` or `/decision bowl`", parse_mode=ParseMode.MARKDOWN)
        return

    dec_text = context.args[0].lower()
    if 'bat' in dec_text: decision = "BAT 🏏"
    elif 'bowl' in dec_text: decision = "BOWL ⚾"
    else: return

    result = await process_decision(chat_id, user_id, decision, context)
    
    if result == "Not authorized":
        await update.message.reply_text("⛔ You are not the Winner or the Creator.", quote=True)
    elif result == "Success":
        try: await update.message.delete()
        except: pass

# --- BUTTON HANDLER ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = query.from_user.id
    
    if chat_id not in games:
        await query.answer("No active toss found.", show_alert=True)
        return

    game = games[chat_id]
    
    # 1. CALL HEADS/TAILS
    if query.data in ['HEADS', 'TAILS']:
        if user_id != game['caller'].id:
            await query.answer("Wait for the Caller!", show_alert=True)
            return
        await query.answer()
        await process_call(chat_id, user_id, query.data, context)

    # 2. FLIP COIN (Only Flipper)
    elif query.data == 'FLIP_NOW':
        if user_id != game['flipper'].id:
            await query.answer("Only the Flipper can flip!", show_alert=True)
            return
            
        await query.answer()
        toss_result = random.choice(['HEADS', 'TAILS'])
        call = game['call_choice']
        
        if call == toss_result:
            winner = game['caller']
            msg = f"Coin landed on <b>{toss_result}</b>! ✅ Correct call."
        else:
            winner = game['flipper']
            msg = f"Coin landed on <b>{toss_result}</b>! ❌ Wrong call."

        game['winner'] = winner
        game['step'] = 'winner_decision'
        
        winner_name = get_display_name(chat_id, winner)
        
        keyboard = [[InlineKeyboardButton("Bat 🏏", callback_data='BAT'), InlineKeyboardButton("Bowl ⚾", callback_data='BOWL')]]
        
        try:
            await query.edit_message_text(
                f"{msg}\n\n"
                f"🎉 <b>{winner_name} WON THE TOSS!</b>\n\n"
                f"{winner_name}, do you want to Bat or Bowl?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Error editing message: {e}")

    # 3. DECISION (Bat/Bowl)
    elif query.data in ['BAT', 'BOWL']:
        decision_text = "BAT 🏏" if query.data == 'BAT' else "BOWL ⚾"
        if user_id != game['winner'].id:
            await query.answer("Only the winner can decide!", show_alert=True)
            return
        await query.answer()
        await process_decision(chat_id, user_id, decision_text, context)

# --- FLASK SERVER (For Uptime) ---
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is running!"

def run_web_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Start Flask Server in Background
    t = Thread(target=run_web_server)
    t.start()
    
    # Start Telegram Bot
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Register Handlers
    application.add_handler(CommandHandler("start", help_command)) 
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("toss", start_toss))
    application.add_handler(CommandHandler("reg", register_team))
    
    # Override Commands
    application.add_handler(CommandHandler("call", command_call))
    application.add_handler(CommandHandler("decision", command_decision))
    
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    application.run_polling()
