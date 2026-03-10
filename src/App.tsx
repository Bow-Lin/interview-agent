import { FormEvent, useEffect, useMemo, useState } from "react";

type Role = "agent_engineer" | "backend_engineer" | "frontend_engineer" | "algorithm_engineer";
type Level = "junior" | "mid" | "senior";
type PromptType = "main_question" | "followup";
type View = "home" | "config" | "interview" | "report";
type Provider = "openai_compatible";

type HistoryItem = {
  session_id: string;
  role: string;
  level: string;
  status: string;
  total_score: number | null;
  duration_minutes?: number;
};

type PromptPayload = {
  question_id: string;
  question_text: string;
  prompt_type: PromptType;
};

type SessionState = {
  session_id: string;
  status: string;
  question_index: number;
  question_limit: number;
  current_prompt: PromptPayload;
  remaining_seconds: number;
};

type Report = {
  session_id: string;
  total_score: number;
  knowledge_score: number;
  communication_score: number;
  system_design_score: number;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
  summary: string;
  question_summaries: Array<{
    question_id: string;
    question_text: string;
    score: number;
    answer_quality: string;
    strengths: string[];
    missing_points: string[];
    summary: string;
  }>;
};

type TranscriptTurn = {
  speaker: "agent" | "candidate";
  text: string;
  kind: PromptType | "answer";
};

type InterviewConfig = {
  role: Role;
  level: Level;
  duration_minutes: 10;
  allow_followup: boolean;
};

type LLMSettingsState = {
  configured: boolean;
  provider: Provider;
  base_url: string;
  model: string;
  api_key_set: boolean;
};

