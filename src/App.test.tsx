import { act, fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import App from "./App";

describe("App", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("renders the home screen and loads history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/history")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              sessions: [
                {
                  session_id: "session-1",
                  role: "agent_engineer",
                  level: "mid",
                  status: "completed",
                  total_score: 82,
                },
              ],
            }),
          });
        }

        return Promise.resolve({
          ok: true,
          json: async () => ({
            configured: true,
            provider: "openai_compatible",
            base_url: "https://api.openai.com/v1",
            model: "gpt-test",
            api_key_set: true,
          }),
        });
      }),
    );

    render(<App />);

    expect(await screen.findByText("Interview Agent")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start Mock Interview" })).toBeTruthy();
    expect(await screen.findByText(/agent engineer/i)).toBeTruthy();
  });

  it("defaults to a 10 minute interview and hides unsupported durations", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/history")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              sessions: [],
            }),
          });
        }

        return Promise.resolve({
          ok: true,
          json: async () => ({
            configured: true,
            provider: "openai_compatible",
            base_url: "https://api.openai.com/v1",
            model: "gpt-test",
            api_key_set: true,
          }),
        });
      }),
    );

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Start Mock Interview" }));

    const durationSelect = (await screen.findByLabelText("Duration")) as HTMLSelectElement;
    expect(durationSelect.value).toBe("10");
    expect(screen.getByRole("option", { name: "10 minutes" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "20 minutes" })).toBeNull();
    expect(screen.queryByRole("option", { name: "30 minutes" })).toBeNull();
  });

  it("opens settings instead of interview config when provider is not configured", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/history")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              sessions: [],
            }),
          });
        }

        return Promise.resolve({
          ok: true,
          json: async () => ({
            configured: false,
            provider: null,
            base_url: null,
            model: null,
            api_key_set: false,
          }),
        });
      }),
    );

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Start Mock Interview" }));

    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.getByLabelText("Base URL")).toBeTruthy();
    expect(screen.getByLabelText("Model")).toBeTruthy();
    expect(screen.getByLabelText("API Key")).toBeTruthy();
  });

  it("updates the interview timer between prompts", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/history")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              sessions: [],
            }),
          });
        }

        if (url.endsWith("/settings/llm")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              configured: true,
              provider: "openai_compatible",
              base_url: "https://api.openai.com/v1",
              model: "gpt-test",
              api_key_set: true,
            }),
          });
        }

        if (url.endsWith("/sessions") && init?.method === "POST") {
          return Promise.resolve({
            ok: true,
            json: async () => ({
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
            }),
          });
        }

        throw new Error(`Unhandled fetch request: ${url}`);
      }),
    );

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
});
