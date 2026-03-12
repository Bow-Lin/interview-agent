import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type Role = "agent_engineer" | "backend_engineer" | "frontend_engineer" | "algorithm_engineer";
type Level = "junior" | "mid" | "senior";
type PromptType = "main_question" | "followup";
type View = "home" | "config" | "interview" | "report";
type Provider = "openai_compatible";
type VoiceInputStatus = "unsupported" | "idle" | "listening" | "stopping" | "error";
type SpeechInputMode = "browser" | "whisper";
type VoiceInputLanguage = "zh-CN" | "en-US";
type QuestionSetSourceType = "system" | "upload";

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
  question_set_id: string;
  role: Role;
  level: Level;
  duration_minutes: 10;
  allow_followup: boolean;
};

type QuestionSetSummary = {
  id: string;
  name: string;
  source_type: QuestionSetSourceType;
  status: string;
  question_count: number;
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

type SpeechSettingsState = {
  mode: SpeechInputMode;
  whisper_model: string;
};

type SpeechSettingsForm = {
  mode: SpeechInputMode;
  whisper_model: string;
};

type SpeechRecognitionAlternativeLike = {
  transcript: string;
};

type SpeechRecognitionResultLike = {
  isFinal: boolean;
  length: number;
  [index: number]: SpeechRecognitionAlternativeLike;
};

type SpeechRecognitionResultListLike = {
  length: number;
  [index: number]: SpeechRecognitionResultLike;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: SpeechRecognitionResultListLike;
};

type SpeechRecognitionErrorEventLike = {
  error: string;
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const BUILT_IN_QUESTION_SET_ID = "built_in_default";

const defaultConfig: InterviewConfig = {
  question_set_id: BUILT_IN_QUESTION_SET_ID,
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

const defaultSpeechSettingsForm: SpeechSettingsForm = {
  mode: "browser",
  whisper_model: "small",
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

function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

function mergeRecognizedText(previous: string, recognizedText: string): string {
  const trimmedRecognizedText = recognizedText.trim();
  if (!trimmedRecognizedText) {
    return previous;
  }
  const trimmedPrevious = previous.trim();
  if (!trimmedPrevious) {
    return trimmedRecognizedText;
  }
  return `${trimmedPrevious} ${trimmedRecognizedText}`;
}

function getVoiceLanguageLabel(language: VoiceInputLanguage): string {
  return language === "zh-CN" ? "Chinese" : "English";
}

function getSpeechModeLabel(mode: SpeechInputMode): string {
  return mode === "whisper" ? "Whisper" : "Browser";
}

function getWhisperLanguageHint(language: VoiceInputLanguage): string {
  return language === "zh-CN" ? "zh" : "en";
}

function canUseWhisperRecording(): boolean {
  return typeof window.MediaRecorder !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);
}

function getVoiceInputMessage(
  status: VoiceInputStatus,
  language: VoiceInputLanguage,
  mode: SpeechInputMode,
): string {
  if (mode === "whisper") {
    switch (status) {
      case "unsupported":
        return "Whisper recording is unavailable in this browser. Use text input instead.";
      case "listening":
        return "Recording for Whisper transcription. Click stop when you finish speaking.";
      case "stopping":
        return "Uploading audio to Whisper...";
      case "error":
        return "Whisper transcription failed. Continue with text input or try again.";
      case "idle":
      default:
        return `Voice input uses ${getSpeechModeLabel(
          mode,
        )}. The language buttons provide an optional hint for transcription.`;
    }
  }

  switch (status) {
    case "unsupported":
      return "Voice input is unavailable in this browser. Use text input instead.";
    case "listening":
      return `Listening in ${getVoiceLanguageLabel(language)}. Click stop when you finish speaking.`;
    case "stopping":
      return "Processing your speech...";
    case "error":
      return "Voice input stopped. Continue with text input or try again.";
    case "idle":
    default:
      return `Voice input is set to ${getVoiceLanguageLabel(
        language,
      )}. Review the text before submitting.`;
  }
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: isFormData
      ? init?.headers
      : {
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
  const [questionSets, setQuestionSets] = useState<QuestionSetSummary[]>([]);
  const [config, setConfig] = useState<InterviewConfig>(defaultConfig);
  const [session, setSession] = useState<SessionState | null>(null);
  const [displayRemainingSeconds, setDisplayRemainingSeconds] = useState<number | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [answer, setAnswer] = useState("");
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voiceInputLanguage, setVoiceInputLanguage] = useState<VoiceInputLanguage>("zh-CN");
  const [speechSettings, setSpeechSettings] = useState<SpeechSettingsState>({
    mode: "browser",
    whisper_model: "small",
  });
  const [voiceInputStatus, setVoiceInputStatus] = useState<VoiceInputStatus>("unsupported");
  const [voiceInputMessage, setVoiceInputMessage] = useState(
    getVoiceInputMessage("unsupported", "zh-CN", "browser"),
  );
  const [interimTranscript, setInterimTranscript] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [questionBankUploadOpen, setQuestionBankUploadOpen] = useState(false);
  const [questionBankFile, setQuestionBankFile] = useState<File | null>(null);
  const [pendingConfigRedirect, setPendingConfigRedirect] = useState(false);
  const [llmSettings, setLlmSettings] = useState<LLMSettingsState>({
    configured: false,
    provider: "openai_compatible",
    base_url: "",
    model: "",
    api_key_set: false,
  });
  const [settingsForm, setSettingsForm] = useState<LLMSettingsForm>(defaultSettingsForm);
  const [speechSettingsForm, setSpeechSettingsForm] =
    useState<SpeechSettingsForm>(defaultSpeechSettingsForm);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const recognizedTranscriptRef = useRef("");
  const suppressVoiceEndRef = useRef(false);
  const voiceErrorMessageRef = useRef<string | null>(null);
  const voiceErrorStatusRef = useRef<VoiceInputStatus>("idle");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    void loadHistory();
    void loadQuestionSets();
    void loadLLMSettings();
    void loadSpeechSettings();
  }, []);

  useEffect(() => {
    if (view !== "interview" || !session) {
      setDisplayRemainingSeconds(null);
      return;
    }

    setDisplayRemainingSeconds(session.remaining_seconds);
    if (session.remaining_seconds <= 0) {
      return;
    }

    const deadline = Date.now() + session.remaining_seconds * 1000;
    const timerId = window.setInterval(() => {
      setDisplayRemainingSeconds(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)));
    }, 1000);

    return () => {
      window.clearInterval(timerId);
    };
  }, [session, view]);

  useEffect(() => {
    if (view !== "interview" || !session) {
      stopVoiceInput(true);
      setVoiceInputStatus("unsupported");
      setVoiceInputMessage(
        getVoiceInputMessage("unsupported", voiceInputLanguage, speechSettings.mode),
      );
      setInterimTranscript("");
      return;
    }

    const nextStatus =
      speechSettings.mode === "whisper"
        ? canUseWhisperRecording()
          ? "idle"
          : "unsupported"
        : getSpeechRecognitionConstructor()
          ? "idle"
          : "unsupported";
    setVoiceInputStatus(nextStatus);
    setVoiceInputMessage(getVoiceInputMessage(nextStatus, voiceInputLanguage, speechSettings.mode));
    setInterimTranscript("");

    return () => {
      stopVoiceInput(true);
    };
  }, [session, view, voiceInputLanguage, speechSettings.mode]);

  useEffect(() => {
    if (busy) {
      stopVoiceInput(true);
    }
  }, [busy]);

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

  async function loadQuestionSets() {
    try {
      const payload = await apiRequest<{ question_sets: QuestionSetSummary[] }>("/question-sets");
      setQuestionSets(payload.question_sets);
      setConfig((previous) => {
        const stillExists = payload.question_sets.some((questionSet) => questionSet.id === previous.question_set_id);
        return {
          ...previous,
          question_set_id: stillExists
            ? previous.question_set_id
            : payload.question_sets[0]?.id ?? BUILT_IN_QUESTION_SET_ID,
        };
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load question banks.");
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

  async function loadSpeechSettings() {
    try {
      const payload = await apiRequest<SpeechSettingsState>("/settings/speech");
      setSpeechSettings(payload);
      setSpeechSettingsForm(payload);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load speech settings.");
    }
  }

  async function uploadQuestionBank() {
    if (!questionBankFile) {
      setError("Choose a JSON question bank file before importing.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", questionBankFile);
      const imported = await apiRequest<QuestionSetSummary>("/question-sets/import", {
        method: "POST",
        body: formData,
      });
      await loadQuestionSets();
      setConfig((previous) => ({
        ...previous,
        question_set_id: imported.id,
      }));
      setQuestionBankFile(null);
      setQuestionBankUploadOpen(false);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Failed to import question bank.",
      );
    } finally {
      setBusy(false);
    }
  }

  function openSettings(options?: { redirectToConfig?: boolean }) {
    setPendingConfigRedirect(Boolean(options?.redirectToConfig));
    setSettingsOpen(true);
    setError(null);
  }

  function cleanupWhisperRecording(stream?: MediaStream | null, options?: { clearChunks?: boolean }) {
    mediaRecorderRef.current = null;
    const streamToStop = stream ?? mediaStreamRef.current;
    streamToStop?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    if (options?.clearChunks ?? true) {
      audioChunksRef.current = [];
    }
  }

  function stopVoiceInput(silent = false) {
    if (!recognitionRef.current) {
      if (!mediaRecorderRef.current) {
        return;
      }
      suppressVoiceEndRef.current = silent;
      if (!silent) {
        setVoiceInputStatus("stopping");
        setVoiceInputMessage(
          getVoiceInputMessage("stopping", voiceInputLanguage, speechSettings.mode),
        );
      }
      mediaRecorderRef.current.stop();
      return;
    }
    suppressVoiceEndRef.current = silent;
    if (!silent) {
      setVoiceInputStatus("stopping");
      setVoiceInputMessage(getVoiceInputMessage("stopping", voiceInputLanguage, speechSettings.mode));
    }
    recognitionRef.current.stop();
  }

  async function startVoiceInput() {
    if (busy || !session || view !== "interview") {
      return;
    }

    if (speechSettings.mode === "whisper") {
      await startWhisperRecording();
      return;
    }

    const SpeechRecognition = getSpeechRecognitionConstructor();
    if (!SpeechRecognition) {
      setVoiceInputStatus("unsupported");
      setVoiceInputMessage(
        getVoiceInputMessage("unsupported", voiceInputLanguage, speechSettings.mode),
      );
      return;
    }

    setError(null);
    setInterimTranscript("");
    recognizedTranscriptRef.current = "";
    suppressVoiceEndRef.current = false;
    voiceErrorMessageRef.current = null;
    voiceErrorStatusRef.current = "idle";

    const recognition = new SpeechRecognition();
    recognition.lang = voiceInputLanguage;
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => {
      setVoiceInputStatus("listening");
      setVoiceInputMessage(getVoiceInputMessage("listening", voiceInputLanguage, speechSettings.mode));
    };

    recognition.onresult = (event) => {
      let nextInterimTranscript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcriptChunk = result[0]?.transcript?.trim() ?? "";
        if (!transcriptChunk) {
          continue;
        }
        if (result.isFinal) {
          recognizedTranscriptRef.current = mergeRecognizedText(
            recognizedTranscriptRef.current,
            transcriptChunk,
          );
        } else {
          nextInterimTranscript = mergeRecognizedText(nextInterimTranscript, transcriptChunk);
        }
      }
      setInterimTranscript(nextInterimTranscript);
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        voiceErrorStatusRef.current = "error";
        voiceErrorMessageRef.current = "Microphone permission was denied. Use text input instead.";
      } else {
        voiceErrorStatusRef.current = "error";
        voiceErrorMessageRef.current = "Voice input stopped. Continue with text input or try again.";
      }
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      setInterimTranscript("");

      if (suppressVoiceEndRef.current) {
        suppressVoiceEndRef.current = false;
        recognizedTranscriptRef.current = "";
        voiceErrorMessageRef.current = null;
        voiceErrorStatusRef.current = "idle";
        return;
      }

      if (voiceErrorMessageRef.current) {
        setVoiceInputStatus(voiceErrorStatusRef.current);
        setVoiceInputMessage(voiceErrorMessageRef.current);
        voiceErrorMessageRef.current = null;
        voiceErrorStatusRef.current = "idle";
        recognizedTranscriptRef.current = "";
        return;
      }

      const finalTranscript = recognizedTranscriptRef.current.trim();
      if (finalTranscript) {
        setAnswer((previous) => mergeRecognizedText(previous, finalTranscript));
        setVoiceInputMessage("Voice input added to your answer. Review the text before submitting.");
      } else {
        setVoiceInputMessage("No speech recognized. Continue with text input or try again.");
      }
      setVoiceInputStatus(getSpeechRecognitionConstructor() ? "idle" : "unsupported");
      recognizedTranscriptRef.current = "";
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setVoiceInputStatus("error");
      setVoiceInputMessage("Voice input could not start. Continue with text input or try again.");
    }
  }

  async function startWhisperRecording() {
    if (!canUseWhisperRecording()) {
      setVoiceInputStatus("unsupported");
      setVoiceInputMessage(
        getVoiceInputMessage("unsupported", voiceInputLanguage, speechSettings.mode),
      );
      return;
    }

    let stream: MediaStream | null = null;
    try {
      setError(null);
      setInterimTranscript("");
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      suppressVoiceEndRef.current = false;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstart = () => {
        setVoiceInputStatus("listening");
        setVoiceInputMessage(getVoiceInputMessage("listening", voiceInputLanguage, speechSettings.mode));
      };

      recorder.onerror = () => {
        voiceErrorStatusRef.current = "error";
        voiceErrorMessageRef.current = "Whisper transcription failed. Continue with text input or try again.";
      };

      recorder.onstop = async () => {
        cleanupWhisperRecording(undefined, { clearChunks: false });

        if (suppressVoiceEndRef.current) {
          suppressVoiceEndRef.current = false;
          audioChunksRef.current = [];
          return;
        }

        try {
          if (audioChunksRef.current.length === 0) {
            setVoiceInputStatus("error");
            setVoiceInputMessage("No audio was captured. Continue with text input or try again.");
            return;
          }

          const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
          const formData = new FormData();
          formData.append("file", blob, "answer.webm");
          formData.append("language_hint", getWhisperLanguageHint(voiceInputLanguage));

          const payload = await fetch(`${API_BASE_URL}/transcriptions`, {
            method: "POST",
            body: formData,
          });
          if (!payload.ok) {
            throw new Error((await payload.text()) || "Whisper transcription failed.");
          }
          const result = (await payload.json()) as { text: string };
          if (result.text.trim()) {
            setAnswer((previous) => mergeRecognizedText(previous, result.text));
            setVoiceInputStatus("idle");
            setVoiceInputMessage("Voice input added to your answer. Review the text before submitting.");
          } else {
            setVoiceInputStatus("error");
            setVoiceInputMessage("Whisper returned no text. Continue with text input or try again.");
          }
        } catch (requestError) {
          setVoiceInputStatus("error");
          setVoiceInputMessage(
            requestError instanceof Error
              ? requestError.message
              : "Whisper transcription failed. Continue with text input or try again.",
          );
        } finally {
          audioChunksRef.current = [];
        }
      };

      recorder.start();
    } catch (error) {
      cleanupWhisperRecording(stream);
      setVoiceInputStatus("error");
      if (error instanceof DOMException && error.name === "NotAllowedError") {
        setVoiceInputMessage("Microphone permission was denied. Use text input instead.");
        return;
      }
      setVoiceInputMessage("Recording could not start. Continue with text input or try again.");
    }
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
      const speechPayload = await apiRequest<SpeechSettingsState>("/settings/speech", {
        method: "PUT",
        body: JSON.stringify(speechSettingsForm),
      });
      setSpeechSettings(speechPayload);
      setSpeechSettingsForm(speechPayload);
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
    stopVoiceInput(true);
    setView("home");
    setReport(null);
    setSession(null);
    setDisplayRemainingSeconds(null);
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
                    Settings
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
                <span>Question Bank</span>
                <select
                  value={config.question_set_id}
                  onChange={(event) =>
                    setConfig((previous) => ({
                      ...previous,
                      question_set_id: event.target.value,
                    }))
                  }
                >
                  {questionSets.map((questionSet) => (
                    <option key={questionSet.id} value={questionSet.id}>
                      {questionSet.name}
                    </option>
                  ))}
                </select>
              </label>

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

            <div className="upload-card">
              <div className="section-heading upload-heading">
                <div>
                  <h3>Custom question bank</h3>
                  <p className="muted-copy">
                    Import a JSON question bank and use it in the next interview.
                  </p>
                </div>
                <button
                  className="ghost-button"
                  onClick={() => setQuestionBankUploadOpen((previous) => !previous)}
                  type="button"
                >
                  Upload Question Bank
                </button>
              </div>

              {questionBankUploadOpen ? (
                <div className="upload-form">
                  <label>
                    <span>Question Bank JSON</span>
                    <input
                      accept=".json,application/json"
                      onChange={(event) => setQuestionBankFile(event.target.files?.[0] ?? null)}
                      type="file"
                    />
                  </label>
                  <p className="muted-copy">
                    Format: top-level `name` plus a `questions` array matching the built-in schema.
                  </p>
                  <div className="button-row">
                    <button
                      className="action-button"
                      disabled={busy || !questionBankFile}
                      onClick={() => void uploadQuestionBank()}
                      type="button"
                    >
                      {busy ? "Importing..." : "Import Question Bank"}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="config-footer">
              <p className="muted-copy">
                {config.duration_minutes} minute sessions will sample a fixed number of main
                questions and can ask up to two follow-ups per question.
              </p>
              <div className="button-row">
                <button className="ghost-button" onClick={() => openSettings()}>
                  Edit Settings
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
                <span className="timer-chip">
                  {formatSeconds(displayRemainingSeconds ?? session.remaining_seconds)}
                </span>
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
              <div className="voice-input-panel">
                <div className="voice-input-header">
                  <div>
                    <strong>Voice input</strong>
                    <p className="muted-copy">{voiceInputMessage}</p>
                  </div>
                  <button
                    className="ghost-button"
                    disabled={
                      busy || voiceInputStatus === "unsupported" || voiceInputStatus === "stopping"
                    }
                    onClick={() =>
                      voiceInputStatus === "listening" ? stopVoiceInput() : startVoiceInput()
                    }
                    type="button"
                  >
                    {voiceInputStatus === "listening"
                      ? speechSettings.mode === "whisper"
                        ? "Stop recording"
                        : "Stop voice input"
                      : speechSettings.mode === "whisper"
                        ? "Start recording"
                        : "Start voice input"}
                  </button>
                </div>
                <div className="voice-language-row" role="group" aria-label="Voice input language">
                  <span className="muted-copy">
                    {speechSettings.mode === "whisper" ? "Language hint" : "Language"}
                  </span>
                  <div className="button-row">
                    <button
                      aria-pressed={voiceInputLanguage === "zh-CN"}
                      className={`ghost-button ${
                        voiceInputLanguage === "zh-CN" ? "voice-language-button active" : "voice-language-button"
                      }`}
                      disabled={voiceInputStatus === "listening" || voiceInputStatus === "stopping"}
                      onClick={() => setVoiceInputLanguage("zh-CN")}
                      type="button"
                    >
                      中文
                    </button>
                    <button
                      aria-pressed={voiceInputLanguage === "en-US"}
                      className={`ghost-button ${
                        voiceInputLanguage === "en-US" ? "voice-language-button active" : "voice-language-button"
                      }`}
                      disabled={voiceInputStatus === "listening" || voiceInputStatus === "stopping"}
                      onClick={() => setVoiceInputLanguage("en-US")}
                      type="button"
                    >
                      English
                    </button>
                  </div>
                </div>
                <div className="voice-input-meta">
                  <span className={`voice-status-chip ${voiceInputStatus}`}>
                    {voiceInputStatus === "unsupported"
                      ? "Unavailable"
                      : voiceInputStatus === "listening"
                        ? "Listening..."
                        : voiceInputStatus === "stopping"
                          ? "Processing..."
                          : voiceInputStatus === "error"
                            ? "Retry available"
                            : "Ready"}
                  </span>
                  {interimTranscript ? (
                    <p className="voice-preview">
                      Preview: <span>{interimTranscript}</span>
                    </p>
                  ) : null}
                </div>
              </div>
              <div className="answer-actions">
                <span className="muted-copy">Be concise, but cover missing details clearly.</span>
                <button
                  className="action-button"
                  disabled={
                    busy ||
                    voiceInputStatus === "listening" ||
                    voiceInputStatus === "stopping" ||
                    !answer.trim()
                  }
                  type="submit"
                >
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
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="settings-title">
            <section className="card modal-card">
              <div className="section-heading">
                <div>
                  <h2 id="settings-title">Settings</h2>
                  <p className="muted-copy">
                    Configure the LLM endpoint and choose how speech input is captured.
                  </p>
                </div>
                <button className="ghost-button" onClick={() => setSettingsOpen(false)}>
                  Close
                </button>
              </div>

              <form className="form-grid settings-form" onSubmit={saveSettings}>
                <div className="settings-section-title">
                  <strong>LLM</strong>
                </div>
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

                <div className="settings-section-title">
                  <strong>Speech input</strong>
                </div>

                <label>
                  <span>Recognition mode</span>
                  <select
                    value={speechSettingsForm.mode}
                    onChange={(event) =>
                      setSpeechSettingsForm((previous) => ({
                        ...previous,
                        mode: event.target.value as SpeechInputMode,
                      }))
                    }
                  >
                    <option value="browser">Browser speech recognition</option>
                    <option value="whisper">Server-side Whisper</option>
                  </select>
                </label>

                <label>
                  <span>Whisper model</span>
                  <select
                    disabled={speechSettingsForm.mode !== "whisper"}
                    value={speechSettingsForm.whisper_model}
                    onChange={(event) =>
                      setSpeechSettingsForm((previous) => ({
                        ...previous,
                        whisper_model: event.target.value,
                      }))
                    }
                  >
                    <option value="tiny">tiny</option>
                    <option value="base">base</option>
                    <option value="small">small</option>
                    <option value="medium">medium</option>
                    <option value="turbo">turbo</option>
                  </select>
                </label>

                <div className="settings-footer">
                  <p className="muted-copy">
                    {llmSettings.api_key_set
                      ? "A key is already stored locally. Leave the field blank to keep it."
                      : "The API key is stored locally by the backend in plaintext for this MVP."}{" "}
                    Whisper mode also requires the optional server speech dependencies.
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
