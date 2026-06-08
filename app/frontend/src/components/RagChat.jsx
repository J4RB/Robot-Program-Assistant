import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useEditor } from '../contexts/EditorContext';
import { sanitizeProgramContext, buildContextLabel, buildProgramContextPayload } from '../utils/programContext';
import './RagChat.css';

const DEFAULT_ASSISTANT_MESSAGE = {
  role: 'assistant',
  content: 'Hi! I can help you understand and improve your robot program. Ask me anything about it.',
};

const MIN_INPUT_HEIGHT = 40;
const MAX_INPUT_HEIGHT = 200;

function getProgramSourceModeInSearch(mode) {
  if (mode === 'full') return 'code';
  if (mode === 'both') return 'metadata + code';
  return 'metadata';
}

function formatSearchedDatabases(routing) {
  const databases = routing?.databases_searched;
  if (!Array.isArray(databases) || databases.length === 0) return '';

  return databases
    .map((db) => {
      if (db === 'robot_programs') {
        return `${db} (${getProgramSourceModeInSearch(routing?.program_context_mode)})`;
      }
      return db;
    })
    .join(', ');
}

function getAgentTraceSummary(message, isLoading = false) {
  if (!message?.agentTrace || message.agentTrace.length === 0) return '';
  if (isLoading) return message.agentTrace[message.agentTrace.length - 1];
  return message.agentTraceFinalized ? 'Agent Traces' : message.agentTrace[message.agentTrace.length - 1];
}

function getSourceMetadata(source) {
  const metadata = source?.metadata || {};
  return {
    metadata,
    nestedMetadata: metadata?.raw_payload || metadata?.metadata || {},
  };
}

function pickSourceValue(source, ...keys) {
  const { metadata, nestedMetadata } = getSourceMetadata(source);
  const containers = [metadata, nestedMetadata, source];

  for (const key of keys) {
    for (const container of containers) {
      const value = container?.[key];
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        return value;
      }
    }
  }

  return undefined;
}

function formatSourceLine(source) {
  const collection = source?.source;
  const programName = pickSourceValue(source, 'program_name', 'program_id') || 'UnknownProgram';
  const pageNumber = pickSourceValue(source, 'page_number');
  const docName = pickSourceValue(source, 'doc_name') || 'Unknown document';
  const startLine = pickSourceValue(source, 'start_line');
  const endLine = pickSourceValue(source, 'end_line');
  const section = pickSourceValue(source, 'section_name', 'chunk_type') || 'action';

  if (collection === 'documentation') {
    const pageSuffix = pageNumber !== undefined ? ` (Page: ${pageNumber})` : '';
    return `${docName}${pageSuffix}`;
  }

  if (collection === 'robot_program_code') {
    const linePart =
      startLine !== undefined && endLine !== undefined
        ? `${startLine}-${endLine}`
        : `${startLine ?? endLine ?? 'unknown'}`;
    return `${programName}:${linePart} (${section})`;
  }

  return `${programName} (Metadata)`;
}

function getSourceRawContent(source) {
  const collection = source?.source;
  const { metadata, nestedMetadata } = getSourceMetadata(source);

  if (collection === 'documentation') {
    return source?.text || nestedMetadata?.text || metadata?.text || 'No documentation text available';
  }

  const raw = nestedMetadata || metadata || {};
  const filtered = {
    chunk_text: raw?.chunk_text,
    snippet_text: raw?.snippet_text,
    metadata: raw?.metadata,
  };

  const sections = [];

  if (filtered.chunk_text !== undefined && filtered.chunk_text !== null && String(filtered.chunk_text).trim() !== '') {
    sections.push(`Chunk Text:\n${String(filtered.chunk_text).trim()}`);
  }

  if (filtered.snippet_text !== undefined && filtered.snippet_text !== null && String(filtered.snippet_text).trim() !== '') {
    sections.push(`Snippet Text:\n${String(filtered.snippet_text).trim()}`);
  }

  if (filtered.metadata !== undefined) {
    const metadataText =
      typeof filtered.metadata === 'string'
        ? filtered.metadata
        : JSON.stringify(filtered.metadata, null, 2);
    sections.push(`Metadata:\n${metadataText}`);
  }

  return sections.length > 0 ? sections.join('\n\n') : 'No source details available';
}

