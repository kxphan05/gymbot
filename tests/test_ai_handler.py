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
    
    with patch("handlers.ai_template.get_client") as mock_get_client:
        mock_ai_client = AsyncMock()
        mock_get_client.return_value = mock_ai_client
        mock_ai_client.chat.completions.create.return_value = mock_response
        
        state = await process_ai_template(mock_update, mock_context)
        
        assert state == EDIT_TEMPLATE_EXERCISE
        assert mock_context.user_data["template_name"] == "Push Day"
        assert len(mock_context.user_data["exercises"]) == 1
        assert mock_update.message.reply_text.called
        assert any("parsed your workout" in str(call) for call in mock_update.message.reply_text.call_args_list)

@pytest.mark.asyncio
async def test_process_ai_template_error(mock_update, mock_context):
    mock_update.message.text = "invalid input"
    mock_context.bot = AsyncMock()
    
    with patch("handlers.ai_template.get_client") as mock_get_client:
        mock_ai_client = AsyncMock()
        mock_get_client.return_value = mock_ai_client
        mock_ai_client.chat.completions.create.side_effect = Exception("API Error")
        
        state = await process_ai_template(mock_update, mock_context)
        assert state == ADD_TEMPLATE_AI_INPUT
        assert any("Sorry, I had trouble understanding" in str(call) for call in mock_update.message.reply_text.call_args_list)

@pytest.mark.asyncio
async def test_process_ai_template_photo(mock_update, mock_context):
    mock_update.message.photo = [MagicMock()]
    mock_update.message.document = None
    mock_context.bot = AsyncMock()
    
    # Mock file download
    mock_file = AsyncMock()
    mock_context.bot.get_file.return_value = mock_file
    mock_file.download_to_memory = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({
            "template_name": "Photo Template",
            "exercises": [
                {
                    "name": "Squat",
                    "sets": 3,
                    "sets_config": [{"weight": 100.0, "reps": 5}]
                }
            ]
        })))
    ]
    
    with patch("handlers.ai_template.get_client") as mock_get_client:
        mock_ai_client = AsyncMock()
        mock_get_client.return_value = mock_ai_client
        mock_ai_client.chat.completions.create.return_value = mock_response
        
        # Import process_ai_template_file
        from handlers import process_ai_template_file
        state = await process_ai_template_file(mock_update, mock_context)
        
        assert state == EDIT_TEMPLATE_EXERCISE
        assert mock_context.user_data["template_name"] == "Photo Template"

@pytest.mark.asyncio
async def test_process_ai_template_csv(mock_update, mock_context):
    mock_update.message.photo = None
    mock_document = MagicMock()
    mock_document.mime_type = "text/csv"
    mock_document.file_name = "workout.csv"
    mock_update.message.document = mock_document
    mock_context.bot = AsyncMock()
    
    # Mock file download with CSV content
    mock_file = AsyncMock()
    mock_context.bot.get_file.return_value = mock_file
    
    csv_content = "exercise,sets,reps,weight\nBench Press,3,10,80"
    
    async def side_effect(bio):
        bio.write(csv_content.encode("utf-8"))
        return None
        
    mock_file.download_to_memory.side_effect = side_effect
    
    from handlers import process_ai_template_file
    state = await process_ai_template_file(mock_update, mock_context)
    
    assert state == EDIT_TEMPLATE_EXERCISE
    assert mock_context.user_data["template_name"] == "CSV Import"
    assert len(mock_context.user_data["exercises"]) == 1
    assert mock_context.user_data["exercises"][0]["name"] == "Bench Press"
