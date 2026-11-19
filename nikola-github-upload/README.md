# Lab II: Nikola Catalog

The complete, runnable coursework project is in **[nikola-catalog/](nikola-catalog/README.md)**.

It uses [Nikola](https://github.com/getnikola/nikola) to generate one index page and one detail page per CSV or YAML entry. Saving the selected source while the preview runs updates the website. Removing a record removes its old generated page after a successful build.

## Quick start

Install Python 3.10 or newer; Python 3.12 is recommended. Clone or download this fork, open a terminal in its root, then run:

~~~sh
cd nikola-catalog
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m nikola build
python -m nikola auto --address 127.0.0.1 --port 8000
~~~

Open [http://127.0.0.1:8000/catalog/](http://127.0.0.1:8000/catalog/).

Windows instructions, YAML selection, and the complete architecture are in the **[full README](nikola-catalog/README.md)**. Keep the preview running while editing data.

## Where to find everything

| Purpose | Location |
| --- | --- |
| Default CSV input | [nikola-catalog/catalog_data/items.csv](nikola-catalog/catalog_data/items.csv) |
| Equivalent YAML input | [nikola-catalog/catalog_data/items.yaml](nikola-catalog/catalog_data/items.yaml) |
| Site settings | [nikola-catalog/conf.py](nikola-catalog/conf.py) |
| Plugin and registration metadata | [nikola-catalog/plugins/catalog/](nikola-catalog/plugins/catalog/) |
| Data loading and validation | [nikola-catalog/catalog_core/loader.py](nikola-catalog/catalog_core/loader.py) |
| Output tracking and cleanup | [nikola-catalog/catalog_core/lifecycle.py](nikola-catalog/catalog_core/lifecycle.py) |
| HTML templates | [nikola-catalog/templates/](nikola-catalog/templates/) |
| Tests | [nikola-catalog/tests/](nikola-catalog/tests/) |
| Explanation and interview demonstration | [nikola-catalog/docs/DEFENSE.md](nikola-catalog/docs/DEFENSE.md) |

There is no upload button on the website. Edit the selected local CSV/YAML file, then Nikola generates static HTML.

## Verify the project

Run these commands inside the nikola-catalog directory with its virtual environment activated:

~~~sh
python -m pytest -q
python -m nikola build
python -m nikola check -l
~~~

Tests cover CSV/YAML loading, validation, rendering, changes, additions, deletions, empty data, interrupted builds, and automatic rebuilding. Two tests start a local preview server; the environment must allow local ports.

## Repository layout

This fork retains the original Nikola source and the earlier demo-site implementation. The maintained coursework demonstration documented here is the self-contained **nikola-catalog/** site. Run its commands from that subdirectory. It installs the official Nikola release as a dependency and does not modify Nikola's core.

The earlier plugins/catalog/catalog.py at the repository root was an incomplete upload. The complete plugin, registration file, supporting modules, templates, and data now live together inside nikola-catalog/. Use that complete site.

The workflow inside nikola-catalog/.github/ is a standalone-repository example. It does not run automatically while nested inside this fork; no remote CI result is claimed.

Current scope: one selected data file, one collection, one language, and the fields id, slug, title, and description. The preview updates local files; it does not publish the site to the internet.
