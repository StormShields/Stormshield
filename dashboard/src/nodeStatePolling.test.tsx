import { act, render, screen } from "@testing-library/react";

import { App } from "./App";
import { fakeNodeSnapshot, nepalNodeState } from "./fakeNodeState";
import { STATE_POLL_MS } from "./useNodeState";

let pressure: number;
let stateRequests: number;
// While set, /api/state never answers, like a Node that has stopped responding mid-request.
let hungUp: boolean;

// Like a real fetch, it fails only when its signal says the request has been given up on.
function neverAnswers(signal?: AbortSignal | null) {
  return new Promise<Response>((_, reject) => {
    const giveUp = () => reject(new Error("request timed out"));
    if (signal?.aborted) giveUp();
    signal?.addEventListener("abort", giveUp);
  });
}

beforeEach(() => {
  pressure = 1015;
  stateRequests = 0;
  hungUp = false;
  vi.stubGlobal("fetch", async (path: string, init?: RequestInit) => {
    if (path === "/api/state") {
      stateRequests += 1;
      if (hungUp) return neverAnswers(init?.signal);
      return Response.json(
        nepalNodeState({
          nodes: [
            fakeNodeSnapshot("porch", {
              measurements: { air_pressure: { value: pressure, unit: "hPa" } },
            }),
          ],
        }),
      );
    }
    return new Response(null, { status: 404 });
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("the screen follows the Node once a second", async () => {
  render(<App />);
  expect(await screen.findByText(/Pressure: 1015 hPa/)).toBeInTheDocument();
  pressure = 990;
  await act(() => vi.advanceTimersByTimeAsync(STATE_POLL_MS));
  expect(screen.getByText(/Pressure: 990 hPa/)).toBeInTheDocument();
});

test("a poll that has not been answered is never joined by another", async () => {
  hungUp = true;
  render(<App />);
  // Short of the 5 s after which the page says Node unreachable instead of Connecting….
  await act(() => vi.advanceTimersByTimeAsync(4 * STATE_POLL_MS));
  expect(stateRequests).toBe(1);
  expect(screen.getByText("Connecting…")).toBeInTheDocument();
});

test("a request the Node never answers is given up on after 2 s, and polling goes on", async () => {
  // The real timeout is a 2 s wait on a clock the fake timers cannot move, so it fires at once here.
  const timeout = vi.spyOn(AbortSignal, "timeout").mockReturnValue(AbortSignal.abort());
  hungUp = true;
  render(<App />);
  await act(() => vi.advanceTimersByTimeAsync(3 * STATE_POLL_MS));
  expect(timeout).toHaveBeenCalledWith(2000);
  expect(stateRequests).toBeGreaterThanOrEqual(3);
});
