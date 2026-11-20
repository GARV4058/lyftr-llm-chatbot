import React, { useState, useEffect, useRef } from 'react';
import { getHealthStatus, sendChatMessage } from './api';
import './App.css';

// Generates a session ID on each page load (e.g. "s-7f3a1b")
function generateSessionId() {
  const rand = Math.random().toString(36).substring(2, 8);
  return `s-${rand}`;
}

export default function App() {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);
  const [simulateFailure, setSimulateFailure] = useState('');
  const [loading, setLoading] = useState(false);
  const [healthInfo, setHealthInfo] = useState(null);
  const messagesEndRef = useRef(null);

  // Initialize new session on page load
  useEffect(() => {
    const id = generateSessionId();
    setSessionId(id);
    checkHealth();
  }, []);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const checkHealth = async () => {
    const data = await getHealthStatus();
    setHealthInfo(data);
  };

  const handleStartNewSession = () => {
    const newId = generateSessionId();
    setSessionId(newId);
    setMessages([]);
    checkHealth();
  };

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const trimmed = inputText.trim();
    if (!trimmed || loading) return;

    // Add user message to UI
    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: trimmed,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText(''); // Clear input immediately
    setLoading(true);

    try {
      const response = await sendChatMessage({
        sessionId,
        message: trimmed,
        systemPrompt: systemPrompt.trim() || undefined,
        simulateFailure: simulateFailure.trim() || undefined,
      });

      // Successful assistant reply
      const assistantMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.reply,
        metadata: response.metadata,
        timestamp: new Date().toLocaleTimeString(),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      console.error('Chat error:', err);
      // Display human-readable error message in chat without crashing
      const errorMsg = {
        id: Date.now() + 1,
        role: 'error',
        status: err.status || 500,
        content:
          err.status === 422
            ? `Validation Error (HTTP 422): ${err.message}`
            : err.status === 503
            ? `Service Outage (HTTP 503): ${err.message}`
            : `Request Failed: ${err.message}`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="app-container">
      {/* Top Navigation / Header */}
      <header className="app-header">
        <div className="header-brand">
          <div className="brand-logo">⚡</div>
          <div className="brand-title">
            <h1>Lyftr AI Gateway</h1>
            <span className="brand-subtitle">Key Failover & Response Caching</span>
          </div>
        </div>

        <div className="header-meta">
          <div className="session-pill" title="Current Session ID">
            <span className="session-label">Session:</span>
            <code className="session-id">{sessionId}</code>
            <button
              className="btn-icon"
              onClick={() => navigator.clipboard.writeText(sessionId)}
              title="Copy Session ID"
            >
              📋
            </button>
            <button
              className="btn-new-session"
              onClick={handleStartNewSession}
              title="Start a new session on demand"
            >
              + New Session
            </button>
          </div>

          <div className="health-badge">
            <span
              className={`status-dot ${
                healthInfo?.status === 'ok' ? 'status-online' : 'status-offline'
              }`}
            />
            <span>
              {healthInfo?.status === 'ok'
                ? `Ready (${healthInfo.keys_configured} Keys)`
                : 'Connecting...'}
            </span>
          </div>
        </div>
      </header>

      {/* Control Drawer / Toolbar */}
      <div className="control-toolbar">
        <div className="toolbar-left">
          <button
            type="button"
            className={`btn-toolbar ${showSystemPrompt ? 'active' : ''}`}
            onClick={() => setShowSystemPrompt(!showSystemPrompt)}
          >
            ⚙️ System Prompt {systemPrompt ? '(Configured)' : ''}
          </button>
        </div>

        <div className="toolbar-right">
          <label className="sim-label" htmlFor="sim-select">
            🧪 Failure Simulation:
          </label>
          <select
            id="sim-select"
            className="sim-select"
            value={simulateFailure}
            onChange={(e) => setSimulateFailure(e.target.value)}
          >
            <option value="">Normal (Live / Cached)</option>
            <option value="key_1=429">Simulate key_1=429 (Failover to key_2)</option>
            <option value="key_1=500">Simulate key_1=500 (Failover to key_2)</option>
            <option value="key_1=429,key_2=500">Simulate key_1=429 & key_2=500</option>
            <option value="*=429">Simulate *=429 (All Fail -> 503)</option>
          </select>
          {simulateFailure && (
            <span className="sim-active-badge">Active: {simulateFailure}</span>
          )}
        </div>
      </div>

      {/* Optional System Prompt Field */}
      {showSystemPrompt && (
        <div className="system-prompt-container">
          <label htmlFor="system-prompt-input">Session System Prompt</label>
          <textarea
            id="system-prompt-input"
            data-testid="system-prompt-input"
            className="system-prompt-input"
            rows="2"
            placeholder="e.g. You are a concise and helpful AI technical advisor."
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
          />
        </div>
      )}

      {/* Chat Messages Feed */}
      <main className="chat-feed">
        {messages.length === 0 && (
          <div className="chat-empty-state">
            <div className="empty-icon">💬</div>
            <h2>Start a Conversation</h2>
            <p>
              Send a message to see key failover, response caching, and per-request
              token telemetry in real-time.
            </p>
            <div className="empty-hints">
              <div className="hint-card">
                <strong>⚡ LiteLLM Response Caching</strong>
                <p>Identical prompt in a new session returns instantly from cache with <code>LLM_CACHE</code>.</p>
              </div>
              <div className="hint-card">
                <strong>🔄 Automatic Key Failover</strong>
                <p>Simulate <code>key_1=429</code> to see seamless fallback to <code>key_2</code> without disruption.</p>
              </div>
            </div>
          </div>
        )}

        {messages.map((msg) => {
          if (msg.role === 'user') {
            return (
              <div key={msg.id} className="message-wrapper message-user">
                <div className="message-bubble user-bubble">
                  <div className="message-content">{msg.content}</div>
                  <div className="message-timestamp">{msg.timestamp}</div>
                </div>
              </div>
            );
          }

          if (msg.role === 'error') {
            return (
              <div key={msg.id} className="message-wrapper message-error">
                <div className="error-card">
                  <div className="error-header">
                    <span className="error-icon">⚠️</span>
                    <strong>{msg.status === 422 ? 'Validation Error' : 'Gateway Error'}</strong>
                  </div>
                  <div className="error-body">{msg.content}</div>
                </div>
              </div>
            );
          }

          // Assistant Message
          return (
            <div
              key={msg.id}
              className="message-wrapper message-assistant"
              data-testid="assistant-message"
            >
              <div className="assistant-card">
                <div className="assistant-reply-text">{msg.content}</div>

                {/* Metadata Row */}
                {msg.metadata && (
                  <div className="assistant-metadata">
                    {/* Source Badge */}
                    <div
                      className={`meta-badge ${
                        msg.metadata.resolution_source === 'LLM_CACHE'
                          ? 'badge-cache'
                          : 'badge-live'
                      }`}
                    >
                      <span className="badge-icon">
                        {msg.metadata.resolution_source === 'LLM_CACHE' ? '⚡' : '🌐'}
                      </span>
                      <span data-testid="meta-source">
                        {msg.metadata.resolution_source}
                      </span>
                    </div>

                    {/* Model */}
                    <div className="meta-item">
                      <span className="meta-label">Model:</span>
                      <span data-testid="meta-model" className="meta-value">
                        {msg.metadata.model}
                      </span>
                    </div>

                    {/* Latency */}
                    <div className="meta-item">
                      <span className="meta-label">Latency:</span>
                      <span data-testid="meta-latency" className="meta-value">
                        {msg.metadata.latency_ms} ms
                      </span>
                    </div>

                    {/* Tokens */}
                    <div className="meta-item">
                      <span className="meta-label">Prompt Tokens:</span>
                      <span data-testid="meta-input-tokens" className="meta-value">
                        {msg.metadata.input_tokens}
                      </span>
                    </div>

                    <div className="meta-item">
                      <span className="meta-label">Completion Tokens:</span>
                      <span data-testid="meta-output-tokens" className="meta-value">
                        {msg.metadata.output_tokens}
                      </span>
                    </div>

                    {/* Key & Fallback Attempts Info */}
                    {msg.metadata.key_id ? (
                      <div className="meta-item meta-key">
                        <span className="meta-label">Key:</span>
                        <span className="meta-value key-tag">
                          {msg.metadata.key_id}
                        </span>
                        {msg.metadata.fallback_attempts > 0 && (
                          <span className="fallback-tag">
                            ({msg.metadata.fallback_attempts} fallback
                            {msg.metadata.fallback_attempts > 1 ? 's' : ''})
                          </span>
                        )}
                      </div>
                    ) : (
                      <div className="meta-item meta-key">
                        <span className="meta-label">Key:</span>
                        <span className="meta-value key-tag muted">none (cached)</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="message-wrapper message-assistant">
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </main>

      {/* Input Form Footer */}
      <footer className="chat-footer">
        <form className="chat-form" onSubmit={handleSendMessage}>
          <textarea
            data-testid="chat-input"
            className="chat-textarea"
            rows="1"
            placeholder="Type your message here... (Press Enter to send, Shift+Enter for newline)"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <button
            type="submit"
            data-testid="send-button"
            className="btn-send"
            disabled={loading || !inputText.trim()}
          >
            {loading ? 'Sending...' : 'Send 🚀'}
          </button>
        </form>
      </footer>
    </div>
  );
}
