# recipes

Mobile recipe viewer for Josh's Notion recipe hub, served at
**https://joshhaaronn.github.io/recipes/**

Notion stays the only place recipes are written. This repo holds a generator that
reads that database and bakes it into one self-contained `index.html`, which GitHub
Pages serves. The page is a snapshot, not a live query - it changes only when the
generator is re-run and pushed.

## Files

| File | What it is |
| --- | --- |
| `index.html` | The whole site. One file: markup, CSS, and every cover image inlined as a webp data URI. No JavaScript, no external requests. ~1.4 MB. |
| `build.py` | Regenerates `index.html` from Notion. |

## Rebuild

```
python3 build.py            # writes ./index.html
python3 build.py out.html   # or to a path you choose
```

Needs Python 3 with Pillow, `curl`, and the `tools` CLI with the user's Notion
integration connected. Takes about 15 seconds.

**No credentials live in this repo, and none belong here - it is public.** The
script shells out to `tools notion ...`, which authenticates through the connected
Notion integration. Pushing to GitHub uses the browser lease signed in as
`joshhaaronn`, whose password is in the vault under the `GitHub` login entry.

## What it reads

Notion data source `338302d3-e376-8022-9690-000b195d7cfb` (the Recipes database).

| Notion property | Type | Used for |
| --- | --- | --- |
| `Name` | title | Card and page title. Rows with an empty title are skipped. |
| `Tags` | multi_select | Tag pills, and the filter chips (ordered by how often each tag is used). |
| `Preparation Time` | number | "N min" in the meta line. |
| `Servings` | number | "serves N" in the meta line. |
| `Ingredients` | rich_text | The categorized one-liner (`produce: ...` / `pantry: ...`), rendered as the collapsible Shopping list. |
| `Instructions` | rich_text | Fallback body only, used when a page has no content blocks. |
| `Notes` | rich_text | The italic source credit at the bottom of a recipe. |
| page cover | - | The card thumbnail and the detail hero. |
| page body | - | The real recipe. Fetched with `notion read-page-markdown` and rendered: `#`/`###` headings, bulleted and numbered lists, `<callout icon="...">` blocks as tip boxes. |

Recipe content is rendered as written in Notion - no substitutions, no added
editorial notes.

## Covers

Notion's own image URLs are signed and expire within the hour, so nothing is
hotlinked. Each cover is downloaded, resized to 900px wide, encoded as webp
(quality 68) and inlined as a data URI. Each image appears once in the file, in a
CSS rule, and is used for both the card thumbnail and the detail hero.

## Publish

Commit `index.html` to `main`. GitHub Pages is configured to deploy from `main`
at `/ (root)`, so the live URL updates about a minute after the commit lands. The
URL never changes, which matters because the page is saved to a phone home screen.

Through the GitHub web UI: **Add file → Upload files** on `main`, drop in the new
`index.html`, commit. Note that an uploaded file can land with a numeric prefix
(`1-index.html`) - if that happens, open the file, edit it, and correct the name
back to `index.html` before committing.

Then confirm the deploy actually served the new bytes:

```
curl -s https://joshhaaronn.github.io/recipes/ | md5sum
md5sum index.html
```

## Design notes for anyone changing it

- Mobile first. Two-column card grid on a phone, three columns above 620px.
- Filtering and the full-screen recipe view are pure CSS, driven by `:target`.
  The filter anchors are absolutely positioned so selecting a tag doesn't scroll
  the header away. Opening a recipe clears the active filter - the back gesture
  restores it.
- Fonts are system only (`ui-serif` for titles, system sans for body), so it looks
  native on iOS and loads nothing.
- `apple-mobile-web-app-*` meta tags are what make Add to Home Screen open it
  full-screen. Don't drop them.
- No search box. That would need JavaScript; everything else deliberately doesn't.
