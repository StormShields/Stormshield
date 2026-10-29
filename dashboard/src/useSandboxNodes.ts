import { useCallback, useEffect, useState } from "react";

export const SANDBOX_POLL_MS = 1000;

// One Node as the Sandbox's Hub lists it (GET /api/sandbox/nodes).
export type SandboxNode = {
  id: string;
  name: string;
  role: "sensor" | "hub";
  // The true spot the radio range is measured from.
  position: [number, number];
  // The Nodes within radio range of this one.
  links: string[];
  // Radio hops to the Hub; null when no chain of Nodes reaches it.
  hops: number | null;
  // Whether this Node has the newest Community Warning the Hub sent.
  heard_warning: boolean;
};

// A spot the Region's author suggests for a Sensor, shown while no Sensor sits there.
export type SuggestedSite = { label: string; why: string; position: [number, number] };

export type SandboxNodes = {
  radio_range_m: number;
  nodes: SandboxNode[];
  suggested_sites: SuggestedSite[];
};

export type SandboxFeed = {
  // Null before the first answer, and while the page is not in the Sandbox.
  sandbox: SandboxNodes | null;
  // What the last change the Hub refused or failed to make said; cleared by the next change.
  problem: string | null;
  setRadioRange: (metres: number) => Promise<void>;
  addSensor: (lat: number, lon: number) => Promise<void>;
  moveSensor: (id: string, lat: number, lon: number) => Promise<void>;
  removeSensor: (id: string) => Promise<void>;
};

async function ask(path: string, init?: RequestInit): Promise<SandboxNodes> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const { detail } = await response.json().catch(() => ({ detail: undefined }));
    throw new Error(typeof detail === "string" ? detail : `Node API returned ${response.status}`);
  }
  return response.json();
}

function sendJson(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

// Polls the Sandbox's Node list while `inSandbox`. A change shows at once and then the Hub's
// answer, so the circles, links and hops follow the slider, a new Sensor or a drag without waiting
// for a poll.
export function useSandboxNodes(inSandbox: boolean): SandboxFeed {
  const [sandbox, setSandbox] = useState<SandboxNodes | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    if (!inSandbox) return;
    let stopped = false;
    const poll = () =>
      ask("/api/sandbox/nodes")
        .then((answer) => {
          if (!stopped) setSandbox(answer);
        })
        .catch((error) => console.error(error));
    void poll();
    const timer = setInterval(poll, SANDBOX_POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
      setSandbox(null);
    };
  }, [inSandbox]);

  // Asks the Hub for a change, and reports a refusal instead of throwing: the callers are map
  // handlers and sliders with nowhere to catch it.
  const change = useCallback(async (what: string, path: string, init: RequestInit) => {
    setProblem(null);
    try {
      setSandbox(await ask(path, init));
    } catch (error) {
      console.error(error);
      setProblem(`Could not ${what}: ${(error as Error).message}`);
    }
  }, []);

  const setRadioRange = useCallback(
    async (metres: number) => {
      setSandbox((current) => current && { ...current, radio_range_m: metres });
      await change(
        "set the radio range",
        "/api/sandbox/radio-range",
        sendJson("POST", { radio_range_m: metres }),
      );
    },
    [change],
  );
  const addSensor = useCallback(
    (latitude: number, longitude: number) =>
      change("add the Sensor", "/api/sandbox/sensors", sendJson("POST", { latitude, longitude })),
    [change],
  );
  const moveSensor = useCallback(
    (id: string, latitude: number, longitude: number) =>
      change(
        "move the Sensor",
        `/api/sandbox/sensors/${encodeURIComponent(id)}`,
        sendJson("PUT", { latitude, longitude }),
      ),
    [change],
  );
  const removeSensor = useCallback(
    (id: string) =>
      change(
        "remove the Sensor",
        `/api/sandbox/sensors/${encodeURIComponent(id)}`,
        sendJson("DELETE"),
      ),
    [change],
  );

  return {
    sandbox: inSandbox ? sandbox : null,
    problem,
    setRadioRange,
    addSensor,
    moveSensor,
    removeSensor,
  };
}
