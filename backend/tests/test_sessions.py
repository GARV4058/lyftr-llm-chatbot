def test_session_not_found(client):
    resp = client.get("/sessions/unknown-session-999/messages")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "session not found"}


def test_session_messages_format_and_order(client, mock_litellm):
    session_id = "s-order-test"
    
    # Send message with system_prompt
    client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "Step 1",
            "system_prompt": "You are a helpful assistant.",
        },
    )
    
    # Send message 2
    client.post(
        "/chat",
        json={
            "session_id": session_id,
            "message": "Step 2",
        },
    )

    resp = client.get(f"/sessions/{session_id}/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    messages = data["messages"]
    assert len(messages) == 4

    # System prompt MUST NOT be in messages
    for m in messages:
        assert m["role"] in ("user", "assistant")
        assert "helpful assistant" not in m["content"]

    # Order check (oldest first)
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Step 1"
    assert messages[1]["role"] == "assistant"
    assert "metadata" in messages[1]
    assert messages[1]["metadata"]["resolution_source"] == "LIVE_INFERENCE"

    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "Step 2"
    assert messages[3]["role"] == "assistant"
