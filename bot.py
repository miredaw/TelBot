from telethon import TelegramClient, events
from telethon.tl.types import User
import asyncio
import json
import os
import re
import datetime
import logging
import time
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')
SESSION_NAME = 'madeline_session'

CONFIG_FILE = 'bot_config.json'
USER_DB_FILE = 'user_database.json'
TEMPLATE_FILE = 'response_templates.json'

DEFAULT_CONFIG = {
    'bot_active': False,
    'away_mode': False,
    'response_delay': 1,
    'respond_to_groups': False
}

DEFAULT_TEMPLATES = {
    'welcome': "👋 Hello! Thanks for messaging me. I'm currently using an auto-responder. How can I help you?",
    'default': "Thanks for your message! I'll get back to you as soon as possible.",
    'away': "درود 👋🏻 ، اکنون در دسترس نیستم.\n🤖این پیام به صورت اتومات برای شما ارسال شد.",
    'keyword_responses': {
        'help|support|assist': "Need help? Please provide more details about what you need assistance with."
    }
}

# Load configuration
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("Config file not found or invalid. Using defaults.")
        return DEFAULT_CONFIG

# Load templates
def load_templates():
    try:
        with open(TEMPLATE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("Templates file not found or invalid. Using defaults.")
        return DEFAULT_TEMPLATES

# Initialize user database
def load_user_database():
    try:
        with open(USER_DB_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("User database file not found or invalid. Creating empty database.")
        return {}

def save_user_database(db):
    with open(USER_DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

# Find matching keyword response
def find_keyword_response(message_text, keyword_responses):
    message_lower = message_text.lower()
    for keywords, response in keyword_responses.items():
        if any(keyword.lower() in message_lower for keyword in keywords.split('|')):
            return response
    return None

# Format the response with variables
def format_response(response_template, user_data):
    # Replace variables in the template
    formatted = response_template
    if '{name}' in formatted and 'name' in user_data:
        name_parts = user_data.get('name', '').split()
        if name_parts:
            formatted = formatted.replace('{name}', name_parts[0])
    
    if '{full_name}' in formatted:
        formatted = formatted.replace('{full_name}', user_data.get('name', ''))
    
    if '{username}' in formatted:
        formatted = formatted.replace('{username}', user_data.get('username', ''))
    
    if '{date}' in formatted:
        formatted = formatted.replace('{date}', datetime.datetime.now().strftime('%Y-%m-%d'))
    
    if '{time}' in formatted:
        formatted = formatted.replace('{time}', datetime.datetime.now().strftime('%H:%M:%S'))
    
    return formatted

# Main function
async def main():
    # Initialize the client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start(PHONE_NUMBER)
    
    # Current configuration state
    current_config = load_config()
    current_templates = load_templates()
    last_config_check = time.time()
    config_check_interval = 10  # Check config every 10 seconds
    
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def handle_new_message(event):
        # Check if bot is active
        nonlocal current_config, current_templates, last_config_check
        
        # Periodically reload config
        current_time = time.time()
        if current_time - last_config_check > config_check_interval:
            current_config = load_config()
            current_templates = load_templates()
            last_config_check = current_time
            logger.info(f"Config reloaded. Bot active: {current_config.get('bot_active', False)}")
        
        # Skip if bot is not active
        if not current_config.get('bot_active', False):
            logger.debug("Bot is inactive, skipping message")
            return
        
        # Get sender information
        sender = await event.get_sender()
        if not isinstance(sender, User):
            return
        
        user_id = str(sender.id)
        message_text = event.message.text
        
        # Log the received message
        logger.info(f"Received message from {getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}: {message_text[:50]}...")
        
        # Load user database
        user_db = load_user_database()
        
        # Add delay to make response seem more natural
        await asyncio.sleep(current_config.get('response_delay', 1))
        
        # Prepare response
        response = ""
        
        # Check if this is first interaction with user
        is_first_message = user_id not in user_db
        
        # Update or create user record
        if is_first_message:
            user_db[user_id] = {
                'name': f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip(),
                'username': getattr(sender, 'username', None),
                'first_contact': datetime.datetime.now().isoformat(),
                'last_contact': datetime.datetime.now().isoformat(),
                'message_count': 1
            }
            response = current_templates.get('welcome', DEFAULT_TEMPLATES['welcome'])
        else:
            # Update existing user
            user_db[user_id]['last_contact'] = datetime.datetime.now().isoformat()
            user_db[user_id]['message_count'] = user_db[user_id].get('message_count', 0) + 1
            
            # Process message for keywords
            keyword_response = find_keyword_response(message_text, current_templates.get('keyword_responses', {}))
            if keyword_response:
                response = keyword_response
            else:
                response = current_templates.get('default', DEFAULT_TEMPLATES['default'])
        
        # Add away message if enabled
        if current_config.get('away_mode', False):
            response = f"\n\n{current_templates.get('away', DEFAULT_TEMPLATES['away'])}"
        
        # Format the response with user data
        response = format_response(response, user_db[user_id])
        
        # Save updated database
        save_user_database(user_db)
        
        # Send response
        await event.respond(response)
        logger.info(f"Responded to {user_db[user_id]['name']} (ID: {user_id})")

    # Command handler to manage the bot through Telegram
    @client.on(events.NewMessage(outgoing=True, pattern=r'^/bot (.+)$'))
    async def bot_command(event):
        nonlocal current_config
        
        command = event.pattern_match.group(1).strip().lower()
        config_changed = False
        
        if command == 'on':
            current_config['bot_active'] = True
            config_changed = True
            await event.edit("Bot activated ✅")
        elif command == 'off':
            current_config['bot_active'] = False
            config_changed = True
            await event.edit("Bot deactivated ❌")
        elif command == 'away on':
            current_config['away_mode'] = True
            config_changed = True
            await event.edit("Away mode activated ✅")
        elif command == 'away off':
            current_config['away_mode'] = False
            config_changed = True
            await event.edit("Away mode deactivated ❌")
        elif command.startswith('set away '):
            current_templates = load_templates()
            current_templates['away'] = command[9:].strip()
            with open(TEMPLATE_FILE, 'w') as f:
                json.dump(current_templates, f, indent=2)
            await event.edit(f"Away message updated: \"{current_templates['away']}\"")
        elif command == 'status':
            status = (
                f"Bot status: {'Active ✅' if current_config.get('bot_active', False) else 'Inactive ❌'}\n"
                f"Away mode: {'On ✅' if current_config.get('away_mode', False) else 'Off ❌'}\n"
                f"Away message: \"{current_templates.get('away', DEFAULT_TEMPLATES['away'])}\"\n"
                f"Response delay: {current_config.get('response_delay', 1)} seconds\n"
                f"Users in database: {len(load_user_database())}"
            )
            await event.edit(status)
        elif command == 'help':
            help_text = (
                "**Bot Commands:**\n"
                "/bot on - Activate the bot\n"
                "/bot off - Deactivate the bot\n"
                "/bot away on - Enable away mode\n"
                "/bot away off - Disable away mode\n"
                "/bot set away [message] - Set custom away message\n"
                "/bot status - Show current bot status\n"
                "/bot help - Show this help message"
            )
            await event.edit(help_text)
        else:
            await event.edit("Unknown command. Try /bot help for available commands.")
        
        # Save config changes
        if config_changed:
            with open(CONFIG_FILE, 'w') as f:
                current_config['last_status_update'] = datetime.datetime.now().isoformat()
                json.dump(current_config, f, indent=2)
    
    # Print startup message
    print("=" * 50)
    print("Madeline Auto-Responder is running!")
    print(f"Bot active: {current_config.get('bot_active', False)}")
    print("Commands:")
    print("  /bot on - Activate the bot")
    print("  /bot off - Deactivate the bot")
    print("  /bot away on - Enable away mode")
    print("  /bot away off - Disable away mode")
    print("  /bot set away [message] - Set custom away message")
    print("  /bot status - Show current bot status")
    print("  /bot help - Show available commands")
    print("=" * 50)
    
    # Keep the bot running
    await client.run_until_disconnected()

# Run the bot
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
