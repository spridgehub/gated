# Gated

A shared tracker of UK analogue supercars, live at https://spridgehub.github.io/gated/.

- `docs/` is the static site (GitHub Pages). `docs/data.json` is exported from the tracker database by `python -m gated.build`.
- The site's **Add a car**, **Log price / views** and **New group** buttons open prefilled GitHub issue forms (`.github/ISSUE_TEMPLATE/`).
- On the Mac mini, `bin/publish` applies issues from the crew (`data/crew.json`, GitHub logins), rebuilds `data.json` and ships the site.
- `reports/` holds the daily market scan (Markdown + `state.json` for diffing).
- Every price and view count comes from a live advert. Nothing is estimated; blanks mean nobody has recorded it yet.
