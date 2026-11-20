import os
from unittest.mock import patch


def test_simulate_failure_key_1_429(client, mock_litellm):
    # key_1 fails with 429, key_2 should answer
    headers = {"X-Simulate-Failure": "key_1=429"}
    resp = client.post(
        "/chat",
        json={"session_id": "sim-1", "message": "Simulate failover test 1"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1
    assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_simulate_failure_key_1_500(client, mock_litellm):
    # key_1 fails with 500, key_2 should answer
    headers = {"X-Simulate-Failure": "key_1=500"}
    resp = client.post(
        "/chat",
        json={"session_id": "sim-2", "message": "Simulate failover test 2"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1


def test_simulate_failure_multiple_keys(client, mock_litellm):
    # key_1 and key_2 fail, key_3 should answer
    headers = {"X-Simulate-Failure": "key_1=429,key_2=500"}
    resp = client.post(
        "/chat",
        json={"session_id": "sim-3", "message": "Simulate failover test 3"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["key_id"] == "key_3"
    assert data["metadata"]["fallback_attempts"] == 2


def test_simulate_failure_wildcard_all_fail(client, mock_litellm):
    # All keys fail with 429 -> 503
    headers = {"X-Simulate-Failure": "*=429"}
    resp = client.post(
        "/chat",
        json={"session_id": "sim-fail-all", "message": "Will fail completely"},
        headers=headers,
    )
    assert resp.status_code == 503
    assert resp.json() == {"detail": "all providers unavailable"}

    # Verify NOTHING was saved to history
    hist = client.get("/sessions/sim-fail-all/messages")
    assert hist.status_code == 404


def test_simulate_failure_switch_disabled(client, mock_litellm):
    # When ENABLE_FAILURE_SIMULATION is false, header must be ignored
    with patch.dict(os.environ, {"ENABLE_FAILURE_SIMULATION": "false"}):
        headers = {"X-Simulate-Failure": "key_1=429"}
        resp = client.post(
            "/chat",
            json={"session_id": "sim-disabled", "message": "Simulation disabled"},
            headers=headers,
        )
        assert resp.status_code == 200
        # key_1 should have answered because simulation header was ignored
        assert resp.json()["metadata"]["key_id"] == "key_1"
        assert resp.json()["metadata"]["fallback_attempts"] == 0
