import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from handlers import start, create_template_start, template_name, exercise_name
from telegram.ext import ConversationHandler

@pytest.mark.asyncio
async def test_start_command(mock_update, mock_context):
    # Mock database session
    with patch("handlers.AsyncSessionLocal") as mock_session_cls:
        # Create the precise result object we expect
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        
        # Create session mock
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        # Ensure execute returns a mock that has the correct method
        mock_session.execute.return_value = mock_result
        
        # Setup context manager
        mock_manager = AsyncMock()
        mock_manager.__aenter__.return_value = mock_session
        mock_manager.__aexit__.return_value = None
        mock_session_cls.return_value = mock_manager

        await start(mock_update, mock_context)
        
        # Verify user creation
        assert mock_session.add.called
        assert mock_session.commit.called
        mock_update.message.reply_text.assert_called_once()
        assert "Welcome to GymBot" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_create_template_flow(mock_update, mock_context):
    # Test create_template_start
    state = await create_template_start(mock_update, mock_context)
    assert state == 0 # TEMPLATE_NAME
    assert "What specific name" in mock_update.message.reply_text.call_args[0][0]

    # Test template_name
    mock_update.message.text = "Leg Day"
    state = await template_name(mock_update, mock_context)
    assert state == 1 # EXERCISE_NAME
    assert mock_context.user_data['template_name'] == "Leg Day"
    
    # Test exercise_name
    mock_update.message.text = "Squat"
    state = await exercise_name(mock_update, mock_context)
    assert state == 2 # EXERCISE_DETAILS
    assert mock_context.user_data['current_exercise_name'] == "Squat"