function RagChat({ programId }) {
  const {
    chatMessages,
    addChatMessage,
    code,
    selectedCodeSelection,
    programData,
    pendingProgramContexts,
    addPendingProgramContext,
    removePendingProgramContext,
    clearPendingProgramContexts,
  } = useEditor();
  const [localMessages, setLocalMessages] = useState(
    chatMessages.length > 0 ? chatMessages : [DEFAULT_ASSISTANT_MESSAGE],
  );
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingTrace, setLoadingTrace] = useState([]);
  const [activeSourceTooltip, setActiveSourceTooltip] = useState(null);
  const tooltipHideTimeoutRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const inputWidthRef = useRef(0);

  const API_BASE = 'http://localhost:8000';

  // Auto-expand textarea as content grows
  const autoExpandTextarea = () => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      const nextHeight = Math.min(
        MAX_INPUT_HEIGHT,
        Math.max(MIN_INPUT_HEIGHT, inputRef.current.scrollHeight),
      );
      inputRef.current.style.height = `${nextHeight}px`;
      inputRef.current.style.overflowY = inputRef.current.scrollHeight > MAX_INPUT_HEIGHT ? 'auto' : 'hidden';
    }
  };

  useEffect(() => {
    autoExpandTextarea();
  }, [input]);

  useEffect(() => {
    const textarea = inputRef.current;
    if (!textarea || typeof ResizeObserver === 'undefined') {
      return undefined;
    }

    const updateHeight = () => {
      autoExpandTextarea();
    };

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      const width = entry?.contentRect?.width ?? textarea.clientWidth;
      if (!width || width === inputWidthRef.current) {
        return;
      }

      inputWidthRef.current = width;
      requestAnimationFrame(updateHeight);
    });

    inputWidthRef.current = textarea.clientWidth;
    requestAnimationFrame(updateHeight);
    resizeObserver.observe(textarea);

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  // Update local messages when context messages change
  useEffect(() => {
    setLocalMessages(chatMessages.length > 0 ? chatMessages : [DEFAULT_ASSISTANT_MESSAGE]);
  }, [chatMessages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [localMessages]);

  const clearTooltipHideTimeout = () => {
    if (tooltipHideTimeoutRef.current) {
      clearTimeout(tooltipHideTimeoutRef.current);
      tooltipHideTimeoutRef.current = null;
    }
  };

  const scheduleHideSourceTooltip = () => {
    clearTooltipHideTimeout();
    tooltipHideTimeoutRef.current = setTimeout(() => {
      setActiveSourceTooltip(null);
      tooltipHideTimeoutRef.current = null;
    }, 140);
  };

  const showSourceTooltip = (tooltipId, rawContent, targetElement) => {
    if (!targetElement) return;
    clearTooltipHideTimeout();
    const rect = targetElement.getBoundingClientRect();
    const tooltipWidth = Math.min(700, Math.max(320, Math.floor(window.innerWidth * 0.68)));
    const left = Math.min(
      window.innerWidth - tooltipWidth - 12,
      Math.max(12, rect.right - tooltipWidth),
    );

    setActiveSourceTooltip({
      id: tooltipId,
      content: rawContent,
      top: Math.max(12, rect.top - 8),
      left,
      width: tooltipWidth,
    });
  };

  useEffect(() => () => clearTooltipHideTimeout(), []);

  const contextFileName = `${programData?.name || programData?.metadata?.name || programId || 'program'}.urpx`;
  const hasSelection = Boolean(selectedCodeSelection?.text);
  const contextButtonLabel = hasSelection
    ? buildContextLabel(contextFileName, selectedCodeSelection.startLine, selectedCodeSelection.endLine)
    : contextFileName;

  const handleAddProgramContext = () => {
    const mode = hasSelection ? 'selection' : 'full';
    const rawContext = mode === 'selection' ? selectedCodeSelection.text : code;
    const sanitized = sanitizeProgramContext(rawContext || '');

    if (!sanitized.trim()) {
      alert('No valid program context found.');
      return;
    }

    addPendingProgramContext({
      text: sanitized,
      source: mode,
      chars: sanitized.length,
      fileName: contextFileName,
      label: mode === 'selection'
        ? buildContextLabel(contextFileName, selectedCodeSelection.startLine, selectedCodeSelection.endLine)
        : contextFileName,
      startLine: mode === 'selection' ? selectedCodeSelection.startLine : undefined,
      endLine: mode === 'selection' ? selectedCodeSelection.endLine : undefined,
    });
  };

  const handleKeyDown = (e) => {
    // Send on Enter, unless Shift is held (Shift+Enter creates newline)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e);
    }
  };

  const streamChat = async (payload, onProgress) => {
    const response = await fetch(`${API_BASE}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Streaming request failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let finalPayload = null;

    const processChunk = (chunk) => {
      buffer += chunk;
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';

      for (const rawEvent of parts) {
        const lines = rawEvent.split('\n');
        let eventType = 'message';
        const dataLines = [];

        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim();
          }
          if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).trim());
          }
        }

        if (!dataLines.length) {
          continue;
        }

        const data = JSON.parse(dataLines.join('\n'));
        if (eventType === 'progress' && data.message) {
          onProgress(data.message);
        }
        if (eventType === 'final') {
          finalPayload = data;
        }
        if (eventType === 'error') {
          throw new Error(data.message || 'Streaming chat failed');
        }
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      processChunk(decoder.decode(value, { stream: true }));
    }

    processChunk(decoder.decode());

    if (!finalPayload) {
      throw new Error('Streaming ended without final response payload');
    }

    return finalPayload;
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    // Add user message
    const userMessage = input;
    const newUserMessage = { role: 'user', content: userMessage };
    setLocalMessages((prev) => [...prev, newUserMessage]);
    addChatMessage(newUserMessage);
    setInput('');
    setLoading(true);
    setLoadingTrace([]);
    const traceHistory = [];
    const contextUsed = pendingProgramContexts.length > 0
      ? pendingProgramContexts.map((context) => ({ ...context }))
      : [];

    try {
      const payload = buildProgramContextPayload(pendingProgramContexts);

      // Log sent contexts for debugging
      if (pendingProgramContexts.length > 0) {
        console.log(
          "[CHAT] Sent program contexts:",
          pendingProgramContexts.map(ctx => ({
            label: ctx.label,
            chars: ctx.chars,
            source: ctx.source,
          }))
        );
        console.log("[CHAT] Combined payload length:", payload?.length || 0);
      }

      const responseData = await streamChat({
        message: userMessage,
        program_context: payload,
      }, (message) => {
        if (traceHistory[traceHistory.length - 1] !== message) {
          traceHistory.push(message);
        }
        setLoadingTrace(traceHistory.slice(-8));
      });

      // Add assistant response
      const assistantMessage = {
        role: 'assistant',
        content: responseData.response,
        sources: responseData.sources,
        routing: responseData.routing,
        programContextsUsed: contextUsed,
        agentTrace: traceHistory,
        agentTraceFinalized: true,
      };
      setLocalMessages((prev) => [...prev, assistantMessage]);
      addChatMessage(assistantMessage);
      clearPendingProgramContexts();
    } catch (error) {
      console.error('Chat failed:', error);
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        error: true,
        agentTrace: traceHistory,
        agentTraceFinalized: true,
      };
      setLocalMessages((prev) => [...prev, errorMessage]);
      addChatMessage(errorMessage);
    } finally {
      setLoading(false);
      setLoadingTrace([]);
    }
  };

  return (
    <div className="rag-chat">
      <div className="chat-messages">
        {localMessages.map((message, index) => (
          <div key={index} className={`chat-message message-${message.role}`}>
            <div className="message-content">
              {message.role === 'assistant' ? (
                <>
                  {message.agentTrace?.length > 0 && (
                    <details className="agent-trace-dropdown">
                      <summary>{getAgentTraceSummary(message)}</summary>
                      <div className="agent-trace-list">
                        {message.agentTrace.map((traceItem, idx) => (
                          <div key={`${idx}-${traceItem}`} className="agent-trace-list-item">
                            {traceItem}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                  <div className="assistant-response markdown-content">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {message.content || ''}
                    </ReactMarkdown>
                  </div>
                </>
              ) : (
                <p className="user-text">{message.content}</p>
              )}

              {(message.sources && message.sources.length > 0) || message.programContextsUsed?.length > 0 ? (
                <details className="message-metadata">
                  <summary>
                    {message.sources?.length || 0} sources
                    {message.programContextsUsed?.length > 0 ? ` + ${message.programContextsUsed.length} code context` : ''}
                  </summary>
                  <div className="metadata-content">
                    {message.programContextsUsed?.length > 0 && (
                      <div className="metadata-section">
                        <div className="metadata-header">Program Context</div>
                        <div className="sources-list">
                          {message.programContextsUsed.map((contextItem) => (
                            <div key={contextItem.id || `${contextItem.label}-${contextItem.chars}`} className="source-item">
                              <div className="source-name">
                                {contextItem.label || contextItem.fileName}
                              </div>
                              <div className="source-score">{contextItem.chars} characters</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {message.sources && message.sources.length > 0 && (
                      <div className="metadata-section">
                        <div className="metadata-header">Sources</div>
                        {message.routing?.databases_searched?.length > 0 && (
                          <div className="routing-decision-text">
                            Searched: {formatSearchedDatabases(message.routing)}
                          </div>
                        )}
                        <div className="sources-list">
                          {message.sources.map((source, idx) => (
                            <div key={idx} className="source-item">
                              <div className="source-body">
                                <div className="source-name">
                                  {formatSourceLine(source)}
                                </div>
                                <div className="source-collection">Collection: {source.source}</div>
                              </div>
                              <div className="source-actions">
                                <div className="source-score">{Number(source.score ?? 0).toFixed(2)}</div>
                                <div
                                  className="source-info-popover"
                                  onMouseEnter={(e) => showSourceTooltip(`${index}-${idx}`, getSourceRawContent(source), e.currentTarget)}
                                  onMouseLeave={scheduleHideSourceTooltip}
                                >
                                  <button
                                    type="button"
                                    className="source-info-button"
                                    aria-label="Show embedded source content"
                                    onFocus={(e) => showSourceTooltip(`${index}-${idx}`, getSourceRawContent(source), e.currentTarget)}
                                    onBlur={scheduleHideSourceTooltip}
                                  >
                                    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2Zm0 4a1.25 1.25 0 1 1 0 2.5A1.25 1.25 0 0 1 12 6Zm2 12h-4v-1.5h1V11h-1V9.5h3V16.5h1V18Z" />
                                    </svg>
                                  </button>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                  </div>
                </details>
              ) : null}

              {message.error && <span className="message-error">Error</span>}
            </div>
          </div>
        ))}
        {loading && (
          <div className="chat-message message-assistant">
            <div className="message-content">
              <div className="loading-state">
                <div className="loading"></div>
                {loadingTrace.length > 0 && (
                  <details className="agent-trace-dropdown agent-trace-dropdown-live">
                    <summary className="compact-summary">{loadingTrace[loadingTrace.length - 1]}</summary>
                    <div className="agent-trace-list">
                      {loadingTrace.map((traceMessage, idx) => (
                        <div key={`${idx}-${traceMessage}`} className="agent-trace-list-item">
                          {traceMessage}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-context-toolbar">
        <button
          type="button"
          className="chat-context-btn"
          onClick={handleAddProgramContext}
          disabled={loading || !programId}
          title="Add selected editor lines or full program as chat context"
        >
          + {contextButtonLabel}
        </button>
        {pendingProgramContexts.map((contextItem) => (
          <div
            key={contextItem.id}
            className="context-pill"
          >
            {contextItem.label || contextItem.fileName}
            <button
              type="button"
              className="context-pill-clear"
              onClick={() => removePendingProgramContext(contextItem.id)}
              aria-label={`Remove ${contextItem.label || contextItem.fileName} from pending chat context`}
            >
              x
            </button>
          </div>
        ))}
      </div>

      <form onSubmit={handleSendMessage} className="chat-input-form">
        <textarea
          ref={inputRef}
          placeholder="Ask about the program..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          className="chat-input"
          rows="1"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="btn-primary chat-send-btn"
        >
          {loading ? '...' : '➤'}
        </button>
      </form>

      {activeSourceTooltip && createPortal(
        <div
          className="source-info-tooltip-portal"
          role="tooltip"
          onMouseEnter={clearTooltipHideTimeout}
          onMouseLeave={scheduleHideSourceTooltip}
          style={{
            top: `${activeSourceTooltip.top}px`,
            left: `${activeSourceTooltip.left}px`,
            width: `${activeSourceTooltip.width}px`,
            transform: 'translateY(-100%)',
          }}
        >
          {activeSourceTooltip.content}
        </div>,
        document.body,
      )}
    </div>
  );
}

export default RagChat;