type LLMSettingsForm = {
  provider: Provider;
  base_url: string;
  model: string;
  api_key: string;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const defaultConfig: InterviewConfig = {
  role: "agent_engineer",
  level: "mid",
  duration_minutes: 10,
  allow_followup: true,
};

const defaultSettingsForm: LLMSettingsForm = {
  provider: "openai_compatible",
  base_url: "https://api.openai.com/v1",
  model: "",
  api_key: "",
};

function formatRole(value: string): string {
  return value
    .split("_")
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function formatPromptLabel(promptType: PromptType): string {
  return promptType === "followup" ? "Follow-up" : "Main question";
}

function formatSeconds(value: number): string {
  const minutes = Math.floor(value / 60)
    .toString()
    .padStart(2, "0");
  const seconds = Math.floor(value % 60)
    .toString()
    .padStart(2, "0");
  return `${minutes}:${seconds}`;
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export default function App() {
  const [view, setView] = useState<View>("home");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [config, setConfig] = useState<InterviewConfig>(defaultConfig);
  const [session, setSession] = useState<SessionState | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [answer, setAnswer] = useState("");
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pendingConfigRedirect, setPendingConfigRedirect] = useState(false);
  const [llmSettings, setLlmSettings] = useState<LLMSettingsState>({
    configured: false,
    provider: "openai_compatible",
    base_url: "",
    model: "",
    api_key_set: false,
  });
  const [settingsForm, setSettingsForm] = useState<LLMSettingsForm>(defaultSettingsForm);

  useEffect(() => {
    void loadHistory();
    void loadLLMSettings();
  }, []);

  const scoreLabel = useMemo(() => {
    if (!report) {
      return "";
    }
    return `${report.total_score} / 100`;
  }, [report]);

  async function loadHistory() {
    try {
      const payload = await apiRequest<{ sessions: HistoryItem[] }>("/history");
      setHistory(payload.sessions);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load history.");
    }
  }

  async function loadLLMSettings() {
    try {
      const payload = await apiRequest<{
        configured: boolean;
        provider: Provider | null;
        base_url: string | null;
        model: string | null;
        api_key_set: boolean;
      }>("/settings/llm");
      const nextState: LLMSettingsState = {
        configured: payload.configured,
        provider: payload.provider ?? "openai_compatible",
        base_url: payload.base_url ?? "",
        model: payload.model ?? "",
        api_key_set: payload.api_key_set,
      };
      setLlmSettings(nextState);
      setSettingsForm({
        provider: nextState.provider,
        base_url: nextState.base_url || defaultSettingsForm.base_url,
        model: nextState.model,
        api_key: "",
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load LLM settings.");
    }
  }

  function openSettings(options?: { redirectToConfig?: boolean }) {
    setPendingConfigRedirect(Boolean(options?.redirectToConfig));
    setSettingsOpen(true);
    setError(null);
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const payload = await apiRequest<{
        configured: boolean;
        provider: Provider;
        base_url: string;
        model: string;
        api_key_set: boolean;
      }>("/settings/llm", {
        method: "PUT",
        body: JSON.stringify(settingsForm),
      });
      const nextState: LLMSettingsState = {
        configured: payload.configured,
        provider: payload.provider,
        base_url: payload.base_url,
        model: payload.model,
        api_key_set: payload.api_key_set,
      };
      setLlmSettings(nextState);
      setSettingsForm((previous) => ({
        ...previous,
        api_key: "",
      }));
      setSettingsOpen(false);
      if (pendingConfigRedirect) {
        setView("config");
        setPendingConfigRedirect(false);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to save LLM settings.");
    } finally {
      setBusy(false);
    }
  }

  async function createSession() {
    if (!llmSettings.configured) {
      openSettings();
      setError("Configure your OpenAI-compatible provider before starting an interview.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await apiRequest<SessionState>("/sessions", {
        method: "POST",
        body: JSON.stringify(config),
      });
      setSession(created);
      setTranscript([
        {
          speaker: "agent",
          text: created.current_prompt.question_text,
          kind: created.current_prompt.prompt_type,
        },
      ]);
      setAnswer("");
      setView("interview");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to create session.");
    } finally {
      setBusy(false);
    }
  }

  async function submitAnswer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session || !answer.trim()) {
      return;
    }

    const trimmedAnswer = answer.trim();
    setBusy(true);
    setError(null);
    try {
      const result = await apiRequest<{
        event: "followup" | "next_question" | "finished";
        session_id: string;
        status: string;
        question_index: number;
        followup_count: number;
        remaining_seconds: number;
        current_prompt: PromptPayload | null;
        report?: Report;
      }>(`/sessions/${session.session_id}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer: trimmedAnswer }),
      });

      setTranscript((previous) => {
        const candidateTurn: TranscriptTurn = {
          speaker: "candidate",
          text: trimmedAnswer,
          kind: "answer",
        };
        const updated: TranscriptTurn[] = [
          ...previous,
          candidateTurn,
        ];
        if (result.current_prompt) {
          updated.push({
            speaker: "agent",
            text: result.current_prompt.question_text,
            kind: result.current_prompt.prompt_type,
          });
        }
        return updated;
      });

      setAnswer("");

      if (result.event === "finished" && result.report) {
        setReport(result.report);
        setSession(null);
        setView("report");
        await loadHistory();
        return;
      }

      if (result.current_prompt) {
        setSession({
          ...session,
          question_index: result.question_index,
          remaining_seconds: result.remaining_seconds,
          status: result.status,
          current_prompt: result.current_prompt,
        });
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to submit answer.");
    } finally {
      setBusy(false);
    }
  }

  async function finishInterview() {
    if (!session) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const finished = await apiRequest<Report>(`/sessions/${session.session_id}/finish`, {
        method: "POST",
      });
      setReport(finished);
      setSession(null);
      setView("report");
      await loadHistory();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to finish interview.");
    } finally {
      setBusy(false);
    }
  }

  async function openReport(sessionId: string) {
    setBusy(true);
    setError(null);
    try {
      const loaded = await apiRequest<Report>(`/reports/${sessionId}`);
      setReport(loaded);
      setView("report");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to load report.");
    } finally {
      setBusy(false);
    }
  }

  function resetToHome() {
    setView("home");
    setReport(null);
    setSession(null);
    setAnswer("");
    setTranscript([]);
  }

  return (
    <div className="app-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <main className="panel">
        <header className="hero">
          <p className="eyebrow">Interactive Interview Simulator</p>
          <h1>Interview Agent</h1>
          <p className="hero-copy">
            A local Web MVP for question-bank driven interviews, dynamic follow-ups, and
            structured feedback reports.
          </p>
        </header>

        {error ? <div className="error-banner">{error}</div> : null}

        {view === "home" ? (
          <section className="card-grid">
            <section className="card primary-card">
              <h2>Start a new mock interview</h2>
              <p>
                Pick a target role, answer in text, and let the interviewer push on missing
                points before generating a report.
              </p>
              <button
                className="action-button"
                onClick={() => {
                  if (!llmSettings.configured) {
                    openSettings({ redirectToConfig: true });
                    return;
                  }
                  setView("config");
                }}
              >
                Start Mock Interview
              </button>
            </section>

            <section className="card history-card">
              <div className="section-heading">
                <h2>History</h2>
                <div className="button-row">
                  <button className="ghost-button" onClick={() => openSettings()}>
                    LLM Settings
                  </button>
                  <button className="ghost-button" onClick={() => void loadHistory()}>
                    Refresh
                  </button>
                </div>
              </div>

              {history.length === 0 ? (
                <p className="muted-copy">No completed sessions yet.</p>
              ) : (
                <ul className="history-list">
                  {history.map((item) => (
                    <li key={item.session_id}>
                      <button className="history-item" onClick={() => void openReport(item.session_id)}>
                        <span>
                          <strong>{formatRole(item.role)}</strong>
                          <small>
                            {item.level.toUpperCase()} · {item.status}
                          </small>
                        </span>
                        <span className="score-pill">{item.total_score ?? "--"}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </section>
        ) : null}

        {view === "config" ? (
          <section className="card config-card">
            <div className="section-heading">
              <h2>Configure interview</h2>
              <button className="ghost-button" onClick={resetToHome}>
                Back
              </button>
            </div>

            <div className="form-grid">
              <label>
                <span>Role</span>
                <select
                  value={config.role}
                  onChange={(event) =>
                    setConfig((previous) => ({
                      ...previous,
                      role: event.target.value as Role,
                    }))
                  }
                >
                  <option value="agent_engineer">Agent Engineer</option>
                  <option value="backend_engineer">Backend Engineer</option>
                  <option value="frontend_engineer">Frontend Engineer</option>
                  <option value="algorithm_engineer">Algorithm Engineer</option>
                </select>
              </label>

              <label>
                <span>Level</span>
                <select
                  value={config.level}
                  onChange={(event) =>
                    setConfig((previous) => ({
                      ...previous,
                      level: event.target.value as Level,
                    }))
                  }
                >
                  <option value="junior">Junior</option>
                  <option value="mid">Mid</option>
                  <option value="senior">Senior</option>
                </select>
              </label>

              <label>
                <span>Duration</span>
                <select
                  value={config.duration_minutes}
                  onChange={(event) =>
                    setConfig((previous) => ({
                      ...previous,
                      duration_minutes: Number(event.target.value) as 10,
                    }))
                  }
                >
                  <option value={10}>10 minutes</option>
                </select>
              </label>

              <label className="toggle-row">
                <span>Allow follow-up questions</span>
                <input
                  type="checkbox"
                  checked={config.allow_followup}
                  onChange={(event) =>
                    setConfig((previous) => ({
                      ...previous,
                      allow_followup: event.target.checked,
                    }))
                  }
                />
              </label>
            </div>

            <div className="config-footer">
              <p className="muted-copy">
                {config.duration_minutes} minute sessions will sample a fixed number of main
                questions and can ask up to two follow-ups per question.
              </p>
              <div className="button-row">
                <button className="ghost-button" onClick={() => openSettings()}>
                  Edit LLM Settings
                </button>
                <button className="action-button" disabled={busy} onClick={() => void createSession()}>
                  {busy ? "Creating..." : "Begin Interview"}
                </button>
              </div>
            </div>
          </section>
        ) : null}

        {view === "interview" && session ? (
          <section className="card interview-card">
            <div className="section-heading">
              <div>
                <h2>{formatRole(config.role)}</h2>
                <p className="muted-copy">
                  Question {session.question_index + 1} of {session.question_limit}
                </p>
              </div>
              <div className="status-cluster">
                <span className="timer-chip">{formatSeconds(session.remaining_seconds)}</span>
                <button className="ghost-button" disabled={busy} onClick={() => void finishInterview()}>
                  Finish now
                </button>
              </div>
            </div>

            <article className="prompt-card">
              <span className="prompt-tag">{formatPromptLabel(session.current_prompt.prompt_type)}</span>
              <h3>{session.current_prompt.question_text}</h3>
            </article>

            <form className="answer-form" onSubmit={submitAnswer}>
              <label htmlFor="answer-box">Your answer</label>
              <textarea
                id="answer-box"
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="Type your answer here..."
                rows={7}
              />
              <div className="answer-actions">
                <span className="muted-copy">Be concise, but cover missing details clearly.</span>
                <button className="action-button" disabled={busy || !answer.trim()} type="submit">
                  {busy ? "Submitting..." : "Submit Answer"}
                </button>
              </div>
            </form>

            <section>
              <div className="section-heading">
                <h3>Conversation</h3>
              </div>
              <ul className="transcript-list">
                {transcript.map((turn, index) => (
                  <li key={`${turn.kind}-${index}`} className={`transcript-item ${turn.speaker}`}>
                    <span>{turn.speaker === "agent" ? "Agent" : "You"}</span>
                    <p>{turn.text}</p>
                  </li>
                ))}
              </ul>
            </section>
          </section>
        ) : null}

        {view === "report" && report ? (
          <section className="card report-card">
            <div className="section-heading">
              <div>
                <h2>Interview report</h2>
                <p className="muted-copy">Session {report.session_id}</p>
              </div>
              <button className="ghost-button" onClick={resetToHome}>
                Back to Home
              </button>
            </div>

            <div className="report-hero">
              <div>
                <p className="eyebrow">Total score</p>
                <h3>{scoreLabel}</h3>
              </div>
              <p>{report.summary}</p>
            </div>

            <div className="score-grid">
              <article className="score-card">
                <span>Knowledge</span>
                <strong>{report.knowledge_score}</strong>
              </article>
              <article className="score-card">
                <span>Communication</span>
                <strong>{report.communication_score}</strong>
              </article>
              <article className="score-card">
                <span>System thinking</span>
                <strong>{report.system_design_score}</strong>
              </article>
            </div>

            <div className="report-columns">
              <article>
                <h3>Strengths</h3>
                <ul>
                  {report.strengths.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>
              <article>
                <h3>Weaknesses</h3>
                <ul>
                  {report.weaknesses.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>
              <article>
                <h3>Suggested topics</h3>
                <ul>
                  {report.suggestions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>
            </div>

            <section>
              <div className="section-heading">
                <h3>Question breakdown</h3>
              </div>
              <div className="summary-stack">
                {report.question_summaries.map((item) => (
                  <article className="summary-card" key={item.question_id}>
                    <header>
                      <h4>{item.question_text}</h4>
                      <span className="score-pill">{item.score}</span>
                    </header>
                    <p>{item.summary}</p>
                    <div className="summary-meta">
                      <span>Quality: {item.answer_quality}</span>
                      <span>Strengths: {item.strengths.join(", ") || "None recorded"}</span>
                      <span>
                        Missing: {item.missing_points.join(", ") || "No major missing points"}
                      </span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </section>
        ) : null}

        {settingsOpen ? (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="llm-settings-title">
            <section className="card modal-card">
              <div className="section-heading">
                <div>
                  <h2 id="llm-settings-title">LLM Settings</h2>
                  <p className="muted-copy">
                    Configure an OpenAI-compatible endpoint for evaluation, follow-ups, and reports.
                  </p>
                </div>
                <button className="ghost-button" onClick={() => setSettingsOpen(false)}>
                  Close
                </button>
              </div>

              <form className="form-grid settings-form" onSubmit={saveSettings}>
                <label>
                  <span>Provider</span>
                  <select
                    value={settingsForm.provider}
                    onChange={(event) =>
                      setSettingsForm((previous) => ({
                        ...previous,
                        provider: event.target.value as Provider,
                      }))
                    }
                  >
                    <option value="openai_compatible">OpenAI-Compatible</option>
                  </select>
                </label>

                <label>
                  <span>Base URL</span>
                  <input
                    value={settingsForm.base_url}
                    onChange={(event) =>
                      setSettingsForm((previous) => ({
                        ...previous,
                        base_url: event.target.value,
                      }))
                    }
                    placeholder="https://api.openai.com/v1"
                  />
                </label>

                <label>
                  <span>Model</span>
                  <input
                    value={settingsForm.model}
                    onChange={(event) =>
                      setSettingsForm((previous) => ({
                        ...previous,
                        model: event.target.value,
                      }))
                    }
                    placeholder="gpt-4o-mini"
                  />
                </label>

                <label>
                  <span>API Key</span>
                  <input
                    type="password"
                    value={settingsForm.api_key}
                    onChange={(event) =>
                      setSettingsForm((previous) => ({
                        ...previous,
                        api_key: event.target.value,
                      }))
                    }
                    placeholder={llmSettings.api_key_set ? "Leave blank to keep current key" : "sk-..."}
                  />
                </label>

                <div className="settings-footer">
                  <p className="muted-copy">
                    {llmSettings.api_key_set
                      ? "A key is already stored locally. Leave the field blank to keep it."
                      : "The API key is stored locally by the backend in plaintext for this MVP."}
                  </p>
                  <button className="action-button" disabled={busy} type="submit">
                    {busy ? "Saving..." : "Save Settings"}
                  </button>
                </div>
              </form>
            </section>
          </div>
        ) : null}
      </main>
    </div>
  );
}
