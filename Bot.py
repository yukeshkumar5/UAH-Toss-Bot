import logging
import random
import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode
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
    
    member = await update.effective_chat.get_member(user_id)
    return member.status in ['administrator', 'creator']

# --- BOT COMMANDS ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /help command """
    help_text = (
        "🏏 <b>CRICKET TOSS BOT HELP</b>\n\n"
        "<b>Basic Commands:</b>\n"
        "• <code>/toss @Flipper @Caller</code> - Start a toss\n"
        "• <code>/reg @User Team Name</code> - Register a team name (Admins only)\n\n"
        "<b>Override Commands (If buttons don't work):</b>\n"
        "<i>(Only the Toss Creator or the Active Player can use these)</i>\n"
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

    # 2. Parse Arguments
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("⚠️ Usage: <code>/reg @User Team Name</code>", parse_mode=ParseMode.HTML)
        return

    # 3. Extract User and Team Name
    # We look for the entity in the message to get the ID safely
    mentions = update.message.parse_entities(types=["mention", "text_mention"])
    target_user_id = None
    
    # Get the first mentioned user
    for entity, user in mentions.items():
        if entity.type == 'text_mention':
            target_user_id = user.user.id
            break
        elif entity.type == 'mention':
            # This is harder because we only have username, but let's try to assume args[0] is the mention
            # Note: Best way in API is text_mention, but for simple string matching:
            target_user_id = None # Logic complicates here without user object, skipping for safety
            # In a real bot, you rely on the update entities.
            pass

    # Fallback: if we can't get ID from entity easily (common in simple bots), 
    # we just warn user to tag correctly.
    # However, let's grab the mention from message entities.
    entities = update.message.entities
    if not entities or entities[0].type not in ['mention', 'text_mention']:
         await update.message.reply_text("⚠️ Please mention the user first: <code>/reg @User Team Name</code>", parse_mode=ParseMode.HTML)
         return

    # Get the user object from the entity if possible, or we need to rely on the update data
    # NOTE: Telegram API doesn't give User ID from a simple text "@username" unless the bot has seen them.
    # We will rely on the `message.parse_entities` we did earlier.
    
    # Let's simplify: To register, the user MUST be clickable (text_mention) or valid username.
    # We will iterate entities again.
    found_user = None
    for key, val in mentions.items():
        # val is the text of the mention, key is the entity object
        if key.type == 'text_mention':
            found_user = key.user
            break
        # If it's a standard @mention, we can't easily get the ID unless we resolve it.
        # For this snippet, we will assume the user has to be interactable.
    
    # Helper: If simple @mention, we try to map if the user has spoken before.
    # For now, let's accept that we need a User Object.
    
    # FIX: Using message.reply_to_message is easier for ID, but requirement says "/reg @user Team".
    # Let's assume the user tagged is in `update.message.effective_user`? No, that's the sender.
    
    # Implementation strategy: Split text.
    # args[0] is likely the name. args[1:] is the team name.
    team_name = " ".join(args[1:])
    
    # We need the ID. If we can't find it via text_mention, we store by username (less reliable).
    # Storing by ID is best.
    user_id_to_save = None
    user_name_to_save = None
    
    for entity in update.message.entities:
        if entity.type == 'text_mention':
            user_id_to_save = entity.user.id
            user_name_to_save = entity.user.first_name
            break
        if entity.type == 'mention':
            # It's a @username. 
            # We can't get ID easily. We will store Key as "USERNAME" (string).
            username_str = update.message.text[entity.offset:entity.offset + entity.length]
            # Verify if this matches args[0]
            if username_str == args[0]:
                 # Warning: Username changes break this.
                 await update.message.reply_text("⚠️ Please use a clickable mention for better accuracy, or I can't get their ID.")
                 return

    if user_id_to_save and team_name:
        if chat_id not in team_data:
            team_data[chat_id] = {}
        
        team_data[chat_id][user_id_to_save] = team_name
        
        await update.message.reply_text(
            f"✅ Registered!\n<b>{team_name}</b> is now managed by {mention_html(user_id_to_save, user_name_to_save)}",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("⚠️ Could not detect user. Please select them from the suggestion list when typing.")

async def start_toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # 1. Parse Mentions
    mentions = update.message.parse_entities(types=["mention", "text_mention"])
    players = []
    
    # Filter out bots and get users
    for entity, text in mentions.items():
        if entity.type == 'text_mention' and entity.user:
             if not entity.user.is_bot:
                players.append(entity.user)
        elif entity.type == 'mention':
            # We can't handle pure text mentions easily for logic without ID.
            # Skipping strictly text-based mentions to ensure ID consistency for teams.
            pass

    # Ensure unique players
    unique_players = list({p.id: p for p in players}.values())

    if len(unique_players) < 2:
        await update.message.reply_text("⚠️ Tag 2 players: <code>/toss @Player1 @Player2</code>", parse_mode=ParseMode.HTML)
        return

    flipper = unique_players[0]
    caller = unique_players[1]
    creator_id = user.id

    # 2. Save Game State
    games[chat_id] = {
        'creator_id': creator_id,
        'flipper': flipper,
        'caller': caller,
        'call_choice': None,
        'winner': None,
        'step': 'caller_choice',
        'message_id': None # We will fill this after sending the message
    }

    # 3. Send Message
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
    
    # Save the message ID so we can edit it later via /call commands
    games[chat_id]['message_id'] = sent_msg.message_id

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
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=game['message_id'],
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
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
    
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=game['message_id'],
        text=final_text,
        parse_mode=ParseMode.HTML
    )
    
    # End Game
    del games[chat_id]
    return "Success"

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
        await update.message.reply_text("⛔ You are not the Caller or the Creator.")
    elif result == "Success":
        # Delete the command message to keep chat clean (optional, requires permission)
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
        await update.message.reply_text("⛔ You are not the Winner or the Creator.")
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
        
        await query.edit_message_text(
            f"{msg}\n\n"
            f"🎉 <b>{winner_name} WON THE TOSS!</b>\n\n"
            f"{winner_name}, do you want to Bat or Bowl?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    # 3. DECISION (Bat/Bowl)
    elif query.data in ['BAT', 'BOWL']:
        decision_text = "BAT 🏏" if query.data == 'BAT' else "BOWL ⚾"
        if user_id != game['winner'].id:
            await query.answer("Only the winner can decide!", show_alert=True)
            return
        await query.answer()
        await process_decision(chat_id, user_id, decision_text, context)

# --- FLASK SERVER ---
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is running!"

def run_web_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    t = Thread(target=run_web_server)
    t.start()
    
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Register Handlers
    application.add_handler(CommandHandler("start", help_command)) # Start shows help
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("toss", start_toss))
    application.add_handler(CommandHandler("reg", register_team))
    
    # Override Commands
    application.add_handler(CommandHandler("call", command_call))
    application.add_handler(CommandHandler("decision", command_decision))
    
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    application.run_polling()
