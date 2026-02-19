import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from handlers import add_template_ai_start, process_ai_template, ADD_TEMPLATE_AI_INPUT, EDIT_TEMPLATE_EXERCISE
import json

@pytest.mark.asyncio
async def test_add_template_ai_start(mock_update, mock_context):
    state = await add_template_ai_start(mock_update, mock_context)
    assert state == ADD_TEMPLATE_AI_INPUT
    assert "Please describe your workout" in mock_update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_process_ai_template_success(mock_update, mock_context):
    mock_update.message.text = "Push Day: 3 sets of Bench Press 80kg for 10 reps"
    mock_context.bot = AsyncMock()
    
    # Mock OpenAI client response
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({
            "template_name": "Push Day",
            "exercises": [
                {
                    "name": "Bench Press",
                    "sets": 3,
                    "sets_config": [{"weight": 80.0, "reps": 10}, {"weight": 80.0, "reps": 10}, {"weight": 80.0, "reps": 10}]
                }
            ]
        })))
    ]
    
    with patch("handlers.get_client") as mock_get_client:
        mock_ai_client = AsyncMock()
        mock_get_client.return_value = mock_ai_client
        mock_ai_client.chat.completions.create.return_value = mock_response
        
        # Mock save_template to avoid DB interaction in this test
        with patch("handlers.save_template", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = -1 # Simulation of ConversationHandler.END (usually -1)
            
            state = await process_ai_template(mock_update, mock_context)
            
            assert state == EDIT_TEMPLATE_EXERCISE
            assert mock_context.user_data["template_name"] == "Push Day"
            assert len(mock_context.user_data["exercises"]) == 1
            assert mock_update.message.reply_text.called
            # The first reply_text is the confirmation, but wait, 
            # handlers.py calls update.message.reply_text twice if successful (once in confirm, once in save_template if mocked)
            # Actually, process_ai_template calls it once, then returns save_template.
            assert any("parsed your workout" in str(call) for call in mock_update.message.reply_text.call_args_list)

@pytest.mark.asyncio
async def test_process_ai_template_error(mock_update, mock_context):
    mock_update.message.text = "invalid input"
    mock_context.bot = AsyncMock()
    
    with patch("handlers.get_client") as mock_get_client:
        mock_ai_client = AsyncMock()
        mock_get_client.return_value = mock_ai_client
        mock_ai_client.chat.completions.create.side_effect = Exception("API Error")
        
        state = await process_ai_template(mock_update, mock_context)
        assert state == ADD_TEMPLATE_AI_INPUT
        assert any("Sorry, I had trouble understanding" in str(call) for call in mock_update.message.reply_text.call_args_list)
