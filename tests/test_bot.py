import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot import (
    start, follow_start, follow_url_input, follow_freq_input,
    remove_start, remove_confirm,
    update_start, update_ask_freq, update_save,
    check_url_job, list_monitors,
    FOLLOW_URL, FOLLOW_FREQ, REMOVE_SELECT, UPDATE_SELECT, UPDATE_FREQ
)
from telegram.ext import ConversationHandler
import bot

# Mock the database setup
@pytest.fixture
async def mock_db(monkeypatch):
    # Mock session
    mock_session = AsyncMock()
    # Configure execute return value (Result)
    mock_result = MagicMock()
    mock_session.execute.return_value = mock_result
    # Configure scalars (Result.scalars() is sync)
    mock_scalars = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None
    
    mock_session_maker = MagicMock(return_value=mock_session_ctx)
    
    monkeypatch.setattr(bot, "async_session", mock_session_maker)
    return mock_session

@pytest.mark.asyncio
async def test_start(mock_db):
    update = AsyncMock()
    context = MagicMock()
    await start(update, context)
    update.message.reply_text.assert_called_once()
    assert "/follow` - Start monitoring" in update.message.reply_text.call_args[0][0]
    assert "/remove` - Stop monitoring" in update.message.reply_text.call_args[0][0]
    assert "/update` - Change check frequency" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_follow_args_rejected():
    update = AsyncMock()
    context = MagicMock()
    context.args = ["arg1"]
    
    state = await follow_start(update, context)
    
    assert state == ConversationHandler.END
    assert "Please use the interactive mode" in update.message.reply_text.call_args[0][0]

# --- Follow Conversation Tests ---

@pytest.mark.asyncio
async def test_follow_start():
    update = AsyncMock()
    context = MagicMock()
    state = await follow_start(update, context)
    assert state == FOLLOW_URL
    assert "Please send me the **URL**" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_follow_url_input_invalid():
    update = AsyncMock()
    update.message.text = "ftp://bad.com"
    context = MagicMock()
    state = await follow_url_input(update, context)
    assert state == FOLLOW_URL
    assert "Invalid URL" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
@patch("bot.PageMonitor.fetch_content", return_value="<html>ok</html>")
async def test_follow_url_input_valid(mock_fetch, mock_db):
    update = AsyncMock()
    update.message.text = "http://good.com"
    context = MagicMock()
    context.user_data = {}
    
    state = await follow_url_input(update, context)
    
    assert state == FOLLOW_FREQ
    assert context.user_data["follow_url"] == "http://good.com"
    # Verification message (edit_text is called on the 'verifying' message)
    # The code does: reply_text("verifying") -> msg; msg.edit_text("success")
    # We need to check if edit_text was called on the return value of reply_text
    status_msg = update.message.reply_text.return_value
    status_msg.edit_text.assert_called()

@pytest.mark.asyncio
async def test_follow_freq_input_success(mock_db):
    update = AsyncMock()
    update.message.text = "30"
    update.effective_chat.id = 123
    context = MagicMock()
    context.user_data = {"follow_url": "http://u.com", "follow_content": "ok"}
    
    # Mock DB: no existing monitor
    mock_db.execute.return_value.scalars.return_value.first.return_value = None
    
    with patch("bot.PageMonitor.get_content_hash", return_value="hash"):
        with patch("bot.schedule_monitor_job") as mock_schedule:
            state = await follow_freq_input(update, context)
            
    assert state == ConversationHandler.END
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
    mock_schedule.assert_called_once()

# --- Remove Conversation Tests ---

@pytest.mark.asyncio
async def test_remove_start_no_monitors(mock_db):
    update = AsyncMock()
    update.effective_chat.id = 123
    context = MagicMock()
    # Return empty list
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    
    state = await remove_start(update, context)
    assert state == ConversationHandler.END
    assert "no active monitors" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_remove_start_with_monitors(mock_db):
    update = AsyncMock()
    update.effective_chat.id = 123
    context = MagicMock()
    
    m = MagicMock(id=1, url="u", frequency=60)
    mock_db.execute.return_value.scalars.return_value.all.return_value = [m]
    
    state = await remove_start(update, context)
    assert state == REMOVE_SELECT
    # Check reply_markup (InlineKeyboardMarkup)
    assert update.message.reply_text.call_args[1]["reply_markup"] is not None

@pytest.mark.asyncio
async def test_remove_confirm(mock_db):
    update = AsyncMock()
    update.effective_chat.id = 123
    query = update.callback_query
    query.data = "1"
    context = MagicMock()
    
    m = MagicMock(id=1, user_id=123, url="u")
    mock_db.get.return_value = m
    
    with patch("bot.remove_jobs_by_name") as mock_rm_job:
        state = await remove_confirm(update, context)
        
    assert state == ConversationHandler.END
    mock_db.delete.assert_called_with(m)
    mock_rm_job.assert_called_with(context.application, "1")

# --- Update Conversation Tests ---

