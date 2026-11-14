# Equipment illustrations and wrist navigation

These assets were generated with the built-in ImageGen tool. They are concept illustrations, not actual instrument product photos or a validated suit layout.

- `public/equipment/eva-suit.png`: initial suit illustration.
- `public/equipment/sensor-modules.png`: six-module thumbnail atlas (oxygen, radiation, temperature, pressure, wind, dust).
- `public/equipment/eva-suit-watch.png`: selected suit illustration with a decorative wristwatch. The watch has no sensor entry, connector or hotspot.

## Final watch edit prompt

Edit target: the provided full body EVA spacesuit product illustration. Change ONLY this: add one realistic compact rugged circular wrist navigation watch strapped over the cuff on the astronaut's left wrist (viewer's right), just above the glove. Dark graphite bezel, cream rubber strap, subtle copper details, a tiny dark round dial with a muted orange navigation needle. Angle it naturally to sit on the existing wrist. Keep the entire suit, pose, proportions, crop, lighting, all other equipment, transparent background and all transparent pixels unchanged. No cables, no labels, no callout, no added sensors. The watch is purely a visual accessory. Preserve full boots and helmet exactly.

## Navigation behavior

Two north-up dials use row/column grid coordinates. Row increases southward. Habitat direction is calculated from the interpolated astronaut position to `site.habitat`; distance is straight-line, not a validated return path. Mission direction points toward the next look-ahead position on `tick.remaining_path`. Replanning updates that path automatically. With no live mission, preview follows the selected route and progress slider. Missing positions and arrival do not invent an azimuth. A lost telemetry link holds navigation and displays a link warning.

The clock is the computer's local civil time, explicitly labelled LOCAL, not Mars LTST. No magnetometer or body heading is currently supplied, so the dials do not claim to rotate with the astronaut's wrist.

## Optional equipment diagnostic adapter

The existing mission tick provides numeric `sensors` values. It does not provide measured accuracy, calibration, or hardware fault state. The UI accepts optional `tick.sensor_health[key]` metadata with `state: ok | warning | fault`, `message`, and `accuracy: { value, unit }`. Missing metadata remains visibly unavailable. This adapter does not change the shared API contract. The separate opt-in equipment demo supplies clearly labelled simulated measurements and diagnostics.

Validation: production build passed; 12 navigation assertions covered cardinal bearings, arrival, missing positions, distance and a bent route. Desktop visual inspection verified both watch needles and distances changing independently during playback, plus the wristwatch illustration in Sensors. Live backend positioning and body orientation were not hardware-tested.

## Application icon variant

`public/images/marswalk-app-icon.png`: built-in ImageGen edit of the supplied `marswalk_logo_dark_preview.png`. Final prompt: preserve the complete original two-line white MARS WALK logo, bootprints, orange Mars and orbit; center at 86% width on a near-black warm-brown (#211a15) rounded square, 18% corner radius, 96% canvas coverage, transparent outside the corners, square 1024px output; no old blue background, no added text, perspective, border or outer shadow. The original supplied logos are preserved. Used for the Electron window and favicon.

## Clean suit cutout

`public/equipment/eva-suit-watch-clean.png`: built-in ImageGen background-extraction edit. Final prompt: precisely cut out the existing suit and wristwatch, preserve pose, scale, position and 1024×1536 canvas, remove every background pixel including corner triangles, halo, shadows and gaps between arms/torso and legs; true alpha zero outside the subject, clean antialiased edges. The Sensors page now uses this version. Inspected the alpha channel: all 64 sampled corner positions are fully transparent, and the previously translucent corner pixels are removed. Original artwork versions remain unchanged.
