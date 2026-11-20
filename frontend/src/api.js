const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (typeof window !== 'undefined' && window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '');

/**
 * Fetch backend health status
 */
export async function getHealthStatus() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`);
    if (!res.ok) {
      throw new Error(`Health check returned ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    console.error('Failed to fetch health status:', err);
    return null;
  }
}

/**
 * Send a chat message
 */
export async function sendChatMessage({
  sessionId,
  message,
  systemPrompt,
  simulateFailure,
}) {
  const headers = {
    'Content-Type': 'application/json',
  };

  if (simulateFailure && simulateFailure.trim()) {
    headers['X-Simulate-Failure'] = simulateFailure.trim();
  }

  const body = {
    session_id: sessionId,
    message: message,
  };

  if (systemPrompt && systemPrompt.trim()) {
    body.system_prompt = systemPrompt.trim();
  }

  const res = await fetch(`${BACKEND_URL}/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    let errorMessage = 'An unexpected error occurred.';
    if (data && data.detail) {
      if (typeof data.detail === 'string') {
        errorMessage = data.detail;
      } else if (Array.isArray(data.detail)) {
        errorMessage = data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
      } else {
        errorMessage = JSON.stringify(data.detail);
      }
    } else {
      errorMessage = `Server returned HTTP ${res.status}`;
    }

    const error = new Error(errorMessage);
    error.status = res.status;
    error.data = data;
    throw error;
  }

  return data;
}

/**
 * Fetch messages for a specific session
 */
export async function getSessionMessages(sessionId) {
  const res = await fetch(`${BACKEND_URL}/sessions/${sessionId}/messages`);
  if (res.status === 404) {
    return { session_id: sessionId, messages: [] };
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error((data && data.detail) || `HTTP error ${res.status}`);
  }
  return await res.json();
}
