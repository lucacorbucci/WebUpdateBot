import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove

from database import Monitor, async_session, init_db, get_all_active_monitors
from monitor import PageMonitor

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# States
FOLLOW_URL, FOLLOW_FREQ = range(2)
REMOVE_SELECT = 2
UPDATE_SELECT, UPDATE_FREQ = range(3, 5)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message."""
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(
        "👋 Welcome to Scraper Bot V2!\n\n"
        "I can monitor webpages for you and notify you when they change.\n\n"
        "**Commands:**\n"
        "`/follow` - Start monitoring a URL\n"
        "`/remove` - Stop monitoring\n"
        "`/list` - Show your monitored pages\n"
        "`/update` - Change check frequency",
        parse_mode=ParseMode.MARKDOWN,
    )


async def follow_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the follow conversation."""
    if context.args:
        await update.message.reply_text("Please use the interactive mode. Just type `/follow` and I will guide you.", parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    await update.message.reply_text(
        "Please send me the **URL** you want to monitor (e.g., https://example.com).",
        parse_mode=ParseMode.MARKDOWN,
    )
    return FOLLOW_URL


async def follow_url_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the URL input."""
    url = update.message.text.strip()

    # Basic URL validation
    if not url.startswith("http"):
        await update.message.reply_text("❌ Invalid URL. Must start with http:// or https://\nPlease try again.")
        return FOLLOW_URL

    # Verify URL is reachable
    status_msg = await update.message.reply_text(f"🔍 Verifying {url}...")
    content = PageMonitor.fetch_content(url)
    
    if not content:
        await status_msg.edit_text("❌ Could not fetch URL. Please check if it works and try again.")
        return FOLLOW_URL

    # Save provisional URL in context
    context.user_data["follow_url"] = url
    context.user_data["follow_content"] = content

    await status_msg.edit_text(
        f"✅ URL verified: {url}\n\n"
        "Now, please send me the **check frequency** in minutes (minimum 5)."
    )
    return FOLLOW_FREQ



async def follow_freq_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the frequency input and saves the monitor."""
    try:
        interval = int(update.message.text.strip())
        if interval < 5:
            await update.message.reply_text("❌ Minimum interval is 5 minutes. Please try again.")
            return FOLLOW_FREQ
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return FOLLOW_FREQ

    url = context.user_data["follow_url"]
    content = context.user_data["follow_content"]
    user_id = update.effective_chat.id
    
    current_hash = PageMonitor.get_content_hash(PageMonitor.clean_content(content))

    # Save to DB
    async with async_session() as session:
        # Check if already exists
        result = await session.execute(
            select(Monitor).where(
                Monitor.user_id == user_id,
                Monitor.url == url
            )
        )
        existing = result.scalars().first()
        
        if existing:
            existing.frequency = interval
            existing.is_active = True
            existing.content_hash = current_hash
            existing.last_checked = datetime.now()
            monitor_id = existing.id
            await session.commit()
            await update.message.reply_text(f"✅ Updated existing monitor for {url} to {interval} minutes.")
        else:
            new_monitor = Monitor(
                user_id=user_id,
                url=url,
                frequency=interval,
                last_checked=datetime.now(),
                content_hash=current_hash,
                is_active=True
            )
            session.add(new_monitor)
            await session.commit()
            await session.refresh(new_monitor)
            monitor_id = new_monitor.id
            await update.message.reply_text(f"✅ Started monitoring {url} every {interval} minutes.")

    # Schedule Job
    schedule_monitor_job(context.application, monitor_id, url, user_id, interval)
    
    # Clean up
    del context.user_data["follow_url"]
    del context.user_data["follow_content"]
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels and ends the conversation."""
    await update.message.reply_text("❌ Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END




async def get_monitor_keyboard(user_id: int):
    """Helper to get a keyboard of monitors."""
    async with async_session() as session:
        result = await session.execute(select(Monitor).where(Monitor.user_id == user_id, Monitor.is_active == True))
        monitors = result.scalars().all()
    
    keyboard = []
    for m in monitors:
        # Callback data: "action|id"
        keyboard.append([InlineKeyboardButton(f"{m.url} ({m.frequency}m)", callback_data=str(m.id))])
    
    return InlineKeyboardMarkup(keyboard) if keyboard else None


async def remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the remove conversation."""
    user_id = update.effective_chat.id
    keyboard = await get_monitor_keyboard(user_id)
    
    if not keyboard:
        await update.message.reply_text("You have no active monitors to remove.")
        return ConversationHandler.END
        
    await update.message.reply_text("Select a URL to stop monitoring:", reply_markup=keyboard)
    return REMOVE_SELECT


async def remove_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the removal selection."""
    query = update.callback_query
    await query.answer()
    
    monitor_id = int(query.data)
    user_id = update.effective_chat.id
    
    async with async_session() as session:
        monitor = await session.get(Monitor, monitor_id)
        if monitor and monitor.user_id == user_id:
            monitor.is_active = False # Soft delete or check logic
            # Actually we can just delete or set inactive. Let's delete for now as per previous logic.
            # But previous logic had `await session.delete(monitor)`.
            # Let's match previous logic:
            await session.delete(monitor)
            await session.commit()
            
            # Remove job
            remove_jobs_by_name(context.application, str(monitor_id))
            
            await query.edit_message_text(f"🗑️ Stopped monitoring {monitor.url}.")
        else:
            await query.edit_message_text("❌ Monitor not found or already deleted.")
            
    return ConversationHandler.END


async def update_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the update conversation."""
    user_id = update.effective_chat.id
    keyboard = await get_monitor_keyboard(user_id)
    
    if not keyboard:
        await update.message.reply_text("You have no active monitors to update.")
        return ConversationHandler.END
        
    await update.message.reply_text("Select a URL to update:", reply_markup=keyboard)
    return UPDATE_SELECT


async def update_ask_freq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for new frequency."""
    query = update.callback_query
    await query.answer()
    
    monitor_id = int(query.data)
    context.user_data["update_monitor_id"] = monitor_id
    
    await query.edit_message_text("Please enter the new frequency in minutes (min 5):")
    return UPDATE_FREQ


async def update_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the new frequency."""
    try:
        interval = int(update.message.text.strip())
        if interval < 5:
            await update.message.reply_text("❌ Minimum interval is 5 minutes. Please try again.")
            return UPDATE_FREQ
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return UPDATE_FREQ
        
    monitor_id = context.user_data["update_monitor_id"]
    user_id = update.effective_chat.id
    
    async with async_session() as session:
        monitor = await session.get(Monitor, monitor_id)
        if monitor and monitor.user_id == user_id:
            monitor.frequency = interval
            await session.commit()
            
            # Reschedule
            schedule_monitor_job(context.application, monitor.id, monitor.url, user_id, interval)
            
            await update.message.reply_text(f"✅ Updated frequency to {interval} minutes for {monitor.url}.")
        else:
            await update.message.reply_text("❌ Monitor not found.")
            
    del context.user_data["update_monitor_id"]
    return ConversationHandler.END


async def list_monitors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all monitored URLs."""
    if not update.effective_chat or not update.message:
        return
    
    user_id = update.effective_chat.id

    async with async_session() as session:
        result = await session.execute(
            select(Monitor).where(Monitor.user_id == user_id)
        )
        monitors = result.scalars().all()

    if not monitors:
        await update.message.reply_text("You are not monitoring any URLs.")
        return

    msg = "**Your Monitored Pages:**\n"
    for m in monitors:
        status = "✅ Active" if m.is_active else "❌ Inactive"
        msg += f"- {m.url} ({m.frequency}m) [{status}]\n"
        
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# --- Job Logic ---

async def check_url_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to check a specific URL."""
    if not context.job or not context.job.data:  # pragma: no cover
        return
        
    job_data = context.job.data
    url = job_data["url"]
    user_id = job_data["user_id"]
    monitor_id = job_data["monitor_id"]

    logger.info(f"Checking {url} for user {user_id}")

    # Fetch DB state
    async with async_session() as session:
        monitor = await session.get(Monitor, monitor_id)
        if not monitor or not monitor.is_active:
            # Monitor deleted or inactive, stop job
            context.job.schedule_removal()
            return

        old_hash = monitor.content_hash

    # Check for changes
    new_hash, changed, summary = PageMonitor.check_for_changes(url, old_hash)

    if changed:
        # Notify User
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 **UPDATE DETECTED!**\n\n{url}\n\n{summary}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to send notification to {user_id}: {e}")

        # Update DB
        async with async_session() as session:
            monitor = await session.get(Monitor, monitor_id)
            if monitor:
                monitor.content_hash = new_hash
                monitor.last_checked = datetime.now()
                await session.commit()
    elif new_hash != old_hash:
        # Update hash even if "not changed" (e.g. initial run) to be safe, 
        # though PageMonitor logic handles the 'First Run' false return.
        # If PageMonitor returns False but new_hash != old_hash (e.g. first run), we should save it.
        async with async_session() as session:
            monitor = await session.get(Monitor, monitor_id)
            if monitor:
                monitor.content_hash = new_hash
                monitor.last_checked = datetime.now()
                await session.commit()


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    """Sends a daily report to the admin."""
    if not ADMIN_CHAT_ID:
        return

    async with async_session() as session:
        # Get stats
        total_monitors = await session.execute(select(Monitor))
        total_monitors_count = len(total_monitors.scalars().all())
        
        active_monitors = await session.execute(select(Monitor).where(Monitor.is_active.is_(True)))
        active_monitors_count = len(active_monitors.scalars().all())

    msg = (
        "📊 **Daily Scraper Bot Report**\n\n"
        f"✅ Bot is alive and running.\n"
        f"Total Monitors: {total_monitors_count}\n"
        f"Active Monitors: {active_monitors_count}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Failed to send admin report: {e}")


def schedule_monitor_job(application, monitor_id, url, user_id, interval):
    """Schedules a repeating job for a monitor."""
    # Ensure no duplicates
    remove_jobs_by_name(application, str(monitor_id))
    
    application.job_queue.run_repeating(
        check_url_job,
        interval=interval * 60,
        first=10, # Wait 10s before first check to avoid startup spikes
        data={"url": url, "user_id": user_id, "monitor_id": monitor_id}, # type: ignore
        name=str(monitor_id)
    )


def remove_jobs_by_name(application, name):
    """Removes all jobs with the given name."""
    jobs = application.job_queue.get_jobs_by_name(name)
    for job in jobs:
        job.schedule_removal()


async def restore_jobs(application: Application):
    """Restores all active monitors from DB on startup."""
    logger.info("Restoring jobs from database...")
    monitors = await get_all_active_monitors()
    count = 0
    for m in monitors:
        schedule_monitor_job(application, m.id, m.url, m.user_id, m.frequency)
        count += 1
    logger.info(f"Restored {count} monitoring jobs.")


async def post_init(application: Application):
    """Post initialization hook."""
    await init_db()
    await restore_jobs(application)
    
    # Set bot commands
    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("follow", "Track a URL"),
        BotCommand("remove", "Stop tracking"),
        BotCommand("list", "List tracked URLs"),
        BotCommand("update", "Update frequency"),
        BotCommand("help", "Show available commands"),
    ]
    await application.bot.set_my_commands(commands)


