import "maplibre-gl/dist/maplibre-gl.css";

import { House, MapPin } from "lucide-react";
import { LngLatBounds, Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { addBasemap, baseStyle, lineCollection, setOverlay } from "./basemap";
import { HATCH_IMAGE, hatchImage, readMapColors, type MapColors } from "./mapStyle";
import { MapMarker } from "./MapMarker";
import type { OfficialGauge } from "./nodeState";
import { officialGaugeLabel } from "./officialGauges";
import { useRegion } from "./RegionContext";
import { regionClockTime } from "./regionTime";
import {
  estimatedLabelSize,
  placeLabels,
  samePlacement,
  type MapLabel,
  type Placement,
  type Side,
} from "./labelPlacement";
import {
  TERRAIN_EXAGGERATION,
  TERRAIN_FROM_ZOOM,
  TERRAIN_PITCH,
  VALLEY_VIEW,
  createFrameWatch,
  type TerrainChoice,
} from "./terrain";
import { markerState } from "./markerState";
import { fieldCorners, paintWeatherField } from "./weatherField";
import type { WeatherLayer } from "./weatherLayer";
import { weatherImageUrl } from "./weatherImageUrl";
import { showWeatherField } from "./weatherOnMap";
import type { WeatherData } from "./useWeatherGrid";
import { NodeMarker } from "./NodeMarker";
import { floodProneCaption, shelterLabel } from "./shelterLabel";
import { visiblePlaces, type Place, type View } from "./placeLabels";
import { highGroundLabel, type Basemap, type HighGroundPin, type Shelter } from "./evacuationPlan";
import type { FloodProneAreas } from "./floodProne";
import type { Home } from "./householdProfile";
import type { LatLon } from "./routeGrid";
import type { NodeOnMap } from "./nodesOnMap";
import type { FlashFloodWarning } from "./communityWarnings";
import type { EventClock } from "./useEventClock";
import { usePrefersReducedMotion } from "./useViewport";
import type { RiverLine } from "./waveEta";
import { nodesTheWavePassed, townsTheWaveReached } from "./waveFront";
import { useRiverFlow } from "./useRiverFlow";
import { RisingWaterLayer } from "./RisingWaterLayer";
import { linkLines, rangeCircles } from "./radioRange";
import type { SandboxNodes } from "./useSandboxNodes";
import type { WaterReach } from "./risingWater";
import { waveFront } from "./waveFront";
import { WaveFrontLayer } from "./WaveFrontLayer";

// Before the pack or any Node says where the Region is, the map shows the whole world.
const WORLD_VIEW = { center: [0, 20] as [number, number], zoom: 1 };
const SPACE_FOR_PANELS = { top: 40, bottom: 40, left: 320, right: 360 };

function viewOf(map: MapLibreMap): View {
  const bounds = map.getBounds();
  return {
    zoom: map.getZoom(),
    bounds: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()],
  };
}

// Only these tags stay on a Node's map label; the rest show on hover and in the Readings Panel.
const TAG_WIDTH_PX = 70;

function mapTagCount(node: NodeOnMap): number {
  const contactLost = markerState(node).contactArc !== null;
  return [contactLost, !node.simulated].filter(Boolean).length;
}

// A town the wave reached keeps the time it arrived beside its name (D-21).
// How long the pitch takes to ease to the valley angle once the fly has landed (D-26).
const TILT_MS = 1500;

// In the Sandbox a Node is drawn where it truly is, the centre of its range circle, not at the
// fuzzed spot its readings carry.
function atTrueSpot(node: NodeOnMap, sandbox: SandboxNodes | null): NodeOnMap {
  const listed = sandbox?.nodes.find((each) => each.id === node.id);
  return listed ? { ...node, position: listed.position } : node;
}

function placeLabelText(
  name: string,
  waveStamps: Map<string, number>,
  timeZone: string | null,
): string {
  const arrivedAt = waveStamps.get(name);
  return arrivedAt === undefined || timeZone === null
    ? name
    : `${name} ${regionClockTime(arrivedAt, timeZone)}`;
}

