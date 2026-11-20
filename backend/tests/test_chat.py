import json
import pytest


def test_chat_validation_missing_fields(client):
    # Missing message
    resp = client.post("/chat", json={"session_id": "s-1"})
    assert resp.status_code == 422
    assert "detail" in resp.json()

    # Missing session_id
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_chat_validation_empty_or_whitespace_message(client):
    # Empty string
    resp = client.post("/chat", json={"session_id": "s-1", "message": ""})
    assert resp.status_code == 422
    assert "detail" in resp.json()

    # Whitespace only
    resp = client.post("/chat", json={"session_id": "s-1", "message": "   \n\t  "})
    assert resp.status_code == 422
    assert "detail" in resp.json()

    # Verify nothing added to session history
    hist = client.get("/sessions/s-1/messages")
    assert hist.status_code == 404


def test_chat_validation_message_too_long(client):
    long_msg = "a" * 4001
    resp = client.post("/chat", json={"session_id": "s-1", "message": long_msg})
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_chat_validation_session_id_bounds(client):
    # Empty session_id
    resp = client.post("/chat", json={"session_id": "", "message": "hello"})
    assert resp.status_code == 422

    # Session ID > 128 chars
    long_id = "s" * 129
    resp = client.post("/chat", json={"session_id": long_id, "message": "hello"})
    assert resp.status_code == 422


def test_live_inference_success(client, mock_litellm):
    payload = {
        "session_id": "s-test-1",
        "message": "What is the capital of France?",
    }
    resp = client.post("/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["session_id"] == "s-test-1"
    assert "Echo: What is the capital of France?" in data["reply"]
    meta = data["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["key_id"] == "key_1"
    assert meta["fallback_attempts"] == 0
    assert meta["latency_ms"] >= 0
    assert meta["input_tokens"] > 0
    assert meta["output_tokens"] > 0
    assert meta["model"] == "gemini/gemini-2.0-flash"

    # Verify session history was saved
    hist = client.get("/sessions/s-test-1/messages")
    assert hist.status_code == 200
    msgs = hist.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "What is the capital of France?"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_response_caching_identical_first_message(client, mock_litellm):
    # Session 1: Live call
    resp1 = client.post("/chat", json={"session_id": "session-A", "message": "Cache test message"})
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert data1["metadata"]["key_id"] == "key_1"
    call_count_before = mock_litellm.call_count

    # Session 2: Identical message in a new session should hit cache!
    resp2 = client.post("/chat", json={"session_id": "session-B", "message": "Cache test message"})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["metadata"]["resolution_source"] == "LLM_CACHE"
    assert data2["metadata"]["key_id"] is None
    assert data2["metadata"]["fallback_attempts"] == 0
    assert data2["reply"] == data1["reply"]
    assert data2["metadata"]["input_tokens"] == data1["metadata"]["input_tokens"]
    assert data2["metadata"]["output_tokens"] == data1["metadata"]["output_tokens"]
    # LiteLLM completion should NOT have been called again
    assert mock_litellm.call_count == call_count_before


def test_different_message_does_not_hit_cache(client, mock_litellm):
    # First message
    resp1 = client.post("/chat", json={"session_id": "session-C", "message": "Message Alpha"})
    assert resp1.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"

    # Second different message
    resp2 = client.post("/chat", json={"session_id": "session-C", "message": "Message Beta"})
    assert resp2.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_multi_turn_conversation_context(client, mock_litellm):
    # Turn 1
    resp1 = client.post("/chat", json={"session_id": "multi-1", "message": "My favorite color is blue."})
    assert resp1.status_code == 200

    # Turn 2
    resp2 = client.post("/chat", json={"session_id": "multi-1", "message": "What did I just say?"})
    assert resp2.status_code == 200

    # Check mock called with full conversation context (turn 1 user + turn 1 assistant + turn 2 user)
    last_call_messages = mock_litellm.call_args_list[-1][1]["messages"]
    roles = [m["role"] for m in last_call_messages]
    assert roles == ["user", "assistant", "user"]
    assert last_call_messages[0]["content"] == "My favorite color is blue."
    assert last_call_messages[2]["content"] == "What did I just say?"

    # Check database history has all 4 messages
    hist = client.get("/sessions/multi-1/messages")
    assert hist.status_code == 200
    history_msgs = hist.json()["messages"]
    assert len(history_msgs) == 4
    assert [m["role"] for m in history_msgs] == ["user", "assistant", "user", "assistant"]
