# Understanding and presenting Nikola Catalog

This guide helps both teammates explain the project. Read the [README](../README.md) for installation and commands, then keep the relevant source files open while following this walkthrough.

## Explain the project in 30 seconds

> Our project generates a website from a CSV or YAML list. A Python plugin validates the file, then asks Nikola to render an index and one page for each entry using Jinja templates. While the local preview is running, saving the data triggers a rebuild. The plugin also tracks generated pages, so removing a record removes its old page after a successful build. The owner edits one data file instead of maintaining many HTML pages.

The sample content is a list of campus initiatives. It is an example of the data, not the core algorithm.

## Follow one record through the program

Take this row from a CSV file:

```csv
id,slug,title,description
p001,robotics-lab,Robotics Lab,Students build small robots together.
```

### 1. Configuration selects the source

In [`conf.py`](../conf.py), `CATALOG_SOURCE` defaults to `catalog_data/items.csv`. Setting the environment variable lets us select a different file without editing Python code. `CATALOG_PATH` defaults to `catalog` and determines the URL prefix.

### 2. The loader produces a common data model

[`load_items()`](../catalog_core/loader.py) selects the CSV or YAML reader from the file extension. It validates every record and returns a list of `Item` objects.

The example becomes:

```python
Item(
    id="p001",
    slug="robotics-lab",
    title="Robotics Lab",
    description="Students build small robots together.",
)
```

Both formats lead to the same model. The renderer does not need separate CSV and YAML logic. No partially validated list is returned: a bad record stops the build before pages are changed.

Key checks: required fields, string values, supported text, allowed URL characters, duplicate IDs/slugs, and unknown fields. YAML uses a safe loader with duplicate-key detection. Error messages identify the source and location.

### 3. The plugin describes the work to Nikola

[`RenderCatalog.gen_tasks()`](../plugins/catalog/catalog.py) loads the entries and determines the desired paths:

```text
index.html
robotics-lab/index.html
```

These paths are relative to `output/catalog/`.

A Nikola task is a description of work: its ordered actions, input dependencies, and output targets. `gen_tasks()` yields one catalog task, which Nikola and its doit build system execute.

The actions run in this order:

```text
prepare -> render index -> render each entry -> finalize
```

The plugin uses Nikola's `site.generic_renderer()` to obtain rendering actions and dependencies that understand the site's theme and templates, then includes them in the single catalog task. It passes a context dictionary: the list of records for the index, or one record for a detail page, plus common site values. If any action fails, later actions, including cleanup, do not run.

The task also tracks the full record list and relevant configuration. An unchanged build can skip the catalog task. A source, template, code, or relevant configuration change rebuilds the whole small catalog; it does not try to optimize individual records.

### 4. Templates create the HTML

[`catalog_index.tmpl`](../templates/catalog_index.tmpl) loops through the records. [`catalog_item.tmpl`](../templates/catalog_item.tmpl) displays a single record. Both extend Nikola's base template.

For example, `{{ item.title|e }}` displays the title and escapes special HTML characters. It does not execute HTML supplied in the data.

The generated page is `output/catalog/robotics-lab/index.html`, available locally at `/catalog/robotics-lab/`. The `slug` controls this address; the `id` identifies the record. The output is ordinary HTML, CSS, and other static assets. It does not need a database or Python server when hosted as static files.

### 5. Cleanup makes deletions work

[`CatalogOutput`](../catalog_core/lifecycle.py) manages three public operations:

| Operation | Purpose |
| --- | --- |
| `validate(desired)` | Check existing tracking data, safe paths, and ownership without changing files. |
| `prepare(desired)` | Record previously known and planned paths in a pending journal before rendering. |
| `finalize(desired)` | After rendering succeeds, delete obsolete tracked pages and save the new manifest. |

Suppose the manifest lists `index.html` and `robotics-lab/index.html`. Removing the row leaves only `index.html` in the desired list:

```text
old tracked pages − desired pages = pages to remove
```

This is necessary because removing an output target from the current build does not automatically delete an HTML file from the previous build. The pending journal also tracks pages written before an interrupted build, so the next successful build can clean them up. Unrelated files are preserved.

### 6. Watching triggers the next build

Two mechanisms have different jobs:

- **File dependencies** tell the build system whether a task's inputs have changed.
- **Watched directories** let `nikola auto` notice a save and start a new build.