// Every label that competes for room on screen. None is ever drawn over another: the chosen
// Shelter, the selected Node, key places and real Nodes win, and a label that loses is hidden until
// its marker is hovered. Shelters other than the plan's choice are named only on hover (0078).
function labelsOnScreen(
  map: MapLibreMap,
  view: View,
  places: Place[],
  shelters: Shelter[],
  chosenShelterId: string | undefined,
  nodes: NodeOnMap[],
  selectedId: string | null,
  waveStamps: Map<string, number>,
  timeZone: string | null,
): MapLabel[] {
  const at = (lat: number, lon: number) => map.project([lon, lat]);
  const labels: MapLabel[] = [];
  for (const place of visiblePlaces(places, view)) {
    labels.push({
      id: `place:${place.name}`,
      ...at(place.lat, place.lon),
      ...estimatedLabelSize(placeLabelText(place.name, waveStamps, timeZone), 12),
      rank: 1,
    });
  }
  const chosen = shelters.find((each) => each.id === chosenShelterId);
  if (chosen) {
    labels.push({
      id: `shelter:${chosen.id}`,
      ...at(chosen.pos[0], chosen.pos[1]),
      ...estimatedLabelSize(shelterLabel(chosen, true), 12),
      rank: 0,
    });
  }
  for (const node of nodes) {
    const text = node.label + (node.waterLevelShown !== null ? ` · ${node.waterLevelShown}` : "");
    labels.push({
      id: `node:${node.id}`,
      ...at(node.position[0], node.position[1]),
      ...estimatedLabelSize(text, 13, mapTagCount(node) * TAG_WIDTH_PX),
      rank: node.id === selectedId ? 0 : 2,
    });
  }
  return labels;
}

function setTerrainDrawn(map: MapLibreMap, drawn: boolean) {
  if (!map.getSource("elevation")) return;
  if (drawn === (map.getTerrain() !== null)) return;
  map.setTerrain(drawn ? { source: "elevation", exaggeration: TERRAIN_EXAGGERATION } : null);
  if (!drawn && map.getPitch() > 0) map.easeTo({ pitch: 0 });
}

function floodProneCollection(areas: FloodProneAreas | null): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: (areas?.features ?? []).map(({ geometry }) => ({
      type: "Feature",
      properties: {},
      geometry,
    })),
  };
}

// This Node hears itself before it hears anyone else, so a map with no basemap is re-framed as
// new Nodes appear, until the resident pans or zooms. After that it is never moved again.
function frameUntilMoved(
  map: MapLibreMap,
  moved: { current: boolean },
  basemap: Basemap | null,
  nodes: NodeOnMap[],
) {
  if (moved.current) return;
  if (basemap) {
    const [south, west, north, east] = basemap.bbox;
    map.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: SPACE_FOR_PANELS, animate: false },
    );
  } else if (nodes.length > 0) {
    const bounds = new LngLatBounds();
    for (const {
      position: [lat, lon],
    } of nodes)
      bounds.extend([lon, lat]);
    map.fitBounds(bounds, { padding: 60, maxZoom: 15, animate: false });
  }
}

type Props = {
  nodes: NodeOnMap[];
  // How often each Node's Flood Risk has risen; a new count plays that Node's ring once.
  rises: Record<string, number>;
  stormSignalOn: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  home: Home | null;
  // From the Cache Pack; empty until a Node holds one.
  shelters: Shelter[];
  openShelterIds: string[];
  floodProne: FloodProneAreas | null;
  basemap: Basemap | null;
  places: Place[];
  // The valley's own river line, drawn only when the pack has no basemap.
  river: RiverLine | null;
  // What the wave front needs: the Surges that started it and the Event clock it runs on.
  warnings: FlashFloodWarning[];
  // The Node a new Community Warning started at: it rings and the camera goes to it, once per key.
  warningFocus: { key: string; nodeId: string } | null;
  clock: EventClock | null;
  // The Shelter the Evacuation Plan chose.
  shelter: Shelter | null;
  // The closest Shelter when none can be reached before the wave; drawn dashed, with a line from home.
  outOfReachShelter: Shelter | null;
  // Hand-placed hillside spots, given only while the plan says to get to higher ground (D-45).
  highGround: HighGroundPin[];
  // Government gauges, drawn apart from Nodes: they never count toward Flood Risk.
  officialGauges: OfficialGauge[];
  route: LatLon[] | null;
  // Pixels at each edge that open Panels cover.
  panelRoom: { left: number; right: number };
  // The unsaved spot being chosen in the form; the saved Home is `home`.
  draftHome: Home | null;
  picking: boolean;
  onPickHome: (home: Home) => void;
  onDonePicking: () => void;
  blockedRoadLines: LatLon[][];
  // False until the Cache Pack has a Road graph to block roads on.
  canBlockRoads: boolean;
  blocking: boolean;
  onToggleBlocking: () => void;
  onTapRoad: (point: Home) => void;
  // What the resident (and the frame-rate watch) left terrain at; `onTerrainSlow` is that watch.
  terrain: TerrainChoice;
  onTerrainSlow: () => void;
  // Counts presses of the Valley button; each one flies the camera to the valley.
  valleyFlights: number;
  // The Weather layer on the terrain, and the moment it shows: the Event clock during a Replay,
  // otherwise the forecast time the slider picked (epoch ms).
  weatherLayer: WeatherLayer;
  weather: WeatherData;
  weatherAtMs: number;
  // The water levels the wave has reached, drawn as height lines on the valley walls (D-46).
  waterReaches: WaterReach[];
  // The Sandbox's radio model: each Node's range circle, the links between Nodes in range of each
  // other, and a mark on a Sensor with no path to the Hub. Null outside the Sandbox.
  sandbox: SandboxNodes | null;
  // Set while "Add Sensor" is armed: the next tap on the map places a Sensor instead of doing
  // what a tap does otherwise.
  placingSensor: { onPlace: (spot: Home) => void; onCancel: () => void } | null;
  onMoveSensor: (id: string, lat: number, lon: number) => Promise<void>;
};

