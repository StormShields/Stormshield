import { useMemo, useState } from "react";

import { AlertsPanel } from "./AlertsPanel";
import { firstSurgeAt, flashFloodWarnings } from "./communityWarnings";
import { EvacuationPlanPanel } from "./EvacuationPlanPanel";
import { evacuationPlan } from "./evacuationPlan";
import { HouseholdPanel } from "./HouseholdPanel";
import { HubPanel } from "./HubPanel";
import { latestAlert, officialTag } from "./officialAlerts";
import { MapLegend } from "./MapLegend";
import type { Home } from "./householdProfile";
import { LayerRail, type MapLayerName } from "./LayerRail";
import { useWeatherLayer } from "./weatherLayer";
import { WeatherLegend } from "./WeatherLegend";
import { useForecastTime } from "./useForecastTime";
import { useWeatherGrid } from "./useWeatherGrid";
import { NodeMap } from "./NodeMap";
import { NodePanel } from "./NodePanel";
import { NodeSheet } from "./NodeSheet";
import { PhoneTabs, type PhoneTab } from "./PhoneTabs";
import { defaultPanels, useOpenPanels, type PanelName } from "./openPanels";
import { usePlaces } from "./placeLabels";
import { nodesOnMap } from "./nodesOnMap";
import { ReadingsPanel } from "./ReadingsPanel";
import { SandboxPanel } from "./SandboxPanel";
import { StatusStrip } from "./StatusStrip";
import { readTerrainChoice, saveTerrainChoice, type TerrainChoice } from "./terrain";
import { TopBar } from "./TopBar";
import { blockedRoadLines, roadNear } from "./rerouting";
import { useBlockedRoads } from "./useBlockedRoads";
import { useCachePack } from "./useCachePack";
import { useCoastWaterEta } from "./useCoastWaterEta";
import { useGroundHeightCm } from "./groundHeight";
import { useEventClock } from "./useEventClock";
import { useReadingTrends } from "./readingTrends";
import { useContactNotes, useLevelRises } from "./useMarkerEvents";
import { exampleHousehold } from "./exampleHousehold";
import { useHouseholdProfile, type StorageProblem } from "./useHouseholdProfile";
import { PagerBanner } from "./PagerBanner";
import { RegionContext } from "./RegionContext";
import { useNodeState } from "./useNodeState";
import { useSandboxNodes } from "./useSandboxNodes";
import { usePager } from "./usePager";
import { useOpenShelterIds } from "./useOpenShelterIds";
import { useRoadGraph } from "./useRoadGraph";
import { waterReaches as waterReachesAt } from "./risingWater";
import { useRiverLine } from "./useRiverLine";
import { useRoutes } from "./useRoutes";
import { useIsPhone, useIsTablet } from "./useViewport";
import { waveArrival, waveFrontKm } from "./waveEta";
import { WarningBanners, WarningTakeover } from "./WarningTakeover";
import { WarningBand } from "./WarningBand";
import { bannerWarnings, pendingWarnings, useAcknowledgedWarnings } from "./acknowledgedWarnings";
import { WaveEtaCard } from "./WaveEtaCard";

// Only the person at the Node's own machine may change that Node's registration; a phone cannot.
function onThisNodesOwnMachine(): boolean {
  return ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
}

// Pixels from the map's edge that an open Panel covers: the rail and the left Panel, and the right
// Panels (see .panel-column in App.css).
const PANEL_ROOM = { left: 368, right: 360 };

const STORAGE_PROBLEM_MESSAGES: Record<StorageProblem, string> = {
  unreadable:
    "Your saved household profile could not be read, so it is treated as missing. It was not deleted.",
  unsaved: "Your household profile will not be remembered after you close this page.",
};