The plugin registers both. After cleanup, Nikola's sitemap scan sees the final set of generated URLs.

## Questions you should be able to answer

**What did you implement, and what comes from Nikola?**  
Our code handles data loading, validation, the catalog build task, and removal of stale pages. Nikola provides the build engine, template/theme integration, asset handling, sitemap generation, and local preview. We use its public plugin API instead of modifying upstream code.

**Why create a plugin?**  
One data record needs one output page. A Task plugin can generate these pages dynamically during a normal `nikola build`. One task with ordered actions keeps the implementation easy to follow, and the pages share templates.

**Why support both CSV and YAML?**  
CSV is convenient for spreadsheet exports. YAML is readable as structured text. We convert either to `Item` objects, then use one rendering pipeline.

**What is the difference between `id` and `slug`?**  
`id` is a stable identifier. `slug` appears in the URL. Renaming a title keeps the URL; changing a slug creates a new URL and removes the previous page. Redirects are not generated.

**Does one YAML file produce one page?**  
It contains a list. A file with three entries produces four pages: one index and three detail pages.

**Where does the user upload a file?**  
The current version has no browser upload. The owner edits the selected local CSV/YAML file or replaces it with a correctly formatted export. The website displays the generated result.

**What happens with invalid data?**  
The loader raises `CatalogDataError` with a useful location and reason. Validation happens before rendering, so existing HTML remains unchanged. A rendering error is different: some local pages may already be updated, but cleanup is not committed until all rendering succeeds.

**Why are there JSON tracking files?**  
They identify pages owned by the plugin and pages involved in an interrupted build. We can delete obsolete output without deleting unrelated files. They are internal bookkeeping, not the source data.

**Why does the code check paths and escape text?**  
A slug becomes a file path and URL, so it must have a restricted format. Text is escaped so data is displayed safely as text. Safe YAML loading avoids treating a data file as instructions to instantiate arbitrary Python objects.

**Is it a web application with a backend?**  
It is a static-site generator extension. Python runs during the build. Visitors receive static files. `nikola auto` is a local development server, not an upload/admin interface.

**How do you test it?**  
Unit tests check loading, validation, and output tracking. Integration tests invoke the real Nikola CLI and inspect generated files, links, changes, deletions, sitemap behavior, and automatic rebuilding. Run the commands in the README and report the result you actually obtained.

**What are the limitations?**  
One selected source, one collection, one language, and four fixed fields. There is no uploader, database, automatic internet publication, direct online spreadsheet connection, or rich-text description. These could be future work; do not present them as existing features.

## A short live demonstration

Use a local working copy. Make a backup of the selected data file first and restore it afterward. Do not run two independent builds in the same output directory.

1. Start `nikola auto --address 127.0.0.1 --port 8000` in the activated environment and open `/catalog/`.
2. Show `catalog_data/items.csv` and explain that every row is one entry.
3. Add this row at the end and save:

   ```csv
   demo001,interview-demo,Interview Demo,This page comes from one CSV row.
   ```

4. Show the new index card and open `/catalog/interview-demo/`.
5. Change the row's title to `Updated Interview Demo`, save, and show that both pages update.
6. Change the slug to `interview-demo-renamed`, save, and show the new page. The previous HTML page is removed.
7. Remove the row, save, and show that its card and page disappear.
8. Demonstrate validation by temporarily duplicating an existing row. Show the duplicate-ID error in the terminal and explain that the previous valid HTML is preserved. Remove the duplicate and save to recover.
9. Restore the original data and confirm the normal catalog is back.

If demonstrating YAML, stop the preview, select `catalog_data/items.yaml` using the README instructions, and restart it. Explain that only the selected source is used. Keep the terminal visible: it shows build and validation results.

## Prepare as a team

A useful division for studying and presenting the code is:

- **Data and validation:** explain `Item`, the two readers, validation, error messages, and loader tests.
- **Site generation and synchronization:** explain the Nikola task, templates, watched folders, cleanup, and integration tests.

Both teammates should still understand the complete flow and perform the demo themselves. This is a suggested presentation split, not a claim about who originally wrote each part. Describe your actual contributions honestly, including tool assistance when relevant or required. The strongest preparation is being able to make a small change and explain its effect.