export function NodeMap({
  nodes,
  rises,
  stormSignalOn,
  selectedId,
  onSelect,
  home,
  shelters,
  openShelterIds,
  floodProne,
  basemap,
  places,
  river,
  warnings,
  warningFocus,
  clock,
  shelter,
  outOfReachShelter,
  highGround,
  officialGauges,
  route,
  panelRoom,
  draftHome,
  picking,
  onPickHome,
  onDonePicking,
  blockedRoadLines,
  canBlockRoads,
  blocking,
  onToggleBlocking,
  onTapRoad,
  terrain,
  onTerrainSlow,
  valleyFlights,
  weatherLayer,
  weather,
  weatherAtMs,
  waterReaches,
  sandbox,
  placingSensor,
  onMoveSensor,
}: Props) {
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [styleReady, setStyleReady] = useState(false);
  const [view, setView] = useState<View | null>(null);
  const colors = useRef<MapColors | null>(null);
  const moved = useRef(false);
  const reducedMotion = usePrefersReducedMotion();
  const terrainChoice = useRef(terrain);
  const onTerrainSlowRef = useRef(onTerrainSlow);
  useEffect(() => {
    terrainChoice.current = terrain;
    onTerrainSlowRef.current = onTerrainSlow;
  });
  const [placement, setPlacement] = useState<Placement>(new Map());
  const nodeIds = nodes.map((node) => node.id).join();

  const attach = useCallback((container: HTMLDivElement | null) => {
    if (!container) return;
    colors.current = readMapColors();
    const created = new MapLibreMap({
      container,
      style: baseStyle(colors.current),
      ...WORLD_VIEW,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      // The demo laptop has 8 GB: keep few decoded tiles, elevation ones included.
      maxTileCacheSize: 40,
    });
    const markMoved = () => (moved.current = true);
    container.addEventListener("pointerdown", markMoved);
    container.addEventListener("wheel", markMoved);
    created.on("styleimagemissing", ({ id }: { id: string }) => {
      if (id === HATCH_IMAGE && !created.hasImage(id)) {
        created.addImage(id, hatchImage(colors.current!.floodProne));
      }
    });
    // The frame-rate watch listens only while the camera moves and terrain is drawn.
    const frameWatch = createFrameWatch(() => onTerrainSlowRef.current());
    let moving = false;
    created.on("movestart", () => {
      moving = true;
      frameWatch.restart();
    });
    created.on("render", () => {
      if (moving && created.getTerrain()) frameWatch.frame();
    });
    created.on("moveend", () => {
      moving = false;
      setView(viewOf(created));
    });
    // Terrain exists only over the valley; zooming out to the country releases it and flattens
    // the map. Zooming in never tilts it (D-33): only a fly or the Valley button does.
    created.on("zoomend", () => {
      const wanted = terrainChoice.current === "3d" && created.getZoom() >= TERRAIN_FROM_ZOOM;
      setTerrainDrawn(created, wanted);
    });
    created.on("load", () => {
      setView(viewOf(created));
      setStyleReady(true);
    });
    setMap(created);
    return () => {
      container.removeEventListener("pointerdown", markMoved);
      container.removeEventListener("wheel", markMoved);
      created.remove();
      setMap(null);
      setStyleReady(false);
    };
  }, []);

  useEffect(() => {
    if (!map || !styleReady || !basemap || map.getSource("water")) return;
    addBasemap(map, basemap, colors.current!);
  }, [map, styleReady, basemap]);

  // After the basemap effect above, so the river-flow layer exists when it first looks.
  useRiverFlow(map, styleReady && basemap !== null, !reducedMotion);

  // The resident's 2D | 3D choice (and a frame-rate drop) applies at once, tilting or flattening.
  useEffect(() => {
    if (!map || !styleReady || !basemap) return;
    const over = map.getZoom() >= TERRAIN_FROM_ZOOM;
    setTerrainDrawn(map, terrain === "3d" && over);
    if (over) map.easeTo({ pitch: terrain === "3d" ? TERRAIN_PITCH : 0 });
  }, [map, styleReady, basemap, terrain]);

  useEffect(() => {
    if (!map || !styleReady || valleyFlights === 0) return;
    moved.current = true;
    map.flyTo({ ...VALLEY_VIEW, pitch: terrain === "3d" && basemap ? TERRAIN_PITCH : 0 });
    // A flight answers a press of the button; changing 2D | 3D later must not fly again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, styleReady, valleyFlights]);

  // D-26: fly flat to the Surging Node, then ease the pitch to the valley angle. The tilt waits for
  // the flight's own end, so a resident who grabs the map mid-flight is not tilted against.
  const focusKey = warningFocus?.key;
  const focusNode = nodes.find((node) => node.id === warningFocus?.nodeId);
  const focusLat = focusNode?.position[0];
  const focusLon = focusNode?.position[1];
  const focusFound = focusNode !== undefined;
  useEffect(() => {
    if (!map || !styleReady || focusLat === undefined || focusLon === undefined) return;
    moved.current = true;
    const tilted = terrainChoice.current === "3d" && basemap !== null;
    const view = { center: [focusLon, focusLat] as [number, number], zoom: VALLEY_VIEW.zoom };
    if (reducedMotion) {
      map.jumpTo({ ...view, pitch: tilted ? TERRAIN_PITCH : 0 });
      return;
    }
    map.flyTo({ ...view, pitch: 0 });
    if (tilted) {
      map.once("moveend", (event: { originalEvent?: unknown }) => {
        if (!event.originalEvent) map.easeTo({ pitch: TERRAIN_PITCH, duration: TILT_MS });
      });
    }
    // One camera move per warning: the Node's position, the terrain choice and the basemap
    // settling later must not fly again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, styleReady, focusKey, focusFound]);

  useEffect(() => {
    if (map && styleReady) frameUntilMoved(map, moved, basemap, nodes);
    // Re-frame when the set of Nodes or the basemap changes, not on every reading.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, styleReady, basemap, nodeIds]);

  // A Panel opening must not cover the selected Node, so the map's centre moves to the clear part.
  const selected = nodes.find((node) => node.id === selectedId);
  const selectedLat = selected?.position[0];
  const selectedLon = selected?.position[1];
  useEffect(() => {
    if (!map || !styleReady || selectedLat === undefined || selectedLon === undefined) return;
    map.easeTo({
      center: [selectedLon, selectedLat],
      padding: { top: 0, bottom: 0, left: panelRoom.left, right: panelRoom.right },
    });
  }, [map, styleReady, selectedLat, selectedLon, panelRoom.left, panelRoom.right]);

  const floodProneData = useMemo(() => floodProneCollection(floodProne), [floodProne]);
  const valleyRiverData = useMemo(
    () => lineCollection(basemap ? [] : (river ?? []).map((reach) => reach.points)),
    [basemap, river],
  );
  const routeData = useMemo(() => lineCollection(route ? [route] : []), [route]);
  const outOfReachData = useMemo(
    () =>
      lineCollection(
        home && outOfReachShelter ? [[[home.lat, home.lon], outOfReachShelter.pos]] : [],
      ),
    [home, outOfReachShelter],
  );
  const blockedData = useMemo(() => lineCollection(blockedRoadLines), [blockedRoadLines]);
  const sandboxSensors = useMemo(
    () => new Set(sandbox?.nodes.filter((node) => node.role === "sensor").map((node) => node.id)),
    [sandbox],
  );
  const radioRangeData = useMemo(() => rangeCircles(sandbox), [sandbox]);
  const radioLinksData = useMemo(
    () => lineCollection(sandbox ? linkLines(sandbox) : []),
    [sandbox],
  );
  useEffect(() => {
    if (!map || !styleReady) return;
    setOverlay(map, "flood-prone", floodProneData);
    setOverlay(map, "valley-river", valleyRiverData);
    setOverlay(map, "route", routeData);
    setOverlay(map, "out-of-reach-line", outOfReachData);
    setOverlay(map, "blocked-roads", blockedData);
    setOverlay(map, "radio-range", radioRangeData);
    setOverlay(map, "radio-links", radioLinksData);
  }, [
    map,
    styleReady,
    floodProneData,
    valleyRiverData,
    routeData,
    outOfReachData,
    blockedData,
    radioRangeData,
    radioLinksData,
  ]);

  const eventT = clock?.event_t ?? null;
  // The painted field changes at most once a second, as the polled Event clock does.
  useEffect(() => {
    if (!map || !styleReady) return;
    if (weatherLayer === "off" || weather.status !== "ready") {
      showWeatherField(map, null);
      return;
    }
    const image = paintWeatherField(weather.grid, weatherLayer, weatherAtMs);
    showWeatherField(map, {
      url: weatherImageUrl(image),
      corners: fieldCorners(weather.grid.grid),
    });
  }, [map, styleReady, weatherLayer, weather, weatherAtMs]);

  useEffect(() => {
    if (!map) return;
    const onTap = placingSensor
      ? placingSensor.onPlace
      : picking
        ? (point: Home) => onPickHome(point)
        : blocking
          ? (point: Home) => onTapRoad(point)
          : null;
    if (!onTap) return;
    const listener = ({ lngLat }: { lngLat: { lat: number; lng: number } }) =>
      onTap({ lat: lngLat.lat, lon: lngLat.lng });
    map.on("click", listener);
    return () => {
      map.off("click", listener);
    };
  }, [map, placingSensor, picking, blocking, onPickHome, onTapRoad]);

  const region = useRegion();
  const timeZone = region?.time_zone ?? null;
  const waving = river !== null && eventT !== null && warnings.length > 0;
  const wavePassedIds = new Set(waving ? nodesTheWavePassed(river, warnings, nodes, eventT) : []);
  const waveStamps = waving
    ? townsTheWaveReached(river, warnings, places, eventT)
    : new Map<string, number>();

  // The label sits on the water: on the wave's head while terrain is on and moving, otherwise on
  // the highest water level, as a static marked height.
  const highest = waterReaches.reduce<WaterReach | null>(
    (top, reach) => (top === null || reach.levelM > top.levelM ? reach : top),
    null,
  );
  const followsHead = terrain === "3d" && !reducedMotion && waving;
  const waterLabelAt =
    highest === null
      ? null
      : ((followsHead ? waveFront(river, warnings, eventT)?.head : null) ?? highest.at);

  // Derived during render, from the last placement so a label keeps its side until it must move.
  const labels =
    map && view
      ? labelsOnScreen(
          map,
          view,
          places,
          shelters,
          (shelter ?? outOfReachShelter)?.id,
          nodes,
          selectedId,
          waveStamps,
          timeZone,
        )
      : [];
  const nextPlacement = placeLabels(labels, placement);
  if (!samePlacement(nextPlacement, placement)) setPlacement(nextPlacement);
  const sideOf = (id: string): Side => placement.get(id) ?? "right";

  return (
    <section aria-label="Map" className="map-area">
      {floodProne && floodProne.features.length > 0 && (
        <p className="flood-prone-caption">{floodProneCaption(region?.water_type ?? "river")}</p>
      )}
      {picking && (
        <div className="pick-banner">
          Tap the map to place your home
          <button type="button" onClick={onDonePicking}>
            Done
          </button>
        </div>
      )}
      {placingSensor && (
        <div className="pick-banner place-sensor-banner">
          Tap the map to place a Sensor
          <button type="button" onClick={placingSensor.onCancel}>
            Cancel
          </button>
        </div>
      )}
      {canBlockRoads && (
        <div className="pick-banner">
          {blocking ? "Tap a road to block it, or a blocked road to clear it" : "Road closed?"}
          <button type="button" onClick={onToggleBlocking}>
            {blocking ? "Done" : "Block a road"}
          </button>
        </div>
      )}
      <div ref={attach} className={picking || blocking ? "node-map picking" : "node-map"} />
      {map && styleReady && (
        <WaveFrontLayer
          map={map}
          river={river}
          warnings={warnings}
          clock={clock}
          reducedMotion={reducedMotion}
        />
      )}
      {map && styleReady && <RisingWaterLayer map={map} reaches={waterReaches} />}
      {map && waterLabelAt && (
        <MapMarker
          map={map}
          lat={waterLabelAt[0]}
          lon={waterLabelAt[1]}
          className="water-reconstruction"
        >
          RECONSTRUCTION
        </MapMarker>
      )}
      {map &&
        view &&
        visiblePlaces(places, view)
          .filter((place) => placement.get(`place:${place.name}`) !== null)
          .map((place) => (
            <MapMarker
              key={place.name}
              map={map}
              lat={place.lat}
              lon={place.lon}
              className={["place-label", waveStamps.has(place.name) && "wave-reached"]
                .filter(Boolean)
                .join(" ")}
            >
              <span className={`map-label label-${sideOf(`place:${place.name}`)}`}>
                {placeLabelText(place.name, waveStamps, timeZone)}
              </span>
            </MapMarker>
          ))}
      {map &&
        shelters.map((each) => {
          const open = openShelterIds.includes(each.id);
          const chosen = each.id === shelter?.id;
          const outOfReach = each.id === outOfReachShelter?.id;
          return (
            <MapMarker
              key={each.id}
              map={map}
              lat={each.pos[0]}
              lon={each.pos[1]}
              className={
                chosen
                  ? "shelter-marker"
                  : outOfReach
                    ? "shelter-marker out-of-reach"
                    : open
                      ? "shelter-pin"
                      : "shelter-pin closed"
              }
            >
              <MapPin size={18} aria-hidden="true" />
              <span
                className={`map-label shelter-label label-${sideOf(`shelter:${each.id}`)}${
                  placement.get(`shelter:${each.id}`) == null ? " label-hidden" : ""
                }`}
              >
                {shelterLabel(each, open, outOfReach)}
              </span>
            </MapMarker>
          );
        })}
      {map &&
        region &&
        officialGauges.map((gauge) => (
          <MapMarker
            key={`${gauge.agency}:${gauge.station}`}
            map={map}
            lat={gauge.pos[0]}
            lon={gauge.pos[1]}
            className="official-gauge-marker"
          >
            <span className="official-gauge-pin" aria-hidden="true" />
            <span className="map-label official-gauge-label">
              {officialGaugeLabel(gauge, region.display_units, region.time_zone)}
            </span>
          </MapMarker>
        ))}
      {map &&
        highGround.map(({ point, walkMinutes, nearest }) => (
          <MapMarker
            key={point.id}
            map={map}
            lat={point.pos[0]}
            lon={point.pos[1]}
            className={nearest ? "high-ground-pin nearest" : "high-ground-pin"}
          >
            <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
              <path
                d="M10 2.5 18 16.5H2Z M10 7v6.5 M7 10l3-3 3 3"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="map-label high-ground-label label-below">
              {highGroundLabel(point.climb_m, walkMinutes)}
            </span>
          </MapMarker>
        ))}
      {map && draftHome && (
        <MapMarker map={map} lat={draftHome.lat} lon={draftHome.lon} className="home-draft-marker">
          <House size={16} aria-hidden="true" />
        </MapMarker>
      )}
      {map && home && (
        <MapMarker map={map} lat={home.lat} lon={home.lon} className="home-marker">
          <House size={16} aria-hidden="true" />
        </MapMarker>
      )}
      {map &&
        // A removed Sensor lingers in the Hub's readings as a stale Node; the Sandbox no longer has it.
        nodes
          .filter((node) => !sandbox || sandbox.nodes.some((listed) => listed.id === node.id))
          .map((node) => (
            <NodeMarker
              key={node.id}
              map={map}
              node={atTrueSpot(node, sandbox)}
              onDragEnd={
                sandboxSensors.has(node.id)
                  ? (lat, lon) => onMoveSensor(node.id, lat, lon)
                  : undefined
              }
              selected={node.id === selectedId}
              wavePassed={wavePassedIds.has(node.id)}
              rises={rises[node.id] ?? 0}
              originOf={node.id === warningFocus?.nodeId ? warningFocus.key : undefined}
              onSelect={onSelect}
              side={sideOf(`node:${node.id}`)}
              labelHidden={placement.get(`node:${node.id}`) === null}
            />
          ))}
      {map &&
        sandbox?.nodes
          .filter((node) => node.role === "sensor" && node.hops === null)
          .map((node) => (
            <MapMarker
              key={node.id}
              map={map}
              lat={node.position[0]}
              lon={node.position[1]}
              className="no-path-marker"
            >
              no path to Hub
            </MapMarker>
          ))}
      {stormSignalOn && <div className="storm-vignette" aria-hidden="true" />}
    </section>
  );
}
