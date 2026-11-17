# Nikola Catalog

A Python project that turns **one CSV or YAML file into a static website** using [Nikola](https://github.com/getnikola/nikola).

A teacher, club, or small shop can maintain a list in a file instead of writing a web page for every entry. The project generates:

- One index page listing all entries.
- One detail page for each entry.
- Updated pages when the data changes, including removal of pages for deleted entries.

The demo is called **Campus Collection** and contains six student initiatives. The same data structure can describe people, products, or projects.

```text
catalog_data/items.csv                 output/catalog/
  or items.yaml     -> Python + Nikola -> index.html
                                        robotics-lab/index.html
                                        campus-garden/index.html
                                        ...
```

This is a Nikola site with our own local plugin. Nikola is installed as a dependency; its upstream source code is not modified. The project uses Nikola 8.3.3, its Task plugin API, Jinja templates, and the `bootstrap4-jinja` theme.

## 1. Install and run

You need **Python 3.10 or newer**; Python 3.12 is recommended. Open a terminal in the project directory after cloning or downloading the repository.

On macOS or Linux:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
nikola build
nikola auto --address 127.0.0.1 --port 8000
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
nikola build
nikola auto --address 127.0.0.1 --port 8000
```

Use another installed Python version of at least 3.10 if 3.12 is unavailable. On macOS, the system `python3` may be older, so check its version before using it in place of `python3.12`.

Open [http://127.0.0.1:8000/catalog/](http://127.0.0.1:8000/catalog/). Keep the terminal running while editing data; `nikola auto` rebuilds the site and refreshes the browser. Press `Ctrl+C` to stop it.

On later runs, activate the existing environment and run `nikola auto` again. Use `nikola build` on its own when you only need the generated files.

`requirements.txt` contains runtime dependencies; `requirements-dev.txt` also installs pytest. `requirements-lock.txt` records the complete dependency set from the original Python 3.12/macOS environment. Use `requirements-dev.txt` for the normal installation.

## 2. Where do I put my data?

Edit **[`catalog_data/items.csv`](catalog_data/items.csv)**. This is the default source file.

**There is no file-upload button on the website.** The website displays the result. You manage data in a local CSV/YAML file, then Nikola generates the HTML pages.

For example, a CSV file with two entries:

```csv
id,slug,title,description
p001,robotics-lab,Robotics Lab,Students build small robots together.
p002,campus-garden,Campus Garden,A shared garden on campus.
```

This produces three pages: `/catalog/`, `/catalog/robotics-lab/`, and `/catalog/campus-garden/`.

The equivalent YAML file looks like this:

```yaml
items:
  - id: p001
    slug: robotics-lab
    title: Robotics Lab
    description: Students build small robots together.
  - id: p002
    slug: campus-garden
    title: Campus Garden
    description: A shared garden on campus.
```

| Field | Meaning and rules |
| --- | --- |
| `id` | Required, unique string identifying the entry. Keep it stable when editing. |
| `slug` | Required, unique URL segment. Use lowercase English letters or digits, separated by single hyphens: `robotics-lab`. `index` is reserved. |
| `title` | Required, nonempty string displayed as the page title. Unicode is supported. |
| `description` | Optional plain-text string. Defaults to an empty string; line breaks are preserved. |

The order in the file determines the order in the index. Extra fields and duplicate identifiers or slugs are rejected. `id`, `slug`, and `title` are trimmed; description text is preserved.

- **CSV:** use UTF-8 and commas as separators. Quote text containing commas or line breaks. You can export a spreadsheet as CSV; `.xlsx` files are not supported directly.
- **YAML:** the only top-level key is `items`, containing a list. All field values must be strings, so write numeric IDs as `"123"`. Quote boolean-like words or dates when using them as text. Duplicate keys and unsafe YAML tags are rejected.
- **Empty catalog:** use a header-only CSV or `items: []` in YAML.

### Select YAML instead of CSV

Only **one source file** is read per build. To use the included [`catalog_data/items.yaml`](catalog_data/items.yaml), stop the preview and run this in your activated environment on macOS/Linux:

```sh
CATALOG_SOURCE=catalog_data/items.yaml nikola auto --address 127.0.0.1 --port 8000
```

In PowerShell:

```powershell
$env:CATALOG_SOURCE = 'catalog_data/items.yaml'
nikola auto --address 127.0.0.1 --port 8000
```

To choose a permanent default, change the fallback path in `CATALOG_SOURCE` in [`conf.py`](conf.py). An environment variable takes precedence. Restart the preview when switching sources. Editing an unselected file does not change the site's content.

To return to CSV in a terminal where you set the variable, use `unset CATALOG_SOURCE` on macOS/Linux or `Remove-Item Env:CATALOG_SOURCE` in PowerShell, then restart the preview.

## 3. How the code works

The central workflow is:

```text
load and validate all entries
          ↓
prepare the output tracking file
          ↓
render the index + render a page for each entry
          ↓
remove outdated pages and save the current page list
```

**Our Python code** reads and validates data, chooses which pages to create, and tracks pages for cleanup. **Nikola** runs the build tasks, applies the theme, copies assets, tracks dependencies, and provides the preview server. **Jinja templates** define how the title, description, and links appear in HTML.

Read the source in this order:

| File | What to understand |
| --- | --- |
| [`catalog_data/items.csv`](catalog_data/items.csv), [`conf.py`](conf.py) | The input and site settings. |
| [`catalog_core/loader.py`](catalog_core/loader.py) | `Item`, the data model, and `load_items()`, which reads either format and returns validated entries. |
| [`plugins/catalog/catalog.py`](plugins/catalog/catalog.py) | `RenderCatalog`, the Nikola plugin that creates the catalog build task. Start with `gen_tasks()`. |
| [`templates/catalog_index.tmpl`](templates/catalog_index.tmpl), [`templates/catalog_item.tmpl`](templates/catalog_item.tmpl) | One template for the list and one reusable template for every detail page. |
| [`catalog_core/lifecycle.py`](catalog_core/lifecycle.py) | `CatalogOutput`: check ownership, prepare rendering, then finalize cleanup. |
| [`tests/`](tests/) | Examples of correct input, rejected input, and real Nikola builds. |

[`plugins/catalog/catalog.plugin`](plugins/catalog/catalog.plugin) registers the plugin. [`files/assets/css/custom.css`](files/assets/css/custom.css) contains the visual styling.

### Why updating and cleanup need separate code

The plugin creates **one catalog task with ordered actions**: prepare, render the index, render each entry, and finalize. It declares the source, Python modules, and templates as **build dependencies**. An unchanged catalog can be skipped; a relevant change rebuilds the small catalog as a whole. There is no per-record build optimization. `nikola auto` also needs **watched directories** to notice file changes; the plugin registers the source directory and `catalog_core/` for this purpose.

Removing an entry removes its render action and output target from the current catalog task, but it does not automatically delete its old HTML file. `CatalogOutput` therefore keeps two small JSON files inside `output/catalog/`:

- `.catalog-manifest.json`: paths belonging to the previous successful build.
- `.catalog-pending.json`: paths involved in the current or interrupted build.

`prepare()` records the paths before rendering. `finalize()` runs only after all current pages succeed, removes tracked paths no longer needed, saves the new manifest, and removes the pending file. This also allows a later successful build to clean up after an interruption. Unrelated files are preserved.

The whole data file is validated before output is changed. A data error leaves the existing HTML untouched. A rendering error can leave partially updated local pages, but prevents cleanup; fix the error and build again. Do not edit generated HTML or remove its tracking files independently. If tracking state is lost, keep a backup of `output/` and build into a fresh output directory. Use one build process per output directory.

## 4. Check the project

In the activated environment:

```sh
python -m pytest -q
nikola build
nikola check -l
```

Tests cover loading, validation, HTML escaping, additions, changes, deletions, empty input, interrupted builds, the sitemap, and deployment in a subdirectory. Integration tests call the real Nikola CLI. Watcher tests start a local server and check automatic rebuilding for CSV and YAML.

If your environment prohibits local servers, run the remaining tests with:

```sh
python -m pytest -q -m 'not watcher'
```

The included [GitHub Actions workflow](.github/workflows/check.yml) is configured to test Python 3.10 and 3.12, build the site, check links, and save the generated site as an artifact. It does not publish the site. A successful remote run must be checked in your own repository after upload.

## 5. Common questions

| Problem | What to check |
| --- | --- |
| My edits do not appear. | Edit the selected source, save it, and check that `nikola auto` is running without errors. Restart it after switching the source path. |
| The file is rejected. | Read the error in the terminal. Check required fields, unique IDs/slugs, the CSV delimiter, and string values in YAML. |
| `nikola` is not found. | Activate `.venv` in the current terminal and install the requirements. |
| Port 8000 is already used. | Stop the previous preview or use `--port 8001` and open the matching address. |
| I cannot see the catalog. | Open `/catalog/`; the index has a collection section below the introduction. |

## 6. GitHub, deployment, and scope

Upload the project source, including tests and documentation. `.gitignore` excludes the local environment, generated `output/`, cache, and build database. No local `.venv` directory is needed in GitHub.

The generated `output/` directory can be hosted as a static website. Set the real URL before building, including any subdirectory:

```sh
NIKOLA_SITE_URL=https://example.org/school/ nikola build
```

Publish only a successful build, replacing the previous output so that deleted pages also disappear from hosting. Local file changes and `nikola auto` do not publish to the internet.

The current scope is one source file, one collection, one language, and the four fields above. There is no browser uploader, database, login, direct Google Sheets connection, or Markdown rendering in descriptions. Catalog entries are custom pages rather than Nikola blog posts, so RSS, tags, and built-in entry search would need extra integration. The plugin integrates with Nikola's sitemap. Changing `CATALOG_PATH` after a build requires fresh output to avoid leaving files under the old path.

For a walkthrough, demo script, and interview questions, read **[the project defense guide](docs/DEFENSE.md)**.

## References

- [Official Nikola repository](https://github.com/getnikola/nikola)
- [Nikola plugin documentation](https://docs.getnikola.com/en/latest/extending.html)
- [Nikola build internals](https://docs.getnikola.com/en/latest/internals.html)
