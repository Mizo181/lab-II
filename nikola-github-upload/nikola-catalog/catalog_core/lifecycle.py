"""Track generated pages so deleted records do not leave old HTML behind.

The manifest lists pages from the last successful build. The pending journal
also records pages a running build may create. Keeping both lets the next build
remove unfinished output without touching files that belong to someone else.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import re
import tempfile


class CatalogOutputError(ValueError):
    """The output directory cannot safely be used by the catalog plugin."""


_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_PAGE = re.compile(r"(?:index\.html|[a-z0-9]+(?:-[a-z0-9]+)*/index\.html)\Z")
_VERSION = 1


class CatalogOutput:
    """Manage one catalog with three steps: validate, prepare, then finalize.

    Validate while collecting tasks, prepare before rendering any page, and
    finalize only after every page has rendered successfully. A failed render
    leaves the manifest and journal available for the next build.
    """

    MANIFEST_NAME = ".catalog-manifest.json"
    PENDING_NAME = ".catalog-pending.json"

    def __init__(self, output_folder: str | Path, catalog_path: str) -> None:
        if not isinstance(catalog_path, str) or not _SLUG.fullmatch(catalog_path):
            raise CatalogOutputError("Catalog output path must be one safe lowercase slug.")
        self.output_folder = Path(output_folder).absolute()
        self.root = self.output_folder / catalog_path
        self.manifest = self.root / self.MANIFEST_NAME
        self.pending = self.root / self.PENDING_NAME

    def validate(self, desired: list[str]) -> None:
        """Check the requested pages and existing output without changing files."""
        try:
            self._check_output(desired)
        except OSError as exc:
            raise CatalogOutputError(f"Cannot inspect catalog output {self.root}: {exc}") from exc

    def prepare(self, desired: list[str]) -> bool:
        """Record ownership before renderers create or update any page."""
        try:
            desired_pages, owned_pages = self._check_output(desired)
            self.root.mkdir(parents=True, exist_ok=True)
            # Include earlier unfinished builds, not just the current pages.
            self._write_state(self.pending, owned_pages | desired_pages)
        except OSError as exc:
            raise CatalogOutputError(f"Cannot prepare catalog output {self.root}: {exc}") from exc
        return True

    def finalize(self, desired: list[str]) -> bool:
        """After successful rendering, delete stale pages and save the manifest."""
        try:
            desired_pages, owned_pages = self._check_output(desired)

            # Check everything before deleting anything. A failed render must
            # leave the previous pages and the recovery journal in place.
            for relative in sorted(desired_pages):
                if not self._page_path(relative).is_file():
                    raise CatalogOutputError(f"Expected rendered catalog page is missing: {self.root / relative}")

            for relative in sorted(owned_pages - desired_pages):
                page = self._page_path(relative)
                if page.exists():
                    page.unlink()
                if page.parent != self.root and page.parent.exists():
                    try:
                        page.parent.rmdir()
                    except OSError as exc:
                        # An unrelated file in the same folder must survive.
                        if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                            raise

            self.root.mkdir(parents=True, exist_ok=True)
            self._write_state(self.manifest, desired_pages)
            self.pending.unlink(missing_ok=True)
        except OSError as exc:
            raise CatalogOutputError(f"Cannot finalize catalog output {self.root}: {exc}") from exc
        return True

    def _check_output(self, desired: list[str]) -> tuple[set[str], set[str]]:
        """Return desired and owned paths after checking every affected file."""
        desired_pages = self._validate_page_paths(desired, "Desired catalog pages")
        self._check_directory(self.output_folder)
        self._check_directory(self.root)
        owned_pages = self._read_state(self.manifest) | self._read_state(self.pending)

        for relative in sorted(owned_pages | desired_pages):
            page = self._page_path(relative)
            if relative in desired_pages and relative not in owned_pages and page.exists():
                raise CatalogOutputError(
                    f"Refusing to overwrite untracked catalog page {page}. "
                    "Choose a fresh output directory, or explicitly move the existing file away."
                )
        return desired_pages, owned_pages

    @staticmethod
    def _validate_page_paths(paths: list[str], label: str) -> set[str]:
        if not isinstance(paths, list):
            raise CatalogOutputError(f"{label}: paths must be a list.")
        checked: set[str] = set()
        for path in paths:
            if not isinstance(path, str) or not _PAGE.fullmatch(path):
                raise CatalogOutputError(
                    f"{label}: unsafe page path {path!r}; expected index.html or <slug>/index.html."
                )
            if path in checked:
                raise CatalogOutputError(f"{label}: duplicate page path {path!r}.")
            checked.add(path)
        return checked

    @staticmethod
    def _check_directory(path: Path) -> None:
        if path.is_symlink():
            raise CatalogOutputError(f"Refusing symbolic link in catalog output: {path}")
        if path.exists() and not path.is_dir():
            raise CatalogOutputError(f"Expected a directory for catalog output: {path}")

    def _page_path(self, relative: str) -> Path:
        """Return a page path, rejecting symlinks and conflicting file types."""
        path = self.root / relative
        if path.parent != self.root:
            self._check_directory(path.parent)
        if path.is_symlink():
            raise CatalogOutputError(f"Refusing symbolic link for a generated page: {path}")
        if path.exists() and not path.is_file():
            raise CatalogOutputError(f"Expected a regular generated page file: {path}")
        return path

    def _read_state(self, path: Path) -> set[str]:
        """Read a manifest or journal; invalid ownership data stops the build."""
        if path.is_symlink():
            raise CatalogOutputError(f"Refusing symbolic link for catalog state: {path}")
        if not path.exists():
            return set()
        if not path.is_file():
            raise CatalogOutputError(f"Catalog state must be a regular file: {path}")
        try:
            state = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=self._reject_duplicate_keys)
        except (OSError, UnicodeError, ValueError) as exc:
            raise CatalogOutputError(
                f"Cannot read catalog state {path}: {exc}. Use a fresh output directory to recover safely."
            ) from exc
        if (
            not isinstance(state, dict)
            or set(state) != {"version", "paths"}
            or type(state["version"]) is not int
            or state["version"] != _VERSION
        ):
            raise CatalogOutputError(
                f"Invalid catalog state schema in {path}; use a fresh output directory to recover safely."
            )
        return self._validate_page_paths(state["paths"], str(path))

    @staticmethod
    def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        # JSON normally accepts repeated keys. Ownership files must be unambiguous.
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate metadata key {key!r}")
            result[key] = value
        return result

    @staticmethod
    def _write_state(path: Path, paths: set[str]) -> None:
        """Replace state atomically; unchanged content keeps its modification time."""
        content = json.dumps({"version": _VERSION, "paths": sorted(paths)}, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix=f"{path.name}.", suffix=".tmp", dir=path.parent,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
