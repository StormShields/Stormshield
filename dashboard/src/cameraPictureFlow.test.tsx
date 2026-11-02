import { act, fireEvent, render, screen, within } from "@testing-library/react";

import { App } from "./App";
import { fakeNodeSnapshot, nepalNodeState } from "./fakeNodeState";
import { STATE_POLL_MS } from "./useNodeState";

let pictureNumber: number;

function stubTheNode({ sandbox }: { sandbox: boolean }) {
  vi.stubGlobal("fetch", async (path: string) => {
    if (path === "/api/state") {
      return Response.json(
        nepalNodeState({
          id: "porch",
          name: "porch",
          sandbox: sandbox ? { label: "SIMULATED" } : null,
          nodes: [
            fakeNodeSnapshot("porch", {
              measurements: { camera: { value: pictureNumber, unit: "pic" } },
            }),
            fakeNodeSnapshot("hilltop", {
              measurements: { camera: { value: 9, unit: "pic" } },
            }),
          ],
        }),
      );
    }
    if (path === "/api/sandbox/nodes") {
      return Response.json({
        radio_range_m: 1000,
        offered_kinds: ["camera"],
        suggested_sites: [],
        nodes: [],
      });
    }
    if (path === "/api/sandbox/regions") return Response.json({ current: "nepal", regions: [] });
    return new Response(null, { status: 404 });
  });
}

beforeEach(() => {
  pictureNumber = 1;
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

async function renderedCard(name: string) {
  if (!document.body.firstChild) render(<App />);
  return await screen.findByRole("region", { name: `Node ${name}` });
}

test("in the Sandbox a Camera line opens its picture, marked SIMULATED, and it follows the picture number", async () => {
  stubTheNode({ sandbox: true });
  const card = await renderedCard("hilltop");
  const line = await within(card).findByRole("button", { name: "Camera: Picture 9" });
  expect(within(card).queryByRole("img")).not.toBeInTheDocument();

  fireEvent.click(line);
  const picture = within(card).getByRole("img", { name: "Simulated camera picture" });
  expect(picture.tagName).toBe("IMG");
  expect(picture.getAttribute("src")).toBe("/api/sandbox/sensors/hilltop/picture?picture=9");
  const figure = picture.closest("figure") as HTMLElement;
  expect(within(figure).getByText("SIMULATED")).toBeInTheDocument();
  expect(
    within(figure).getByText(/Stays on this Camera; it does not cross the Mesh/),
  ).toBeInTheDocument();

  const porch = await renderedCard("porch");
  fireEvent.click(within(porch).getByRole("button", { name: "Camera: Picture 1" }));
  expect(within(porch).getByRole("img").getAttribute("src")).toContain("picture=1");
  pictureNumber = 2;
  await act(() => vi.advanceTimersByTimeAsync(STATE_POLL_MS));
  expect(
    await within(porch).findByRole("button", { name: "Camera: Picture 2" }),
  ).toBeInTheDocument();
  expect(within(porch).getByRole("img").getAttribute("src")).toContain("picture=2");

  fireEvent.click(within(porch).getByRole("button", { name: "Camera: Picture 2" }));
  expect(within(porch).queryByRole("img")).not.toBeInTheDocument();
});

test("outside the Sandbox only the connected Node's own Camera can open", async () => {
  stubTheNode({ sandbox: false });
  const other = await renderedCard("hilltop");
  expect(within(other).queryByRole("button", { name: /Camera/ })).not.toBeInTheDocument();
  expect(within(other).getByText("Camera: Picture 9")).toBeInTheDocument();

  const own = await renderedCard("porch");
  fireEvent.click(await within(own).findByRole("button", { name: "Camera: Picture 1" }));
  expect(within(own).getByRole("img").getAttribute("src")).toBe("/api/camera/picture?picture=1");
});
