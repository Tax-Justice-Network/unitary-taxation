# Unitary Taxation Explorer — web deployment

**Live at: <https://taxjustice.net/wp-content/uploads/pay-where-you-play/>**
(password-gated with StatiCrypt until the embargo lifts on 2 August 2026;
the deployed file is `encrypted/index.html`, the plain `index.html` is the
ungated master to publish from then on).

`index.html` is the complete website: a single self-contained file (~1 MB)
with all data, fonts and code embedded. **No server code, no database, no
external requests, no dependencies.** It can be hosted anywhere that serves
static files.

## For the web team

- Upload `index.html` as a static file (do NOT paste its contents into a CMS
  rich-text editor). Any static path works, e.g. `/unitary-taxation-explorer/`.
- It renders on desktop and mobile, adapts to light/dark mode, and needs no
  cookies and no JavaScript from any other domain (nothing to add to consent
  banners).
- `unitary_taxation_baseline_results.xlsx` is the companion download (baseline
  results as a spreadsheet); host it next to `index.html` if download links
  are wanted.

## WordPress specifically

Two supported routes — do NOT paste the file's contents into the page editor
(block editors strip or mangle the embedded script):

1. **Static folder (preferred).** With hosting/SFTP access, place `index.html`
   in a folder next to the WordPress install, e.g.
   `public_html/unitary-taxation-explorer/` → the page is live at
   `https://<site>/unitary-taxation-explorer/`, full-screen, no WordPress
   involvement. WordPress happily coexists with static folders.
2. **WordPress page + iframe.** Create a normal page (it keeps the site's
   header and menu) and paste `wordpress_embed_snippet.html` into a
   Custom HTML block — its `src` already points at the live location
   (`https://taxjustice.net/wp-content/uploads/pay-where-you-play/`).
   The app posts its height to the host page, so the iframe grows with the
   content — no nested scrollbar. Updates then never touch WordPress: replace
   the hosted file and the embed follows.

## Updating

The file is generated from the replication package:

```
python src/_results_explorer_build.py
```

which rewrites `output/app/unitary_taxation_explorer.html` AND the copy in
this folder. To update the website, re-run the build and replace the hosted
file with the new `index.html`.

## GitHub Pages (optional fallback)

The primary hosting is the taxjustice.net upload above. If GitHub Pages is
ever wanted as a fallback mirror: Settings → Pages → deploy this folder (via
an Actions workflow, or move/copy it to `/docs`). NOTE: on Free/Team plans a
published Pages site is world-readable even from a private repository — do
not enable Pages before the publication embargo lifts.
