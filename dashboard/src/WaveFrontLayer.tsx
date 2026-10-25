import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef } from "react";

import { lineCollection, pointCollection, setOverlay } from "./basemap";
import type { FlashFloodWarning } from "./communityWarnings";
import type { EventClock } from "./useEventClock";
import type { RiverLine } from "./waveEta";
import { waveFront } from "./waveFront";

// The clock is only heard once a second; between answers the front is moved on by the clock's own
// rate, but never further than this, so a stalled poll does not run the front off down the river.
const MAX_GLIDE_MS = 2500;
// The front never steps back for a clock answer that is only a little behind the glide (poll
// jitter); one this far behind is a real jump back (Reset, or a jump to an earlier phase).
const REAL_JUMP_BACK_MS = 5000;
// Redrawing the two sources makes the map re-tile them, which costs more than a frame.
const REDRAW_EVERY_MS = 50;

type Props = {
  map: MapLibreMap;
  river: RiverLine | null;
  warnings: FlashFloodWarning[];
  clock: EventClock | null;
  reducedMotion: boolean;
};

// Draws nothing itself: it moves the wave front, which lives in the map's own layers, so a frame
// costs no React render. With reduced motion the front is a marked reach that moves once per
// clock answer instead of gliding.
export function WaveFrontLayer({ map, river, warnings, clock, reducedMotion }: Props) {
  const eventT = clock?.event_t ?? null;
  const playing = clock?.state === "playing";
  const rate = clock?.rate ?? 1;
  const gliding = playing && !reducedMotion && warnings.length > 0;

  // What the glide reads each frame. A new `warnings` array every poll must not restart it, or the
  // front would snap back to the last clock answer, up to a second old.
  const latest = useRef({ river, warnings });
  const heard = useRef({ eventT, at: performance.now(), rate });
  useEffect(() => {
    latest.current = { river, warnings };
  });
  useEffect(() => {
    heard.current = { eventT, at: performance.now(), rate };
  }, [eventT, rate]);

  const draw = (t: number) => {
    const { river: line, warnings: surges } = latest.current;
    const front = line && surges.length > 0 ? waveFront(line, surges, t) : null;
    setOverlay(map, "wave-trail", lineCollection(front ? [front.trail] : []));
    setOverlay(map, "wave-head", pointCollection(front ? [front.head] : []));
  };

  // At rest (paused, reduced motion, or no Surge yet) the front is drawn once per change.
  useEffect(() => {
    if (!gliding) draw(eventT ?? 0);
    // `draw` reads only refs and `map`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, river, warnings, eventT, gliding]);

  useEffect(() => {
    if (!gliding) return;
    let shown = -Infinity;
    let drawnAt = 0;
    let frame = requestAnimationFrame(function tick(now) {
      frame = requestAnimationFrame(tick);
      if (now - drawnAt < REDRAW_EVERY_MS) return;
      drawnAt = now;
      const { eventT: base, at, rate: perSecond } = heard.current;
      if (base === null) return;
      const glided = Math.min(performance.now() - at, MAX_GLIDE_MS);
      const t = base + (glided / 1000) * perSecond;
      if (t >= shown || shown - t > (REAL_JUMP_BACK_MS / 1000) * perSecond) shown = t;
      draw(shown);
    });
    return () => cancelAnimationFrame(frame);
    // `draw` reads only refs and `map`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, gliding]);

  return null;
}
