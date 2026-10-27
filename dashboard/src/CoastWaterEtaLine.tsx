import {
  coastEtaBasis,
  coastEtaHasArrived,
  coastEtaLine,
  type CoastWaterEta,
} from "./coastWaterEta";
import type { DisplayUnits } from "./nodeState";

// Without a running Event clock there is nothing to count down against, so nothing is shown.
export function CoastWaterEtaLine({
  eta,
  eventT,
  units,
}: {
  eta: CoastWaterEta | null;
  eventT: number | null;
  units: DisplayUnits;
}) {
  if (eta === null || eventT === null) return null;
  const atGround = coastEtaHasArrived(eta, eventT);
  return (
    <p className={`coast-eta${atGround ? " at-ground" : ""}`}>
      {coastEtaLine(eta, eventT)}
      <span className="coast-eta-basis">{coastEtaBasis(eta, units)}</span>
    </p>
  );
}
