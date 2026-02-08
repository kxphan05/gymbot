import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from handlers import (
    start,
    create_template_start,
    template_name,
    exercise_name,
    show_edited_template,
    rest_timer_callback,
)
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
    assert state == 0  # TEMPLATE_NAME
    assert "What specific name" in mock_update.message.reply_text.call_args[0][0]

    # Test template_name
    mock_update.message.text = "Leg Day"
    state = await template_name(mock_update, mock_context)
    assert state == 1  # EXERCISE_NAME
    assert mock_context.user_data["template_name"] == "Leg Day"

    # Test exercise_name
    mock_update.message.text = "Squat"
    state = await exercise_name(mock_update, mock_context)
    assert state == 2  # EXERCISE_DETAILS
    assert mock_context.user_data["current_exercise_name"] == "Squat"


@pytest.mark.asyncio
async def test_volume_calculation_template(mock_update, mock_context):
    """Test that volume is calculated correctly for template exercises."""
    mock_context.user_data["editing_exercises"] = [
        {"name": "Squat", "sets": 3, "weight": 100.0, "reps": 5},
        {"name": "Bench Press", "sets": 4, "weight": 80.0, "reps": 8},
    ]
    mock_context.user_data["editing_template_name"] = "Leg Day"

    mock_message = AsyncMock()

    await show_edited_template(mock_update, mock_context, mock_message)

    call_args = mock_message.reply_text.call_args
    reply_markup = call_args[1]["reply_markup"]
    button_texts = [
        button.text for row in reply_markup.inline_keyboard for button in row
    ]
    assert any("Squat (3x100.0kgx5) - 1500.0kg vol" in text for text in button_texts)
    assert any(
        "Bench Press (4x80.0kgx8) - 2560.0kg vol" in text for text in button_texts
    )


@pytest.mark.asyncio
async def test_volume_calculation_zero_weight(mock_update, mock_context):
    """Test volume calculation with zero weight exercises."""
    mock_context.user_data["editing_exercises"] = [
        {"name": "Pull-ups", "sets": 3, "weight": 0.0, "reps": 10},
    ]
    mock_context.user_data["editing_template_name"] = "Upper Body"

    mock_message = AsyncMock()

    await show_edited_template(mock_update, mock_context, mock_message)

    call_args = mock_message.reply_text.call_args
    reply_markup = call_args[1]["reply_markup"]
    button_texts = [
        button.text for row in reply_markup.inline_keyboard for button in row
    ]
    assert any("Pull-ups (3x0.0kgx10) - 0.0kg vol" in text for text in button_texts)


@pytest.mark.asyncio
async def test_rest_timer_callback_deletes_message(mock_context):
    """Test that rest timer callback deletes the rest message."""
    mock_context.user_data = {
        "rest_message_id": 123,
        "rest_job": MagicMock(),
    }
    mock_context.job = MagicMock()
    mock_context.job.chat_id = 12345
    mock_context.bot = AsyncMock()

    await rest_timer_callback(mock_context)

    mock_context.bot.delete_message.assert_called_once_with(12345, 123)
    assert "rest_message_id" not in mock_context.user_data
    assert "rest_job" not in mock_context.user_data


@pytest.mark.asyncio
async def test_rest_timer_callback_handles_missing_message(mock_context):
    """Test that rest timer callback handles missing message gracefully."""
    mock_context.user_data = {}
    mock_context.job = MagicMock()
    mock_context.job.chat_id = 12345
    mock_context.bot = AsyncMock()

    await rest_timer_callback(mock_context)

    mock_context.bot.delete_message.assert_not_called()
