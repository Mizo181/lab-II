# -*- coding: utf-8 -*-

"""Generate one page per entry in YAML/CSV data files, plus an index page.

Drop data files into the lists/ folder of a site (configurable via
DATA_PAGES_FOLDER). Each file becomes a collection named after the file:
lists/people.yaml -> output/people/index.html + one page per entry at
output/people/<slug>/index.html. Entries are dicts (YAML list of maps or
CSV rows); 'slug'/'title'/'name' fields are used to build URLs and titles.
"""

import csv
import io
import os

from nikola.plugin_categories import Task
from nikola import utils


class DataPages(Task):
    """Render one page per entry found in data files."""

    name = "render_datapages"

    def set_site(self, site):
        """Store the config values we need, then attach to the site."""
        self.kw = {
            "lists_folder": site.config.get("DATA_PAGES_FOLDER", "lists"),
            "output_folder": site.config["OUTPUT_FOLDER"],
            "index_file": site.config["INDEX_FILE"],
            "pretty_urls": site.config["PRETTY_URLS"],
            "default_lang": site.config["DEFAULT_LANG"],
            "filters": site.config["FILTERS"],
        }
        return super().set_site(site)

    def gen_tasks(self):
        """Yield a doit task per entry page, plus one index per data file."""
        yield self.group_task()
        folder = self.kw["lists_folder"]
        if not os.path.isdir(folder):
            return
        for fname in sorted(os.listdir(folder)):
            path = os.path.join(folder, fname)
            entries = self._load_entries(path)
            if entries:
                collection = os.path.splitext(fname)[0]
                yield from self._collection_tasks(path, collection, entries)

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _load_entries(path):
        """Return a list of dicts (one per entry) from a data file."""
        if path.lower().endswith(".csv"):
            with io.open(path, newline="", encoding="utf-8-sig") as f:
                return [dict(row) for row in csv.DictReader(f)]
        data = utils.load_data(path)  # handles .yaml/.yml/.json/.toml
        if isinstance(data, dict):    # allow YAML like {entries: [...]}
            data = data.get("entries")
        return data if isinstance(data, list) else []

    def _collection_tasks(self, data_file, collection, entries):
        """Build the tasks for one data file: entry pages + index page."""
        index_entries = []
        for i, entry in enumerate(entries):
            slug = self._entry_slug(entry, i)
            index_entries.append((self._entry_link(slug), entry))
            yield self._page_task("datapage.tmpl", collection, slug, data_file, {
                "collection": collection,
                "entry": entry,
                "title": self._entry_title(entry, slug),
                "pagekind": ["datapage"],
            })
        yield self._page_task("datapages_index.tmpl", collection, None, data_file, {
            "collection": collection,
            "entries": index_entries,
            "title": collection.replace("-", " ").replace("_", " ").title(),
            "pagekind": ["datapages_index"],
        })

    def _page_task(self, template, collection, slug, data_file, context):
        """Build one doit task dict that renders `template` to one page."""
        parts = [self.kw["output_folder"], collection]
        if slug is None:
            parts.append(self.kw["index_file"])
        elif self.kw["pretty_urls"]:
            parts += [slug, self.kw["index_file"]]
        else:
            parts.append(slug + ".html")
        out_name = os.path.join(*parts)
        context["lang"] = self.kw["default_lang"]
        context["permalink"] = self._permalink(out_name)
        template_deps = self.site.template_system.template_deps(
            template, self.site.GLOBAL_CONTEXT)
        return utils.apply_filters({
            "basename": self.name,
            "name": out_name,
            "file_dep": [data_file] + template_deps,
            "targets": [out_name],
            "actions": [(self.render, [template, out_name, context])],
            "uptodate": [utils.config_changed(
                {"context": context, "kw": self.kw},
                "nikola.plugins.task.datapages:" + out_name)],
            "clean": True,
        }, self.kw["filters"])

    def render(self, template_name, out_name, context):
        """Render one page. Runs when doit decides the task is out of date."""
        self.site.render_template(template_name, out_name, context)

    # --- naming ----------------------------------------------------------

    def _entry_slug(self, entry, i):
        """URL slug for an entry: explicit slug, else title/name, else number."""
        raw = entry.get("slug") or entry.get("title") or entry.get("name") or str(i)
        return utils.slugify(str(raw), self.kw["default_lang"])

    @staticmethod
    def _entry_title(entry, slug):
        """Human-readable title for an entry."""
        return str(entry.get("title") or entry.get("name") or slug)

    def _entry_link(self, slug):
        """Link from the index page to one entry page (relative)."""
        return slug + "/" if self.kw["pretty_urls"] else slug + ".html"

    def _permalink(self, out_name):
        """Site-relative URL of an output file."""
        rel = os.path.relpath(out_name, self.kw["output_folder"])
        rel = rel.replace(os.sep, "/")
        if rel.endswith(self.kw["index_file"]):
            rel = rel[:-len(self.kw["index_file"])]
        return "/" + rel