def main():  # pragma: no cover
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)

    # Build Application
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commands
    application.add_handler(CommandHandler("start", start))
    # Handlers
    
    # Follow Conversation
    follow_conv = ConversationHandler(
        entry_points=[CommandHandler("follow", follow_start)],
        states={
            FOLLOW_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, follow_url_input)],
            FOLLOW_FREQ: [MessageHandler(filters.TEXT & ~filters.COMMAND, follow_freq_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(follow_conv)

    application.add_handler(CommandHandler("start", start))
    # application.add_handler(CommandHandler("follow", follow)) # Replaced by conv
    # Remove Conversation
    remove_conv = ConversationHandler(
        entry_points=[CommandHandler("remove", remove_start)],
        states={
            REMOVE_SELECT: [CallbackQueryHandler(remove_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(remove_conv)
    
    # Update Conversation
    update_conv = ConversationHandler(
        entry_points=[CommandHandler("update", update_start)],
        states={
            UPDATE_SELECT: [CallbackQueryHandler(update_ask_freq)],
            UPDATE_FREQ: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_save)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(update_conv)

    # application.add_handler(CommandHandler("remove", remove_monitor)) # Replaced
    application.add_handler(CommandHandler("list", list_monitors))
    # application.add_handler(CommandHandler("update", follow)) # Replaced
    application.add_handler(CommandHandler("help", start)) # Help -> same as start

    # Daily Report Job
    if ADMIN_CHAT_ID:
        # Run daily at 9:00 AM UTC approx (or just interval)
        application.job_queue.run_repeating(daily_report_job, interval=86400, first=10)

    logger.info("Bot started!")
    application.run_polling()


if __name__ == "__main__":  # pragma: no cover
    main()
