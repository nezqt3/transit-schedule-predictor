# Design QA — Сигнальная сетка

**Source visual:** `C:\Users\user\.codex\skills\artifact-template-signal-grid\assets\reference.png` (unchanged copy of the supplied PNG)
**Rendered implementation:** `C:\Users\user\.codex\visualizations\2026\09\25\01a0d986-7812-7df2-8cb0-e823eac1159e\desktop-final.png`
**Tablet evidence:** `C:\Users\user\.codex\visualizations\2026\09\25\01a0d986-7812-7df2-8cb0-e823eac1159e\tablet-implementation.png`
**Viewport and density:** source 1672 × 941 pixels; desktop browser 1672 × 941 CSS pixels at 1×; tablet browser 834 × 1194 CSS pixels at 1×. No density normalization required.
**State:** eight temporary NDTP verification packets in backend memory, with one alert and selected terminal #777. The final running backend was restarted afterward to clear these packets.

## Findings

No actionable P0/P1/P2 findings remain. The source and browser screenshot were inspected together at their original size, including focused inspection of the left queue/detail column and map markers.

- **Typography:** The cobalt header, strong title, compact terminal rows and numeric facts preserve the source hierarchy. The browser uses Segoe UI/system fallback rather than the mock's exact font; readability is comparable.
- **Layout and spacing:** Header height is 70px in both. The implemented left rail is 390px versus roughly 417px in the reference; the map remains dominant. The queue scrolls independently so the selected terminal stays available.
- **Colors and tokens:** Cobalt, white, pale blue selection, red alarm and green stop states follow the source. Selected and alert markers also differ by icon and outline, not color alone.
- **Map/image quality:** The reference's illustrated map was replaced by live interactive OpenStreetMap tiles with visible attribution. The live cartography is denser than the reference; this is an accepted functional difference. Tiles, zoom and terminal markers were verified in the browser.
- **Copy/content:** Mock route numbers, terminal prefixes and numeric delay forecasts were intentionally removed. `unit_id` is labeled as a terminal ID; the forecast field explicitly says it is unavailable without schedule and current deviation data.
- **Responsive:** At 834px width the map remains the larger column; at 652px it moves above the list and details. No persistent controls are clipped.

## Comparison history

1. First desktop capture showed the selected speed chart pushing the unavailable forecast below the viewport. The chart was made expandable and the forecast moved into the always-visible facts.
2. The first narrow capture showed the map partly above the scroll origin. Replacing `column-reverse` with explicit visual ordering fixed the initial viewport.
3. Final desktop capture shows the forecast row and history toggle in the selected panel, with no browser console errors. The map, list, search and selected detail remained synchronized in browser checks.

**Primary interactions tested:** NDTP TCP packet → backend REST → marker; marker selection → detail; list selection → marker; ID search → filtered markers and detail; zoom controls present; backend unavailable and no-telemetry states visible.
**Follow-up polish:** A quieter tile provider would bring the map closer to the mock if a licensed tile key is supplied.
**final result: passed**
