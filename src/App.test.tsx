import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the home screen and loads history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
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
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          sessions: [],
        }),
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
});
