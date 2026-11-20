import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

const SUGGESTIONS = [
  "What is AIDA project?",
  "What services does Wasalt offer?",
  "What is the Gross Development Value of DarGlobal?",
  "Tell me about Trump Tower Jeddah",
];

function Arrow({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3 8h9M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function External() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M6 3h7v7M13 3L5 11" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 10v3H3V4h3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function EmptyState({ onAsk, busy }) {
  return (
    <div className="empty">
      <div className="empty-rule" />
      <h2>
        Ask the record.
        <span>Read the answer.</span>
      </h2>
      <p>
        A quiet desk for questions about DarGlobal projects and Wasalt services.
        Every answer is drawn from public pages, and every source is shown beneath it.
      </p>
      <div className="prompt-label">Suggested questions</div>
      {SUGGESTIONS.map((question) => (
        <button key={question} className="prompt-row" onClick={() => onAsk(question)} disabled={busy}>
          <span>{question}</span>
          <span className="arrow"><Arrow size={17} /></span>
        </button>
      ))}
    </div>
  );
}

function toMarkdown(content, sources) {
  return content.replace(/\[(\d+)\]/g, (mark, number) => {
    const source = sources[Number(number) - 1];
    return source ? `[[${number}]](${source.url})` : mark;
  });
}

const markdownComponents = {
  p: ({ children }) => <p className="answer-p">{children}</p>,
  strong: ({ children }) => <strong className="answer-strong">{children}</strong>,
  em: ({ children }) => <em className="answer-em">{children}</em>,
  ul: ({ children }) => <ul className="answer-list">{children}</ul>,
  ol: ({ children }) => <ol className="answer-list">{children}</ol>,
  li: ({ children }) => <li className="answer-item">{children}</li>,
  h2: ({ children }) => <h3 className="answer-heading">{children}</h3>,
  h3: ({ children }) => <h3 className="answer-heading">{children}</h3>,
  a: ({ href, children }) => (
    <a className="citation" href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
};

function Message({ item }) {
  if (item.role === "user") {
    return (
      <div className="message message-user">
        <div className="bubble">{item.content}</div>
      </div>
    );
  }

  return (
    <div className="message message-assistant">
      <div className="meta">Concierge</div>
      <div className="answer">
        <ReactMarkdown components={markdownComponents}>
          {toMarkdown(item.content, item.sources ?? [])}
        </ReactMarkdown>
      </div>
      {item.sources?.length > 0 && (
        <div className="sources">
          <div className="sources-label">Sources</div>
          {item.sources.map((source, index) => (
            <a key={`${source.url}-${index}`} className="source-row" href={source.url} target="_blank" rel="noreferrer">
              <span className="source-index">{String(index + 1).padStart(2, "0")}</span>
              <span>{source.title}</span>
              <span className="source-name">{source.source}</span>
              <External />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy, error]);

  async function ask(question) {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    setLastQuestion(text);
    setMessages((current) => [...current, { role: "user", content: text }]);
    setInput("");

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });
      if (!response.ok) {
        let detail = "The concierge could not answer right now.";
        try {
          const body = await response.json();
          if (body?.detail) detail = body.detail;
        } catch {
          /* response body was not JSON */
        }
        throw new Error(detail);
      }
      const data = await response.json();
      setMessages((current) => [
        ...current,
        { role: "assistant", content: data.answer, sources: data.sources ?? [] },
      ]);
    } catch (err) {
      setError(err.message || "The concierge could not answer right now.");
    } finally {
      setBusy(false);
      textareaRef.current?.focus();
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      ask(input);
    }
  }

  return (
    <div className="shell">
      <aside className="rail">
        <div>
          <div className="brand-mark">DG<span>/</span>WS</div>
          <div className="brand-sub">Public Data Concierge</div>
        </div>

        <div className="rail-intro">
          <h1>
            Know before
            <br />
            <em>you invest.</em>
          </h1>
          <p>
            Project facts, company figures, and property listings from the public
            record of DarGlobal and Wasalt.
          </p>
        </div>

        <div className="rail-section">
          <div className="rail-section-label">Try asking</div>
          {SUGGESTIONS.slice(0, 3).map((question) => (
            <button key={question} className="suggestion" onClick={() => ask(question)} disabled={busy}>
              <Arrow size={15} />
              <span>{question}</span>
            </button>
          ))}
        </div>

        <div className="rail-foot">
          Answers come only from the published sources shown below each reply.
          Verify current prices and availability on the source site.
        </div>
      </aside>

      <main className="stage">
        <div className="stage-head">
          <div className="stage-title">Conversation</div>
          <div className="status"><span className="status-dot" /> Knowledge base connected</div>
        </div>

        <div className="thread">
          <div className="thread-inner">
            {messages.length === 0 && <EmptyState onAsk={ask} busy={busy} />}
            {messages.map((item, index) => (
              <Message key={index} item={item} />
            ))}
            {busy && (
              <div className="message message-assistant">
                <div className="meta">Concierge</div>
                <div className="typing"><span /><span /><span /></div>
              </div>
            )}
            {error && (
              <div className="message message-assistant">
                <div className="error-note">
                  {error}
                  <br />
                  <button onClick={() => ask(lastQuestion)} disabled={busy}>Try again</button>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="composer-wrap">
          <div className="composer">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question…"
              aria-label="Your question"
              disabled={busy}
            />
            <button className="send" onClick={() => ask(input)} disabled={!input.trim() || busy} aria-label="Send question">
              <Arrow size={18} />
            </button>
          </div>
          <div className="composer-hint">Press Enter to send · Shift + Enter for a new line</div>
        </div>
      </main>
    </div>
  );
}
