# Interface cleanup

The interface now prioritizes the contact check and uses expandable supporting sections.

- Centered lookup form, shorter introduction, one primary action and a compact privacy note.
- Three main navigation links; research, registry, methodology and review tools remain in More. The menu supports Escape and closes after selection.
- Examples and coverage statistics expand on demand. The source-check count remains visible in the coverage summary.
- Cleaner verdict cards: official contacts first, additional verified numbers and audit history in expandable groups, and source evidence still accessible.
- Dashboard collection status, state sample counts, language comparison and query evidence expand separately. Open sections survive filter/data refreshes.
- Map categories show Banks, Government and Refunds, with the other categories in More. Empty result filters are hidden until findings exist. Mobile category placement follows the actual search/location-card height, preventing overlap.
- Consistent spacing, larger supporting text, softer borders and responsive form layouts. The keyboard skip control focuses the main content without changing the application route.
- Removed the duplicate Google camera control while retaining the application's map controls. The option is documented in the [Google Maps reference](https://developers.google.com/maps/documentation/javascript/reference/map).

Browser checks covered desktop at 1280px, contact lookup at 390px, and dashboard/map at 320px. The pages fit the viewport; the narrow map had more than six pixels between the location card and category row. Navigation, stored SBI lookup, additional numbers, query/state/language filtering and keyboard skipping were checked. Browser error logs were empty and every static JavaScript file passed syntax checking.

Refresh http://127.0.0.1:8006/#lookup to load the updated assets. These changes update the existing source project and downloadable source bundle.
