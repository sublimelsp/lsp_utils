# Documentation

Install:
 - uv - https://docs.astral.sh/uv/getting-started/installation/

Zensical is installed automatically by uv, using the version pinned in `requirements.txt`.

## Commands

* `make serve` - Start the live-reloading docs server.
* `make build` - Build the documentation site.
* `make clean` - Remove the built site.

## Project layout

    zensical.toml             # The configuration file.
    griffe_sphinx_markup.py   # Converts Sphinx markup in docstrings to Markdown.
    src/
        index.md              # The documentation homepage.
        ...                   # Other markdown pages.

The API reference is generated from the docstrings in `lsp_utils/` with mkdocstrings.
