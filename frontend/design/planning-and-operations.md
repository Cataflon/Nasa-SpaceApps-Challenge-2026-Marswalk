# Planning and operations

## Latest layout and rendering pass

- Waypoint rows have separate selection, trip membership and deletion actions. Itinerary rows use numbered stops, reorder and remove controls. Mission plan lists custom waypoints as well as catalog targets; custom selection uses local preview until the backend contract extension is implemented.
- Planning has one Open simulation action. The user can collapse the desktop sidebar. An active floating map reserves a gutter beside the dashboard on desktop/tablet; compact layouts reserve bottom space. Fullscreen layers live inside MapView and are suppressed in the small PiP viewport.
- Analytic layers snapshot and restore the original material and color attribute. This fixes the dark surface after disabling Slope. Labels project each active frame; expensive terrain occlusion is throttled independently. No hardware FPS claim is made.
- Simulation puts the terrain/devices first, a compact copilot status above them and controls/event configuration below. Chat was removed. Event parameters match the existing engine fields and use explicit coordinates, meters, degrees and m/s; recorded demo events remain presets.
- Shared sensor source is a labeled select, with one receive timestamp per telemetry block. Sensor illustrations use SVG viewBox cropping and preserveAspectRatio instead of stretching sprite tiles.
- Native Electron checks covered waypoint membership/reorder layout, manual sidebar collapse, fullscreen layers, Slope on/off color restoration, map rotation, PiP gutter, custom stop selection in Mission plan, simulation section order/event fields and sensor illustration proportions. Full real-backend E2E and Playwright were not run.
- Integration handoff: [Frontend / backend / algorithm contract](../contracts/FRONTEND_BACKEND_ALGORITHM.md). The proposed wire extension is explicitly separate from current runtime support.
- Final validation: 18 Node tests pass and the Electron package is updated. The existing Three.js chunk-size warning remains. JSON fixtures were parsed and cross-checked against required keys and event serialization; a full external JSON Schema validator and real-backend E2E were not run.

## Follow-up: shared instruments and waypoint trips

- Navigation remains fixed on desktop and sticky at the top of compact layouts. Native Electron QA with increased UI zoom verified that it stays accessible during scrolling.
- Waypoints & trip now sits above the planning map. Saved points can be added to an ordered itinerary, moved earlier/later, and routed from the habitat with an optional return. Build waypoint trip uses the terrain worker to combine slope-weighted legs, measures the complete distance/ascent, and provides Preview trip in the synchronized map, FPV and watch. Editing/removing stops invalidates the generated trip.
- This is a local terrain trip. The current route API takes catalog target IDs; custom waypoints do not gain a mission GO verdict, oxygen budget, hazard validation or live event simulation. Live Start is disabled while viewing a local trip. Selecting the backend mission remains a separate live mode.
- App owns one useEquipmentFeed instance: the source selector, demo clock, diagnostic overrides, history and decoded readings survive page switches. Sensors, Simulation summary, tracker/watch oxygen and instrument oxygen/wind share that instance. A fault produces an unavailable value everywhere instead of falling back to an old mission reading. Demo data remains explicitly identified.
- FPV now smooths a forward direction rather than a world-space target. The camera target is always constructed ahead of the current eye, with a stable downward pitch. Local preview samples by route progress, preserving the return-leg direction when a closed trip retraces the outbound leg. Live navigation projects onto its remaining path.
- Increased spacing separates the terrain, physical tracker and watch; narrower layouts stack before devices become cramped.
- Validation: 15 Node tests pass, including ordered waypoint routing/return, invalid waypoint rejection, closed-trip heading, shared sensor fault/value SSR and existing terrain/contracts tests. Build and local Electron package succeed. Native checks verified waypoint save/add/build/preview, a forward 100 m step, source persistence across pages and an oxygen fault propagated from Sensors to Simulation and devices. Backend custom-stop support and full real-backend E2E remain unavailable; Playwright was not run.

The Electron application has three user-facing pages: Planning, Simulation and Sensors.

## Planning

- The central terrain viewport takes the full content width. Terrain layers open in a dismissible overlay. Site Overview and Reference are absent from application navigation.
- Source metadata and a route legend sit below the map. The source-elevation profile follows, then the expedition dashboard: science catalog, mission planner, budget, map notes and route comparison.
- Once the map scrolls out of view above the window, its existing canvas becomes a floating corner viewport. An observed placeholder preserves page height and avoids an IntersectionObserver feedback loop. ResizeObserver updates the camera and route-line resolution. The viewport can be hidden or restored and has a return-to-map control.
- Terrain clicks create a selection; Map notes saves a name and a waypoint, science, caution or shelter tag. Notes persist in localStorage, per site, up to 100 points. These are unverified annotations. The backend still accepts catalog science IDs for mission stops; annotations do not silently change those API semantics.
- Budgets come from the mission planner. Local slope-weighted/shortest previews do not validate oxygen, hazards or mission feasibility.

## Simulation

- Terrain on the left; rugged first-person tracker and a two-compass watch side by side on the right. Narrow windows stack these sections. Current sensor channels appear below, with a Sensor details link to the existing equipment page. Copilot advice is confined to Simulation.
- A single useNavigationTransport hook owns preview playback, progress, steps and mode. Map, tracker and watch receive the same path and position. Preview steps use meters; both ends are clamped. Reset returns preview to the route start. Preview data is explicitly distinct from telemetry.
- Live mode uses useLive/controlLive, the interpolated astronaut position, and the remaining path. Tracker Start/Pause/Resume/Reset controls the same engine as the operations toolbar. Mission controls and event injection appear only here.
- The backend exposes start/pause/reset/speed, without a seek or reverse command. Forward/backward stepping is available in Route preview; it is disabled in live mode. Pause before switching to preview. Preview movement does not fabricate sensor samples or consume oxygen.
- Copilot route proposals can update an idle mission, retaining the existing chat API. Review the resulting budget in Planning. Planning is locked while the EVA is running or paused.

## Rendering

- Share the fetched terrain grid and habitat data between viewports; do not start routing workers for tracking or first-person scenes.
- Reuse the path distance index with a WeakMap. Keep the simulated map route object stable during local playback so overlays are not rebuilt on every position update.
- Render WebGL on camera/position/layer/overlay changes and active animations. Static scenes retain their last frame. Orbit damping, follow motion, route reveal and camera flights still request rendered frames.
- Adapt pixel ratio and shadow resolution to viewport role. Project/occlude labels at a throttled interval. Preserve source mesh and elevation values.
- This is a rendering strategy, not a measured FPS claim. Hardware profiling remains necessary for target field devices.

## Validation

- Vite production build succeeds. Its existing Three.js chunk-size warning remains.
- 13 Node tests pass: source interpolation/profile, navigation bearings, preview step/clamp behavior, contracts, sensor readings and SSR of planning/operations panels.
- Native Electron QA at 1427 × 810 verified a large planning map, local route selection/profile, floating map, mission generation, simultaneous tracker/watch/map, a synchronized 100 m step, reset, demo Start/Pause, sensor summary/detail navigation, local note save/remove and the layers drawer without Site Overview.
- Backend was unavailable during native QA, so live controls were exercised with the labeled recorded scenario. A full real-backend E2E run and hardware FPS profiling were not completed.
- Playwright specifications were updated to the new flows but not executed: Playwright and its browser are not installed. No dependency or backend changes were made.

Run from `frontend`:

```powershell
node --test tests/audit_pure.test.mjs tests/explorer.test.mjs tests/explorer_render.test.mjs
npm.cmd run build
node desktop/package.mjs
```
