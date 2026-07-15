import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.classifier.llm_scorer import LLMScorer


def _make_json_response(data: dict):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = data
    return mock


@pytest.fixture
def scorer():
    return LLMScorer(api_key="test-key", model="openai/gpt-4o-mini")


@pytest.mark.asyncio
async def test_score_returns_parsed_importance(scorer):
    mock_resp = _make_json_response({
        "choices": [{
            "message": {
                "content": '{"importance": 7, "summary": "Urgent meeting request", "reason": "Manager explicitly requests immediate response"}'
            }
        }]
    })

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        result = await scorer.score(
            text="Hi, need you to join the meeting ASAP",
            sender="boss@example.com",
            group_name="Work Chat"
        )

    assert result["score"] == 7
    assert result["summary"] == "Urgent meeting request"
    assert result["reason"] == "Manager explicitly requests immediate response"


@pytest.mark.asyncio
async def test_score_clamps_importance_below_zero(scorer):
    mock_resp = _make_json_response({
        "choices": [{
            "message": {
                "content": '{"importance": -5, "summary": "Low priority", "reason": "Not relevant"}'
            }
        }]
    })

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        result = await scorer.score(
            text="some text",
            sender="user@example.com",
            group_name="Random"
        )

    assert result["score"] == 0


@pytest.mark.asyncio
async def test_score_clamps_importance_above_ten(scorer):
    mock_resp = _make_json_response({
        "choices": [{
            "message": {
                "content": '{"importance": 15, "summary": "Very important", "reason": "Critical"}'
            }
        }]
    })

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        result = await scorer.score(
            text="URGENT!",
            sender="ceo@example.com",
            group_name="Exec"
        )

    assert result["score"] == 10


@pytest.mark.asyncio
async def test_score_returns_zero_on_api_error(scorer):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        result = await scorer.score(
            text="test message here",
            sender="user@example.com",
            group_name="General"
        )

    assert result["score"] == 0
    assert "error" in result
    assert result["summary"] == "test message here"
