# Update indicator UX

The desktop Arena Companion uses this repository's GitHub Releases as its stable update source.

## Top-bar indicator

- Neutral icon: no known update.
- Checking state: icon shows a checking state.
- Up-to-date state: icon shows a success state.
- Update available: icon changes to the update color and displays a small `1` badge.
- Clicking an available-update icon opens the release notes and Update action.
- Automatic checks never interrupt Arena grinding with a popup; they only light the badge.
- Manual clicks may show the update dialog immediately.

Update/debug configuration belongs in the Tools menu rather than the primary action row.
