"""Read CSV or YAML, check every record, and return plain Item objects."""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


class CatalogDataError(ValueError):
    """A readable error in a catalog file or one of its records."""


@dataclass(frozen=True)
class Item:
    """The four fields shared by CSV, YAML, and the page templates."""

    id: str
    slug: str
    title: str
    description: str = ""

    def as_dict(self) -> dict[str, str]:
        """Give Nikola a normal dictionary to pass to the templates."""
        return asdict(self)


_REQUIRED_FIELDS = {"id", "slug", "title"}
_ALLOWED_FIELDS = _REQUIRED_FIELDS | {"description"}
_SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_INVALID_TEXT_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def load_items(path: str | Path) -> list[Item]:
    """Read the file, validate every item, then check IDs and slugs are unique.

    Return all items in file order or raise CatalogDataError; callers never get
    a partially validated list. HTML escaping belongs to the page templates.
    """
    source = Path(path)
    extension = source.suffix.lower()
    if extension not in {".csv", ".yaml", ".yml"}:
        raise _error(str(source), "expected a .csv, .yaml, or .yml source file")
    try:
        if extension == ".csv":
            records = _read_csv(source)
        else:
            records = _read_yaml(source)
    except (OSError, UnicodeError) as error:
        raise _error(str(source), f"cannot read catalog: {error}") from error

    items = []
    used_ids = {}
    used_slugs = {}
    for record in records:
        item = _validate_item(record, source)
        if item.id in used_ids:
            raise _error(record.location(source), f"duplicate id {item.id!r}; first used at {used_ids[item.id]}")
        if item.slug in used_slugs:
            raise _error(record.location(source), f"duplicate slug {item.slug!r}; first used at {used_slugs[item.slug]}")
        used_ids[item.id] = record.position
        used_slugs[item.slug] = record.position
        items.append(item)
    return items


@dataclass
class _Record:
    """Unvalidated data, plus source positions for helpful error messages."""

    data: Any
    position: str
    field_positions: dict[str, str] = field(default_factory=dict)

    def location(self, path: Path, field_name: str | None = None) -> str:
        position = self.field_positions.get(field_name, self.position)
        return f"{path}: {position}"


class _CatalogLoader(yaml.SafeLoader):
    """Keep safe YAML parsing, but reject repeated keys instead of losing data."""

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise yaml.constructor.ConstructorError(
                    None, None, "mapping keys must be strings", key_node.start_mark
                )
            if key in result:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate mapping key {key!r}", key_node.start_mark
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _error(location: str, message: str) -> CatalogDataError:
    return CatalogDataError(f"{location}: {message}")


def _validate_item(record: _Record, path: Path) -> Item:
    """Apply exactly the same field rules to both input formats."""
    raw = record.data
    location = record.location(path)
    if not isinstance(raw, dict):
        raise _error(location, "each item must be a mapping of field names to strings")
    missing = _REQUIRED_FIELDS - set(raw)
    unknown = set(raw) - _ALLOWED_FIELDS
    if missing:
        raise _error(location, f"missing required fields: {', '.join(sorted(missing))}")
    if unknown:
        raise _error(location, f"unexpected fields: {', '.join(sorted(unknown))}")

    values = {}
    for name in ("id", "slug", "title", "description"):
        value = raw.get(name, "")
        location = record.location(path, name)
        if not isinstance(value, str):
            raise _error(location, f"field {name!r} must be a string; quote numeric, boolean, or date values in YAML")
        invalid_character = _INVALID_TEXT_PATTERN.search(value)
        if invalid_character:
            codepoint = ord(invalid_character.group())
            raise _error(location, f"field {name!r} contains unsupported text character U+{codepoint:04X}")
        # Trim identifiers and titles; preserve intentional description whitespace.
        values[name] = value if name == "description" else value.strip()
        if name in _REQUIRED_FIELDS and not values[name]:
            raise _error(location, f"field {name!r} must not be empty")

    slug = values["slug"]
    if slug == "index":
        raise _error(record.location(path, "slug"), "slug 'index' is reserved")
    if not _SLUG_PATTERN.fullmatch(slug):
        raise _error(
            record.location(path, "slug"),
            "slug must contain lowercase ASCII letters or digits separated by single hyphens",
        )
    return Item(values["id"], values["slug"], values["title"], values["description"])


def _read_csv(path: Path) -> list[_Record]:
    records = []
    # utf-8-sig also accepts Excel's UTF-8 BOM; newline="" preserves quoted lines.
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        try:
            header = next(reader, None)
            location = f"{path}: CSV line 1"
            if header is None:
                raise _error(location, "missing header; expected id,slug,title[,description]")
            if len(set(header)) != len(header):
                raise _error(location, "duplicate column names in header")
            missing = _REQUIRED_FIELDS - set(header)
            unknown = set(header) - _ALLOWED_FIELDS
            if missing:
                raise _error(location, f"missing required columns: {', '.join(sorted(missing))}")
            if unknown:
                raise _error(location, f"unexpected columns: {', '.join(sorted(unknown))}")
            while True:
                first_line = reader.line_num + 1
                row = next(reader, None)
                if row is None:
                    break
                if not row:  # Empty lines are allowed between records.
                    continue
                position = f"CSV line {first_line}"
                if len(row) != len(header):
                    raise _error(f"{path}: {position}", f"expected {len(header)} fields, found {len(row)}")
                records.append(_Record(dict(zip(header, row)), position))
        except csv.Error as error:
            raise _error(f"{path}: CSV line {reader.line_num}", str(error)) from error
    return records


def _yaml_position(label: str, node) -> str:
    """YAML node marks count from zero; messages count from one."""
    mark = node.start_mark
    return f"{label} (line {mark.line + 1}, column {mark.column + 1})"


def _read_yaml(path: Path) -> list[_Record]:
    try:
        with path.open("r", encoding="utf-8-sig") as source:
            loader = _CatalogLoader(source)
            try:
                # Keep nodes for line numbers, and build ordinary Python data.
                node = loader.get_single_node()
                document = loader.construct_document(node) if node is not None else None
            finally:
                loader.dispose()
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        position = f"line {mark.line + 1}, column {mark.column + 1}" if mark else "document"
        problem = getattr(error, "problem", None) or str(error)
        raise _error(f"{path}: YAML {position}", problem) from error

    position = _yaml_position("YAML document", node) if node is not None else "YAML document"
    if not isinstance(document, dict) or set(document) != {"items"}:
        raise _error(f"{path}: {position}", "expected exactly one top-level field: items")
    # The schema guarantees one top-level key, so its value node is the items node.
    items_node = node.value[0][1]
    if not isinstance(document["items"], list):
        raise _error(f"{path}: {_yaml_position('YAML document', items_node)}", "items must be a list")

    records = []
    for number, (raw, item_node) in enumerate(zip(document["items"], items_node.value), start=1):
        label = f"YAML item {number}"
        record = _Record(raw, _yaml_position(label, item_node))
        if isinstance(item_node, yaml.MappingNode):
            for key_node, value_node in item_node.value:
                record.field_positions[key_node.value] = _yaml_position(label, value_node)
        records.append(record)
    return records

