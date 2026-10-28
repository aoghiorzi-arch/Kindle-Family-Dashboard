# Today display — layout and physical-size review

Date: 28 October 2026. Target: Kindle Touch D01200, portrait 600×800 at 167 ppi.

## Completed software review

Four fictional scenarios are reproducible with `python3 -m app.review`. The generated `data/display-review/index.html` embeds its images and can be opened without the server. Each board is 91.257 × 121.677 mm (approximately a six-inch diagonal). A 50 mm calibration line appears on each page.

| Scenario | Review coverage | Findings after fixes |
|---|---|---|
| Typical household day | Date, three events, shopping, weather and thought | Clear separation of sections; 600×800 output retained. |
| Long/stale/private/overflow | September date, negative temperature, long forecast/title/attribution, unbroken word, 500 shopping items and four events | Date fits its own column; text stays within the screen; truncation is visible; private event is Busy; extra-event count shown. |
| Empty/unavailable | No events, shopping, weather or thought | Clear empty states; unavailable temperature/sunset use dashes. |
| One-item/private | Singular shopping count and a confidential appointment | Singular wording and privacy masking are correct. |

The generated images were inspected visually. Automated checks measure every drawn text bounding box in these scenarios against the screen, check all twelve month names against the date column, verify privacy and confirm the printable dimensions/calibration line. Existing tests also verify the bundled verse collection fits within two lines.

Fixes: fit long date/temperature text into separate columns; wrap unbroken words and fit the final ellipsis; use the fitted attribution font; fit shopping/sunset text; show extra events and genuine empty-thought feedback. The existing monochrome design, bundled fonts and 167 ppi PNG metadata are preserved.

## Paper acceptance — still required

1. Run `python3 -m app.review` from the repository root.
2. Open `data/display-review/index.html` in a browser.
3. Print at **100% / actual size** with fit-to-page and browser headers/footers disabled.
4. Measure the line: it must be 50 mm. The board itself must be about 91 × 122 mm.
5. Read each board at the intended household viewing distance. Record comfort, small-text readability and any clipping on the sheet.

Software bounds checks and image inspection cannot establish paper readability, actual E Ink contrast or ghosting. Physical Kindle testing remains behind the hardware approval gate; no device was connected or changed for this review.