export function App() {
  const { state, lastAnswer, connection, refresh } = useNodeState();
  const unreachable = connection === "unreachable";
  // Still true of the Node while it is unreachable, unlike its readings.
  const identity = lastAnswer?.state ?? null;
  const floodRisk = state?.flood_risk ?? null;
  const region = state?.region ?? null;
  const hazard = state?.hazard ?? null;
  const { sandbox, problem, setRadioRange, addSensor, moveSensor, removeSensor } = useSandboxNodes(
    state?.sandbox != null,
  );
  const [sandboxPanelOpen, setSandboxPanelOpen] = useState(true);
  const [placingSensor, setPlacingSensor] = useState(false);
  const eventClock = useEventClock(!unreachable);
  const nodes = nodesOnMap(state);
  const rises = useLevelRises(nodes);
  const trends = useReadingTrends(nodes, lastAnswer?.at ?? 0);
  const contactNotes = useContactNotes(nodes);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const toggleSelected = (id: string) => setSelectedId((current) => (current === id ? null : id));
  const { profile, storageProblem, save, remove } = useHouseholdProfile();
  const pager = usePager(nodes, profile?.home ?? null);
  const cachePack = useCachePack();
  const [openShelterIds, showOpenShelterIds] = useOpenShelterIds();
  // Until a resident saves their own profile, an example home keeps the plan and Route on screen.
  const example = profile === null ? exampleHousehold(cachePack) : null;
  const shownProfile = profile ?? example;
  const routes = useRoutes(shownProfile?.home ?? null, cachePack?.routeGrid ?? null);
  const roadGraph = useRoadGraph(cachePack !== null);
  const river = useRiverLine(cachePack !== null);
  const [blockedRoads, toggleBlockedRoad] = useBlockedRoads();
  const [blocking, setBlocking] = useState(false);
  const blockedLines = useMemo(
    () => (roadGraph ? blockedRoadLines(roadGraph, blockedRoads) : []),
    [roadGraph, blockedRoads],
  );
  const tapRoad = (point: Home) => {
    const road = roadGraph && roadNear(roadGraph, point);
    if (road) toggleBlockedRoad(road);
  };
  // Kept while unreachable: each carries its own issue time, and losing an evacuation order to a
  // Wi-Fi drop is worse than showing one a few seconds old.
  const officialAlerts = lastAnswer?.state.official_alerts ?? [];
  const heardWarnings = lastAnswer?.state.community_warnings;
  const communityWarnings = heardWarnings ?? [];
  // Kept until the next poll: the wave layer redraws whenever this array changes.
  const riverWarnings = useMemo(() => flashFloodWarnings(heardWarnings ?? []), [heardWarnings]);
  const eventNow = eventClock.clock?.event_t ?? null;
  const waterReaches =
    river && eventNow !== null ? waterReachesAt(river, riverWarnings, nodes, eventNow) : [];
  // The home never leaves the device: the profile's, or else where the connected Node sits.
  const thisNode = lastAnswer?.state.nodes.find((node) => node.id === lastAnswer.state.id);
  const waveHome: Home | null =
    shownProfile?.home ??
    (thisNode ? { lat: thisNode.position[0], lon: thisNode.position[1] } : null);
  const eventT = eventClock.clock?.event_t ?? null;
  const arrival = river && waveHome && waveArrival(river, waveHome, riverWarnings);
  const onCoast = region?.water_type === "coast";
  const groundCm = useGroundHeightCm(
    onCoast ? waveHome : null,
    cachePack?.basemap?.terrain.zooms ?? null,
  );
  const coastEta = useCoastWaterEta({ region, home: waveHome, groundCm, nodes, eventT });
  // A coast ETA that has arrived hands the plan a wave expected now.
  const planWave =
    arrival && arrival.kind === "expected" && eventT !== null
      ? { arrivalAt: arrival.at, eventT }
      : coastEta && eventT !== null
        ? { arrivalAt: coastEta.kind === "expected" ? coastEta.at : eventT, eventT }
        : null;
  const waveKm = river && eventT !== null ? waveFrontKm(river, riverWarnings, eventT) : null;
  const [acknowledged, acknowledge] = useAcknowledgedWarnings();
  const plan = evacuationPlan({
    profile: shownProfile,
    pack: cachePack,
    openShelterIds,
    floodRisk,
    region,
    hazard,
    routes,
    rerouting: roadGraph && { graph: roadGraph, blocked: blockedRoads },
    officialAlerts,
    wave: planWave,
  });
  const places = usePlaces(cachePack?.basemap != null);
  const warning = officialAlerts.length > 0 || communityWarnings.length > 0;
  const phone = useIsPhone();
  const [phoneTab, setPhoneTab] = useState<PhoneTab>("map");
  const panels = useOpenPanels(defaultPanels(floodRisk?.level ?? null, warning), useIsTablet());
  const [warned, setWarned] = useState(false);
  // Opened once, when the first warning arrives; after that the resident's own choices stand.
  if (warning && !warned) {
    setWarned(true);
    panels.show("alerts", "plan");
  }
  // On a phone each tab shows its Panels in full, so there is nothing to collapse.
  const panel = (name: PanelName) =>
    phone
      ? { open: true, onToggle: () => {} }
      : { open: panels.open.includes(name), onToggle: () => panels.toggle(name) };
  const weather = useWeatherLayer();
  // A Replay shows the recorded weather on the Event clock; with none running, the Hub's forecast.
  const replaying = eventClock.clock !== null;
  const forecastTime = useForecastTime();
  const weatherData = useWeatherGrid(
    weather.layer !== "off" && eventClock.heard,
    replaying ? "replay" : "forecast",
  );
  const weatherAtMs = eventClock.clock ? eventClock.clock.event_t * 1000 : forecastTime.atMs;
  const [hiddenLayers, setHiddenLayers] = useState<MapLayerName[]>([]);
  const toggleLayer = (layer: MapLayerName) =>
    setHiddenLayers((hidden) =>
      hidden.includes(layer) ? hidden.filter((each) => each !== layer) : [...hidden, layer],
    );
  const shows = (layer: MapLayerName) => !hiddenLayers.includes(layer);
  const openShelterCount = (cachePack?.shelters ?? []).filter((each) =>
    openShelterIds.includes(each.id),
  ).length;
  // Room the open Panels take, so the map can keep the selected Node clear of them.
  const panelRoom = {
    left: panels.open.includes("readings") ? PANEL_ROOM.left : 0,
    right: panels.open.some((name) => name !== "readings") ? PANEL_ROOM.right : 0,
  };
  const [panelOpen, setPanelOpen] = useState(false);
  const [hubPanelOpen, setHubPanelOpen] = useState(false);
  const [nodePanelOpen, setNodePanelOpen] = useState(false);
  const [terrainChoice, setTerrainChoice] = useState(readTerrainChoice);
  // The frame-rate watch turns terrain off without touching the saved choice (D-35).
  const [terrainDropped, setTerrainDropped] = useState(false);
  const [valleyFlights, setValleyFlights] = useState(0);
  const terrainShown = terrainDropped ? "2d" : terrainChoice;
  const chooseTerrain = (choice: TerrainChoice) => {
    setTerrainChoice(choice);
    setTerrainDropped(false);
    saveTerrainChoice(choice);
  };
  const [picking, setPicking] = useState(false);
  const [draftHome, setDraftHome] = useState<Home | null>(null);
  // The panels slide in over the same edge, so only one is open at a time.
  const openPanel = () => {
    setHubPanelOpen(false);
    setNodePanelOpen(false);
    setDraftHome(profile?.home ?? null);
    setPanelOpen(true);
  };
  const openHubPanel = () => {
    closePanel();
    setNodePanelOpen(false);
    setHubPanelOpen(true);
  };
  const openNodePanel = () => {
    closePanel();
    setHubPanelOpen(false);
    setNodePanelOpen(true);
  };
  const pickHomeOnMap = () => {
    setPhoneTab("map");
    setPicking(true);
  };
  const closePanel = () => {
    setPanelOpen(false);
    setPicking(false);
  };
  const readingsPanel = (
    <ReadingsPanel
      nodes={nodes}
      floodRisk={floodRisk}
      region={region}
      hazard={hazard}
      hubId={state?.role === "hub" ? state.id : null}
      waveKm={waveKm}
      selectedId={selectedId}
      onSelect={toggleSelected}
      rises={rises}
      trends={trends}
      panel={panel("readings")}
    />
  );
  const sandboxPanel = sandbox && (
    <SandboxPanel
      sandbox={sandbox}
      problem={problem}
      onSetRadioRange={setRadioRange}
      placing={placingSensor}
      onTogglePlacing={() => setPlacingSensor((placing) => !placing)}
      onRemoveSensor={removeSensor}
      warningSent={communityWarnings.length > 0}
      eventClock={eventClock}
      panel={
        phone
          ? { open: true, onToggle: () => {} }
          : { open: sandboxPanelOpen, onToggle: () => setSandboxPanelOpen((open) => !open) }
      }
    />
  );
  const alertsPanel = (
    <AlertsPanel
      alerts={officialAlerts}
      region={region}
      warnings={communityWarnings}
      nodes={lastAnswer?.state.nodes ?? []}
      thisNodeId={lastAnswer?.state.id ?? ""}
      appliesToYouIds={plan.officialAlerts.map((alert) => alert.id)}
      firstCommunityWarningAt={firstSurgeAt(communityWarnings)}
      waveArrival={arrival}
      eventT={eventT}
      online={state?.status === "online"}
      acknowledged={acknowledged}
      onAcknowledge={acknowledge}
      panel={panel("alerts")}
    />
  );
  const planPanel = (
    <EvacuationPlanPanel
      plan={plan}
      region={region}
      exampleHome={example !== null}
      handOff={!phone && profile === null}
      waveArrival={arrival}
      coastEta={coastEta}
      eventT={eventT}
      shelterStatusConfirmedAt={unreachable ? (lastAnswer?.at ?? null) : null}
      panel={panel("plan")}
    />
  );
  const latestOfficialAlert = latestAlert(officialAlerts);
  const pending = pendingWarnings(officialAlerts, communityWarnings, acknowledged);
  const allNodes = lastAnswer?.state.nodes ?? [];
  const thisNodeId = lastAnswer?.state.id ?? "";
  // The desktop's band, camera and ring follow the first Community Warning not yet acknowledged.
  const newWarning = pending.find((each) => each.kind === "community");
  const warningFocus =
    !phone && newWarning?.kind === "community"
      ? { key: newWarning.key, nodeId: newWarning.warning.origin }
      : null;
  const acknowledgedWarnings = bannerWarnings(officialAlerts, communityWarnings, acknowledged);
  const warningChip =
    !phone && acknowledgedWarnings.length > 0
      ? {
          community: acknowledgedWarnings.some((each) => each.kind === "community"),
          minutesLeft:
            arrival && arrival.kind === "expected" && eventT !== null
              ? Math.max(0, Math.ceil((arrival.at - eventT) / 60))
              : null,
          onOpen: () => panels.show("alerts"),
        }
      : null;
  const selectedNode = nodes.find((node) => node.id === selectedId);
  return (
    <RegionContext.Provider value={region}>
      <main className={phone ? "phone" : undefined}>
        <TopBar
          phone={phone}
          eventClock={eventClock.clock}
          floodRisk={floodRisk}
          region={region}
          showStormSignal={shows("storm-signal")}
          warningChip={warningChip}
          status={state?.status ?? null}
          householdSaved={profile !== null}
          onOpenHousehold={openPanel}
          onOpenNode={onThisNodesOwnMachine() && identity ? openNodePanel : null}
          onOpenHub={identity?.role === "hub" ? openHubPanel : null}
        />
        {unreachable && (
          <p role="alert" className="banner">
            Node unreachable. Live readings are hidden until it answers again; the map, Shelters and
            your household profile are still here.
          </p>
        )}
        {phone && (
          <WarningBanners shown={acknowledgedWarnings} nodes={allNodes} thisNodeId={thisNodeId} />
        )}
        {storageProblem && (
          <p role="alert" className="banner">
            {STORAGE_PROBLEM_MESSAGES[storageProblem]}
          </p>
        )}
        {panelOpen && (
          <HouseholdPanel
            profile={profile}
            home={draftHome}
            hidden={picking}
            onPickHome={pickHomeOnMap}
            onSave={save}
            onDelete={remove}
            onClose={closePanel}
          />
        )}
        {hubPanelOpen && (
          <HubPanel
            eventClock={eventClock}
            shelters={cachePack?.shelters ?? []}
            openShelterIds={openShelterIds}
            onOpenShelterIdsChanged={showOpenShelterIds}
            onClose={() => setHubPanelOpen(false)}
          />
        )}
        {nodePanelOpen && state && (
          <NodePanel
            registration={state.registration}
            onSignedUp={refresh}
            onClose={() => setNodePanelOpen(false)}
          />
        )}
        {pager.alert && <PagerBanner alert={pager.alert} onDismiss={pager.dismiss} />}
        <div className="stage">
          {!phone && <WarningBand pending={pending} nodes={allNodes} thisNodeId={thisNodeId} />}
          <NodeMap
            nodes={shows("nodes") ? nodes : []}
            rises={rises}
            stormSignalOn={shows("storm-signal") && (floodRisk?.storm_signal.on ?? false)}
            selectedId={selectedId}
            onSelect={toggleSelected}
            home={shownProfile?.home ?? null}
            shelters={shows("shelters") ? (cachePack?.shelters ?? []) : []}
            openShelterIds={openShelterIds}
            floodProne={shows("flood-prone") ? (cachePack?.floodProne ?? null) : null}
            basemap={cachePack?.basemap ?? null}
            places={places}
            river={river}
            warnings={riverWarnings}
            warningFocus={warningFocus}
            clock={eventClock.clock}
            shelter={plan.shelter}
            outOfReachShelter={plan.outOfReachShelter}
            highGround={plan.highGround}
            route={shows("route") ? plan.route : null}
            panelRoom={panelRoom}
            draftHome={panelOpen ? draftHome : null}
            picking={picking}
            onPickHome={setDraftHome}
            onDonePicking={() => setPicking(false)}
            blockedRoadLines={blockedLines}
            canBlockRoads={roadGraph !== null}
            blocking={blocking}
            onToggleBlocking={() => setBlocking((on) => !on)}
            onTapRoad={tapRoad}
            terrain={terrainShown}
            onTerrainSlow={() => setTerrainDropped(true)}
            valleyFlights={valleyFlights}
            weatherLayer={weather.layer}
            weather={weatherData}
            weatherAtMs={weatherAtMs}
            waterReaches={waterReaches}
            sandbox={sandbox}
            placingSensor={
              placingSensor
                ? {
                    onPlace: ({ lat, lon }) => {
                      setPlacingSensor(false);
                      void addSensor(lat, lon);
                    },
                    onCancel: () => setPlacingSensor(false),
                  }
                : null
            }
            onMoveSensor={moveSensor}
          />
          {phone ? (
            <>
              {phoneTab === "map" && (
                <div className="phone-map-overlay">
                  {selectedNode && (
                    <NodeSheet node={selectedNode} onClose={() => setSelectedId(null)} />
                  )}
                  {latestOfficialAlert && (
                    <p role="status" className="pinned-alert">
                      <strong>{officialTag(latestOfficialAlert)}</strong>{" "}
                      {latestOfficialAlert.headline}
                    </p>
                  )}
                </div>
              )}
              {phoneTab !== "map" && (
                <div className="phone-pane">
                  {phoneTab === "readings" && (
                    <>
                      {readingsPanel}
                      {sandboxPanel}
                    </>
                  )}
                  {phoneTab === "alerts" && alertsPanel}
                  {phoneTab === "plan" && (
                    <>
                      <section aria-label="Household Profile" className="panel">
                        <div className="panel-head">
                          <h2>Household Profile</h2>
                        </div>
                        <div className="panel-body">
                          <p>{profile ? "Household profile saved" : "No household profile yet"}</p>
                          <button type="button" onClick={openPanel}>
                            {profile ? "My household" : "Set up your household"}
                          </button>
                        </div>
                      </section>
                      {planPanel}
                    </>
                  )}
                </div>
              )}
            </>
          ) : (
            <>
              <LayerRail
                hiddenLayers={hiddenLayers}
                openPanels={panels.open}
                registeredNodes={nodes.filter((node) => node.registered).length}
                openShelters={openShelterCount}
                onToggleLayer={toggleLayer}
                onTogglePanel={panels.toggle}
                weatherLayer={weather.layer}
                onChooseWeather={weather.choose}
              />
              <WeatherLegend
                layer={weather.layer}
                weather={weatherData}
                replaying={replaying}
                nowMs={forecastTime.nowMs}
                forecastHours={forecastTime.hours}
                onForecastHours={forecastTime.setHours}
              />
              <MapLegend
                basemap={cachePack?.basemap ?? null}
                terrain={terrainShown}
                onChooseTerrain={chooseTerrain}
                onFlyToValley={() => setValleyFlights((count) => count + 1)}
              />
              <div className="panel-column left">
                {readingsPanel}
                {sandboxPanel}
              </div>
              <div className="panel-column right">
                {alertsPanel}
                {planPanel}
              </div>
              <WaveEtaCard arrival={arrival} eventT={eventT} home={waveHome} places={places} />
            </>
          )}
        </div>
        <StatusStrip
          nodes={nodes}
          contactNotes={contactNotes}
          identity={identity}
          connecting={connection === "connecting"}
          status={state?.status ?? null}
          cachePackBuilt={cachePack?.built ?? null}
          cachePackLoaded={cachePack !== null}
          basemap={cachePack?.basemap ?? null}
          terrainDropped={terrainDropped}
          waterDrawn={waterReaches.length > 0}
        />
        {phone && <PhoneTabs tab={phoneTab} onChange={setPhoneTab} />}
        {phone && (
          <WarningTakeover
            pending={pending}
            region={region}
            nodes={allNodes}
            thisNodeId={thisNodeId}
            waveArrival={arrival}
            eventT={eventT}
            online={state?.status === "online"}
            onAcknowledge={acknowledge}
          />
        )}
      </main>
    </RegionContext.Provider>
  );
}
