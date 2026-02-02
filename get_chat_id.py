import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot

async def get_chat_id():
    """Retrieves the Chat ID from the latest bot updates."""
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token or token == "your_bot_token_here":
        print("Error: Please set TELEGRAM_BOT_TOKEN in your .env file first.")
        return

    bot = Bot(token=token)
    print("Checking for updates... (Make sure you have sent a message to your bot)")
    
    try:
        updates = await bot.get_updates()
        if not updates:
            print("No updates found.")
            print("1. Open your bot in Telegram.")
            print("2. Send command /start or any message.")
            print("3. Run this script again.")
            return

        print("\nFound the following Chat IDs:")
        for update in updates:
            if update.message:
                chat = update.message.chat
                user = update.message.from_user
                print(f"Chat ID: {chat.id}")
                print(f"  - Type: {chat.type}")
                print(f"  - User: {user.username} ({user.first_name})")
                print("-" * 30)
                
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(get_chat_id())
