import { useState } from "react";

import { kindLabel } from "./ReadingsPanel";
import { ReadingSlot } from "./ReadingSlot";

type Props = {
  // The Camera's picture number; the picture is fetched again whenever it changes.
  pictureNumber: number;
  shown: string;
  // Where the newest picture is, or null when this page may not show it.
  pictureUrl: string | null;
};

// A Camera's row. Where the page may show its picture, the line opens it: the Sandbox's Hub passes
// on any Sensor's picture, and outside the Sandbox only this Node's own Camera is reachable.
export function CameraLine({ pictureNumber, shown, pictureUrl }: Props) {
  const [open, setOpen] = useState(false);
  const label = `${kindLabel("camera")}: ${shown}`;
  return (
    <>
      <ReadingSlot value={pictureNumber}>
        {pictureUrl ? (
          <button
            type="button"
            className="camera-toggle"
            aria-expanded={open}
            onClick={(event) => {
              // The card behind the line selects its Node on a click; opening a picture should not.
              event.stopPropagation();
              setOpen((was) => !was);
            }}
          >
            {label}
          </button>
        ) : (
          label
        )}
      </ReadingSlot>
      {pictureUrl && open && (
        <figure className="camera-picture">
          {/* An <img>, never inline markup: a script inside the SVG cannot run. */}
          <img src={`${pictureUrl}?picture=${pictureNumber}`} alt="Simulated camera picture" />
          <figcaption>
            <strong className="tag simulated">SIMULATED</strong> Stays on this Camera; it does not
            cross the Mesh
          </figcaption>
        </figure>
      )}
    </>
  );
}
