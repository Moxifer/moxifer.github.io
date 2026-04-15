# BG3 Dialog Browser

This repository is set up to publish a simple GitHub Pages site for browsing
generated dialog HTML exports.

## How it works

- `index.md` is rendered by GitHub Pages with Jekyll and automatically lists
  every `.html` file under `dialog/`.
- `dialog/` holds the generated dialog pages that are linked from the landing
  page.

## GitHub Pages setup

- Repository name: `moxifer.github.io`
- Recommended Pages source: `main` branch, `/(root)` folder
- Jekyll is not strictly required for GitHub Pages in general, but this repo
  uses the built-in Jekyll/Liquid pass so the landing page can auto-list files
  without maintaining a manual index.

## Adding more dialogs

Commit additional `.html` files under `dialog/` and GitHub Pages should pick
them up on the next publish without any landing-page edits.
