import { act, fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import App from "./App";

type MockFetchOptions = {
  configured?: boolean;
  speechSettings?: {
    mode: "browser" | "whisper";
    whisper_model: string;
  };
  sessions?: Array<{
    session_id: string;
    role: string;
    level: string;
    status: string;
    total_score: number | null;
  }>;
  createSessionResponse?: Record<string, unknown>;
  transcriptionText?: string;
};

class FakeSpeechRecognition {
  static instances: FakeSpeechRecognition[] = [];

  lang = "";
  continuous = false;
  interimResults = false;
  onstart: (() => void) | null = null;
  onresult:
    | ((event: {
        resultIndex: number;
        results: {
          length: number;
          [index: number]: {
            isFinal: boolean;
            length: number;
            0: { transcript: string };
          };
        };
      }) => void)
    | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;

  constructor() {
    FakeSpeechRecognition.instances.push(this);
  }

  start() {
    this.onstart?.();
  }

  stop() {
    this.onend?.();
  }

  emitResult(chunks: Array<{ transcript: string; isFinal: boolean }>) {
    const results = chunks.reduce(
      (collection, chunk, index) => {
        collection[index] = {
          isFinal: chunk.isFinal,
          length: 1,
          0: {
            transcript: chunk.transcript,
          },
        };
        return collection;
      },
      { length: chunks.length } as {
        length: number;
        [index: number]: {
          isFinal: boolean;
          length: number;
          0: { transcript: string };
        };
      },
    );

    this.onresult?.({
      resultIndex: 0,
      results,
    });
  }

  emitError(error: string) {
    this.onerror?.({ error });
    this.onend?.();
  }
}

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];

  mimeType = "audio/webm";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstart: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(public stream: MediaStream) {
    FakeMediaRecorder.instances.push(this);
  }

  start() {
    this.onstart?.();
  }

  stop() {
    this.ondataavailable?.({ data: new Blob(["audio"], { type: "audio/webm" }) });
    this.onstop?.();
  }
}

class ThrowingMediaRecorder extends FakeMediaRecorder {
  override start() {
    throw new Error("Unsupported codec");
  }
}

const mockMediaStream = {
  getTracks: () => [
    {
      stop: vi.fn(),
    },
  ],
} as unknown as MediaStream;

function mockFetch({
  configured = true,
  speechSettings = { mode: "browser" as const, whisper_model: "small" },
  sessions = [],
  createSessionResponse,
  transcriptionText = "transcribed answer",
}: MockFetchOptions = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/history")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            sessions,
          }),
        });
      }

      if (url.endsWith("/settings/llm")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            configured,
            provider: configured ? "openai_compatible" : null,
            base_url: configured ? "https://api.openai.com/v1" : null,
            model: configured ? "gpt-test" : null,
            api_key_set: configured,
          }),
        });
      }

      if (url.endsWith("/settings/speech")) {
        if (init?.method === "PUT") {
          return Promise.resolve({
            ok: true,
            json: async () => speechSettings,
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => speechSettings,
        });
      }

      if (url.endsWith("/sessions") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: async () =>
            createSessionResponse ?? {
              session_id: "session-1",
              status: "in_progress",
              question_index: 0,
              question_limit: 3,
              remaining_seconds: 600,
              current_prompt: {
                question_id: "q1",
                question_text: "Tell me about your last project.",
                prompt_type: "main_question",
              },
            },
        });
      }

      if (url.endsWith("/transcriptions") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            text: transcriptionText,
          }),
        });
      }

      throw new Error(`Unhandled fetch request: ${url}`);
    }),
  );
}

async function openInterview() {
  render(<App />);

  await act(async () => {
    await Promise.resolve();
  });

  fireEvent.click(screen.getByRole("button", { name: "Start Mock Interview" }));

  await act(async () => {
    await Promise.resolve();
  });

  fireEvent.click(screen.getByRole("button", { name: "Begin Interview" }));

  await act(async () => {
    await Promise.resolve();
  });
}

