import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Chat, Message
from telegram.ext import ContextTypes

@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = 123456789
    update.effective_user.username = "testuser"
    update.message = AsyncMock(spec=Message)
    update.message.reply_text = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {}
    return context
