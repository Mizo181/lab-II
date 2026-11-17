import re
from pathlib import Path

from nikola.plugin_categories import Task

from catalog_core.loader import load_items
from catalog_core.lifecycle import CatalogOutput


class RenderCatalog(Task):
    """Build an index and one page per CSV/YAML record."""

    name = "render_catalog"

    def set_site(self, site):
        """Tell Nikola which folders to watch and when to scan the sitemap."""
        super().set_site(site)
        source = Path(site.config.get("CATALOG_SOURCE", "catalog_data/items.csv"))
        self.register_auto_watched_folder(str(source.parent.resolve()))
        self.register_auto_watched_folder(str(Path("catalog_core").resolve()))
        # Sitemap discovery must wait until old catalog pages have been removed.
        self.inject_dependency("_scan_locs", self.name)

    def gen_tasks(self):
        """Describe the build. Nikola runs these actions only when needed."""
        config = self.site.config
        self._check_configuration()
        source = Path(config.get("CATALOG_SOURCE", "catalog_data/items.csv"))
        catalog_path = config.get("CATALOG_PATH", "catalog")

        # 1. Read and validate every record before changing any HTML.
        items = load_items(source)
        records = []
        page_files = ["index.html"]
        for item in items:
            record = item.as_dict()
            record["url"] = f"/{catalog_path}/{item.slug}/"
            records.append(record)
            page_files.append(f"{item.slug}/index.html")

        output = CatalogOutput(config["OUTPUT_FOLDER"], catalog_path)
        output.validate(page_files)

        # 2. Start with Nikola's index-page task. Its context contains every
        # record, so its change check also covers all entry titles/descriptions.
        shared = self._shared_context(len(records))
        index_context = shared.copy()
        index_context.update({
            "title": shared["catalog_title"],
            "description": shared["catalog_description"],
            "permalink": shared["catalog_index_url"],
            "items": records,
        })
        task = self._render_task("index.html", "catalog_index.tmpl", index_context, source)
        task["basename"] = self.name
        task["name"] = "pages"

        # 3. Add each entry's render actions, output file, and template dependencies
        # to the SAME task. A small catalog does not need a separate task per page.
        for record in records:
            context = shared.copy()
            context.update({
                "title": record["title"],
                "description": record["description"],
                "permalink": record["url"],
                "item": record,
            })
            page = self._render_task(
                f"{record['slug']}/index.html", "catalog_item.tmpl", context, source
            )
            task["actions"].extend(page["actions"])
            task["targets"].extend(page["targets"])
            task["file_dep"].extend(page["file_dep"])
        task["file_dep"] = sorted(set(task["file_dep"]))

        # 4. Record ownership first; remove stale pages only after ALL render
        # actions succeed. If an action fails, doit stops before finalize.
        task["actions"].insert(0, (output.prepare, [page_files]))
        task["actions"].append((output.finalize, [page_files]))
        # Finish an interrupted build even if the input files have not changed.
        task["uptodate"].append(not output.pending.exists())

        # yield hands instructions to Nikola; it does not render pages here.
        yield self.group_task()
        yield task

    def _render_task(self, relative_path, template, context, source):
        """Ask Nikola for the actions and dependencies for one themed page."""
        config = self.site.config
        target = Path(config["OUTPUT_FOLDER"]) / config.get("CATALOG_PATH", "catalog") / relative_path
        dependencies = [str(source), str(Path(__file__).resolve())]
        for module in sorted(Path("catalog_core").glob("*.py")):
            dependencies.append(str(module))
        return self.site.generic_renderer(
            config["DEFAULT_LANG"], str(target), template, config["FILTERS"],
            file_deps=dependencies, context=context,
        )

    def _shared_context(self, count):
        """Values used by both the index and entry templates."""
        config = self.site.config
        return {
            "catalog_title": config.get("CATALOG_TITLE", "Collection"),
            "catalog_description": config.get("CATALOG_DESCRIPTION", ""),
            "catalog_index_url": f"/{config.get('CATALOG_PATH', 'catalog')}/",
            "catalog_count": count,
            "pagekind": ["catalog"],
            "enable_comments": False,
        }

    def _check_configuration(self):
        """Keep the small project's supported settings explicit."""
        config = self.site.config
        path = config.get("CATALOG_PATH", "catalog")
        if not isinstance(path, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", path):
            raise ValueError("CATALOG_PATH must be one URL segment, e.g. 'catalog'.")
        if len(config["TRANSLATIONS"]) != 1:
            raise ValueError("The catalog supports one language per site.")
        if config["INDEX_FILE"] != "index.html":
            raise ValueError("The catalog requires INDEX_FILE = 'index.html'.")