describe("App", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    FakeSpeechRecognition.instances = [];
    FakeMediaRecorder.instances = [];
  });

  it("renders the home screen and loads history", async () => {
    mockFetch({
      sessions: [
        {
          session_id: "session-1",
          role: "agent_engineer",
          level: "mid",
          status: "completed",
          total_score: 82,
        },
      ],
    });

    render(<App />);

    expect(await screen.findByText("Interview Agent")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start Mock Interview" })).toBeTruthy();
    expect(await screen.findByText(/agent engineer/i)).toBeTruthy();
  });

  it("defaults to a 10 minute interview and hides unsupported durations", async () => {
    mockFetch();

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Start Mock Interview" }));

    const durationSelect = (await screen.findByLabelText("Duration")) as HTMLSelectElement;
    expect(durationSelect.value).toBe("10");
    expect(screen.getByRole("option", { name: "10 minutes" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "20 minutes" })).toBeNull();
    expect(screen.queryByRole("option", { name: "30 minutes" })).toBeNull();
  });

  it("opens settings instead of interview config when provider is not configured", async () => {
    mockFetch({ configured: false });

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Start Mock Interview" }));

    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.getByLabelText("Base URL")).toBeTruthy();
    expect(screen.getByLabelText("Model")).toBeTruthy();
    expect(screen.getByLabelText("API Key")).toBeTruthy();
  });

  it("updates the interview timer between prompts", async () => {
    vi.useFakeTimers();
    mockFetch();
    await openInterview();

    expect(screen.getByText("10:00")).toBeTruthy();

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    expect(screen.getByText("09:59")).toBeTruthy();

    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    expect(screen.getByText("09:56")).toBeTruthy();
  });

  it("shows a disabled voice input button when speech recognition is unavailable", async () => {
    mockFetch();
    await openInterview();

    const voiceButton = screen.getByRole("button", { name: "Start voice input" });
    expect(voiceButton.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText("Voice input is unavailable in this browser. Use text input instead."),
    ).toBeTruthy();
  });

  it("fills the answer box from recognized speech after stopping", async () => {
    mockFetch();
    vi.stubGlobal("webkitSpeechRecognition", FakeSpeechRecognition);

    await openInterview();

    fireEvent.change(screen.getByLabelText("Your answer"), {
      target: { value: "I built an agent" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Start voice input" }));

    expect(screen.getByText("Listening...")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Stop voice input" })).toBeTruthy();

    const recognition = FakeSpeechRecognition.instances[0];
    await act(async () => {
      recognition.emitResult([{ transcript: "that used tools", isFinal: false }]);
    });
    expect(screen.getByText((content) => content.includes("Preview:"))).toBeTruthy();
    expect(screen.getByText("that used tools")).toBeTruthy();

    await act(async () => {
      recognition.emitResult([{ transcript: "with looped reasoning", isFinal: true }]);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Stop voice input" }));
    });

    expect(screen.getByDisplayValue("I built an agent with looped reasoning")).toBeTruthy();
    expect(
      screen.getByText("Voice input added to your answer. Review the text before submitting."),
    ).toBeTruthy();
  });

  it("switches voice input to English before starting recognition", async () => {
    mockFetch();
    vi.stubGlobal("webkitSpeechRecognition", FakeSpeechRecognition);

    await openInterview();

    fireEvent.click(screen.getByRole("button", { name: "English" }));
    fireEvent.click(screen.getByRole("button", { name: "Start voice input" }));

    const recognition = FakeSpeechRecognition.instances[0];
    expect(recognition.lang).toBe("en-US");
    expect(
      screen.getByText("Listening in English. Click stop when you finish speaking."),
    ).toBeTruthy();
  });

  it("records audio and uses whisper transcription when speech mode is whisper", async () => {
    mockFetch({
      speechSettings: {
        mode: "whisper",
        whisper_model: "small",
      },
      transcriptionText: "mixed language answer",
    });
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn(async () => mockMediaStream),
      },
    });

    await openInterview();

    expect(
      screen.getByText("Voice input uses Whisper. The language buttons provide an optional hint for transcription."),
    ).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
    });

    expect(screen.getByText("Recording for Whisper transcription. Click stop when you finish speaking.")).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    });

    expect(screen.getByDisplayValue("mixed language answer")).toBeTruthy();
  });

  it("cleans up the microphone stream if whisper recording cannot start", async () => {
    const stopTrack = vi.fn();
    const localMediaStream = {
      getTracks: () => [
        {
          stop: stopTrack,
        },
      ],
    } as unknown as MediaStream;

    mockFetch({
      speechSettings: {
        mode: "whisper",
        whisper_model: "small",
      },
    });
    vi.stubGlobal("MediaRecorder", ThrowingMediaRecorder);
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn(async () => localMediaStream),
      },
    });

    await openInterview();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
    });

    expect(stopTrack).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText("Recording could not start. Continue with text input or try again."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start recording" })).toBeTruthy();
  });

  it("shows a permission error and falls back to text input", async () => {
    mockFetch();
    vi.stubGlobal("webkitSpeechRecognition", FakeSpeechRecognition);

    await openInterview();

    fireEvent.click(screen.getByRole("button", { name: "Start voice input" }));

    const recognition = FakeSpeechRecognition.instances[0];
    await act(async () => {
      recognition.emitError("not-allowed");
    });

    expect(
      screen.getByText("Microphone permission was denied. Use text input instead."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start voice input" })).toBeTruthy();
  });
});