@pytest.mark.asyncio
async def test_update_start(mock_db):
    update = AsyncMock()
    update.effective_chat.id = 123
    context = MagicMock()
    m = MagicMock(id=1, url="u", frequency=60)
    mock_db.execute.return_value.scalars.return_value.all.return_value = [m]
    
    state = await update_start(update, context)
    assert state == UPDATE_SELECT

@pytest.mark.asyncio
async def test_update_ask_freq(mock_db):
    update = AsyncMock()
    query = update.callback_query
    query.data = "1"
    context = MagicMock()
    context.user_data = {}
    
    state = await update_ask_freq(update, context)
    assert state == UPDATE_FREQ
    assert context.user_data["update_monitor_id"] == 1

@pytest.mark.asyncio
async def test_update_save(mock_db):
    update = AsyncMock()
    update.message.text = "120"
    update.effective_chat.id = 123
    context = MagicMock()
    context.user_data = {"update_monitor_id": 1}
    
    m = MagicMock(id=1, user_id=123, url="u")
    mock_db.get.return_value = m
    
    with patch("bot.schedule_monitor_job") as mock_schedule:
        state = await update_save(update, context)
        
    assert state == ConversationHandler.END
    assert m.frequency == 120
    mock_db.commit.assert_called_once()
    mock_schedule.assert_called_once()

# --- Job/Other Tests ---

@pytest.mark.asyncio
async def test_check_url_job(mock_db):
    context = MagicMock()
    context.job.data = {"url": "u", "user_id": 1, "monitor_id": 1}
    m = MagicMock(is_active=True, content_hash="old")
    mock_db.get.return_value = m
    
    with patch("bot.PageMonitor.check_for_changes", return_value=("new", True, "chg")):
        await check_url_job(context)
        
    context.bot.send_message.assert_called_once()
    mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_list_monitors(mock_db):
    update = AsyncMock()
    context = MagicMock()
    update.effective_chat.id = 123
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    await list_monitors(update, context)
    assert "not monitoring any URLs" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_post_init(mock_db):
    app = MagicMock()
    app.bot.set_my_commands = AsyncMock()
    with patch("bot.init_db", new_callable=AsyncMock), patch("bot.restore_jobs", new_callable=AsyncMock):
        await bot.post_init(app)
        app.bot.set_my_commands.assert_called_once()

@pytest.mark.asyncio
async def test_daily_report_job(mock_db):
    context = MagicMock()
    # Mock admin chat id
    with patch("bot.ADMIN_CHAT_ID", "123"):
        # Mock monitors
        mock_db.execute.return_value.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
        await bot.daily_report_job(context)
        context.bot.send_message.assert_called_once()
        assert "Total Monitors: 2" in context.bot.send_message.call_args[1]["text"]

@pytest.mark.asyncio
async def test_restore_jobs(mock_db):
    app = MagicMock()
    m = MagicMock(id=1, url="u", user_id=1, frequency=60)
    with patch("bot.get_all_active_monitors", return_value=[m]):
        with patch("bot.schedule_monitor_job") as mock_schedule:
            await bot.restore_jobs(app)
            mock_schedule.assert_called_once()

@pytest.mark.asyncio
async def test_remove_jobs_by_name():
    app = MagicMock()
    job = MagicMock()
    app.job_queue.get_jobs_by_name.return_value = [job]
    bot.remove_jobs_by_name(app, "name")
    job.schedule_removal.assert_called_once()


@pytest.mark.asyncio
async def test_cancel():
    update = AsyncMock()
    context = MagicMock()
    state = await bot.cancel(update, context)
    assert state == ConversationHandler.END
    assert "cancelled" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_follow_freq_input_invalid_number():
    update = AsyncMock()
    update.message.text = "abc"
    context = MagicMock()
    state = await follow_freq_input(update, context)
    assert state == FOLLOW_FREQ
    assert "valid number" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_follow_freq_input_too_small():
    update = AsyncMock()
    update.message.text = "2"
    context = MagicMock()
    state = await follow_freq_input(update, context)
    assert state == FOLLOW_FREQ
    assert "Minimum interval" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_update_save_invalid():
    update = AsyncMock()
    update.message.text = "abc"
    context = MagicMock()
    state = await update_save(update, context)
    assert state == UPDATE_FREQ

@pytest.mark.asyncio
async def test_remove_confirm_not_found(mock_db):
    update = AsyncMock()
    query = update.callback_query
    query.data = "999"
    context = MagicMock()
    
    mock_db.get.return_value = None
    
    state = await remove_confirm(update, context)
    assert state == ConversationHandler.END
    assert "not found" in query.edit_message_text.call_args[0][0]

@pytest.mark.asyncio
async def test_update_save_not_found(mock_db):
    update = AsyncMock()
    update.message.text = "60"
    context = MagicMock()
    context.user_data = {"update_monitor_id": 999}
    
    mock_db.get.return_value = None
    
    state = await update_save(update, context)
    assert state == ConversationHandler.END
    assert "not found" in update.message.reply_text.call_args[0][0]
