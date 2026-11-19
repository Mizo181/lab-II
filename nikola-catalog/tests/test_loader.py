"""Input contracts tested independently from Nikola rendering and lifecycle."""

import json
from dataclasses import FrozenInstanceError

import pytest

from catalog_core import CatalogDataError, Item, load_items


def source(tmp_path, contents, suffix=".yaml"):
    path = tmp_path / f"catalog{suffix}"
    path.write_text(contents, encoding="utf-8")
    return path


def test_csv_and_yaml_produce_same_normalized_records(tmp_path):
    csv = source(
        tmp_path,
        "id,slug,title,description\n p1 ,robotics-club, Клуб робототехники ,  Текст  \np2,chess,Chess,\n",
        ".csv",
    )
    yaml = source(
        tmp_path,
        'items:\n  - id: " p1 "\n    slug: robotics-club\n    title: " Клуб робототехники "\n'
        '    description: "  Текст  "\n  - id: p2\n    slug: chess\n    title: Chess\n',
    )
    expected = [Item("p1", "robotics-club", "Клуб робототехники", "  Текст  "), Item("p2", "chess", "Chess")]
    assert load_items(csv) == load_items(yaml) == expected


def test_csv_bom_quotes_newlines_and_field_order(tmp_path):
    path = source(
        tmp_path,
        '\ufefftitle,id,description,slug\r\n"A, B",one,"First line\r\nSecond line",one\r\n',
        ".csv",
    )
    assert load_items(path) == [Item("one", "one", "A, B", "First line\r\nSecond line")]


@pytest.mark.parametrize("contents,suffix", [("id,slug,title\n", ".csv"), ("items: []\n", ".yaml")])
def test_explicit_empty_catalog_is_valid(tmp_path, contents, suffix):
    assert load_items(source(tmp_path, contents, suffix)) == []


def test_csv_empty_lines_are_allowed(tmp_path):
    assert load_items(source(tmp_path, "id,slug,title\n\np1,one,One\n\n", ".csv")) == [Item("p1", "one", "One")]


@pytest.mark.parametrize(
    "contents,match",
    [
        ("", "missing header"),
        ("id,slug\np1,one\n", "missing required columns: title"),
        ("id,slug,title,title\np1,one,One,One\n", "duplicate column"),
        ("id,slug,title,price\np1,one,One,5\n", "unexpected columns: price"),
        ("id,slug,title\np1,one\n", "expected 3 fields, found 2"),
        ("id,slug,title\np1,one,One,extra\n", "expected 3 fields, found 4"),
        ('id,slug,title\np1,one,"Unclosed\n', "CSV line"),
    ],
)
def test_invalid_csv_schema(tmp_path, contents, match):
    path = source(tmp_path, contents, ".csv")
    with pytest.raises(CatalogDataError, match=match) as error:
        load_items(path)
    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    "contents,match",
    [
        ("", "top-level field"),
        ("[]", "top-level field"),
        ("items: []\nextra: value", "top-level field"),
        ("items: null", "items must be a list"),
        ("items: {}", "items must be a list"),
        ("items: [string]", "each item must be a mapping"),
        ("items: [{id: p1, slug: one}]", "missing required fields: title"),
        ("items: [{id: p1, slug: one, title: One, price: 2}]", "unexpected fields: price"),
        ("items: []\nitems: []", "duplicate mapping key 'items'"),
        ("items: [{id: p1, slug: one, title: One, title: Two}]", "duplicate mapping key 'title'"),
        ("items: [{id: p1, slug: one, title: One, 1: value}]", "mapping keys must be strings"),
        ("items: [", "YAML line"),
        ("items: !!python/object:builtins.object {}", "could not determine a constructor"),
    ],
)
def test_invalid_yaml_schema_and_unsafe_tags(tmp_path, contents, match):
    path = source(tmp_path, contents)
    with pytest.raises(CatalogDataError, match=match) as error:
        load_items(path)
    assert str(path) in str(error.value)


@pytest.mark.parametrize("field", ["id", "slug", "title", "description"])
@pytest.mark.parametrize("value", ["42", "true", "2026-11-12", "null", "[]", "{}"])
def test_yaml_fields_must_be_strings(tmp_path, field, value):
    fields = {"id": "p1", "slug": "one", "title": "One", "description": "Description"}
    fields[field] = value
    path = source(tmp_path, "items:\n  - " + "\n    ".join(f"{key}: {val}" for key, val in fields.items()))
    with pytest.raises(CatalogDataError, match=f"field '{field}' must be a string") as error:
        load_items(path)
    assert "YAML item 1 (line" in str(error.value)


@pytest.mark.parametrize("field", ["id", "slug", "title"])
def test_required_values_cannot_be_whitespace(tmp_path, field):
    fields = {"id": "p1", "slug": "one", "title": "One"}
    fields[field] = '"  "'
    path = source(tmp_path, "items:\n  - " + "\n    ".join(f"{key}: {val}" for key, val in fields.items()))
    with pytest.raises(CatalogDataError, match=f"field '{field}' must not be empty"):
        load_items(path)


@pytest.mark.parametrize("slug", ["index", "../outside", "/outside", "two/parts", "A", "two--parts", "-one", "one-", "кириллица", "a.b", "a_b", "a\\b"])
def test_slug_is_safe_for_a_dedicated_directory(tmp_path, slug):
    path = source(tmp_path, f'id,slug,title\np1,{slug},One\n', ".csv")
    with pytest.raises(CatalogDataError, match="slug"):
        load_items(path)


@pytest.mark.parametrize("contents,match", [
    ("id,slug,title\n p1 ,one,One\np1,two,Two\n", "duplicate id 'p1'"),
    ("id,slug,title\np1,one,One\np2, one ,Two\n", "duplicate slug 'one'"),
])
def test_duplicates_checked_after_normalization_with_both_positions(tmp_path, contents, match):
    with pytest.raises(CatalogDataError, match=match) as error:
        load_items(source(tmp_path, contents, ".csv"))
    assert "CSV line 3" in str(error.value)
    assert "first used at CSV line 2" in str(error.value)


def test_yaml_duplicate_ids_identify_second_record(tmp_path):
    path = source(tmp_path, "items:\n  - {id: one, slug: one, title: One}\n  - {id: one, slug: two, title: Two}\n")
    with pytest.raises(CatalogDataError, match="YAML item 2.*duplicate id"):
        load_items(path)


def test_description_is_plain_text_and_item_is_immutable_and_serializable(tmp_path):
    malicious_text = '<script>alert("x")</script> & text'
    path = source(tmp_path, "items:\n  - id: one\n    slug: one\n    title: '<b>Title</b>'\n    description: '<script>alert(\"x\")</script> & text'\n")
    item = load_items(path)[0]
    assert item.title == "<b>Title</b>"
    assert item.description == malicious_text
    assert json.loads(json.dumps(item.as_dict())) == {
        "id": "one", "slug": "one", "title": "<b>Title</b>", "description": malicious_text,
    }
    with pytest.raises(FrozenInstanceError):
        item.title = "Other"


def test_recursion_cannot_escape_schema_validation(tmp_path):
    path = source(tmp_path, "items: &items [*items]")
    with pytest.raises(CatalogDataError):
        load_items(path)


def test_file_errors_have_source_path(tmp_path):
    missing = tmp_path / "missing.csv"
    with pytest.raises(CatalogDataError, match="cannot read catalog") as error:
        load_items(missing)
    assert str(missing) in str(error.value)
    with pytest.raises(CatalogDataError, match="expected a .csv"):
        load_items(tmp_path / "catalog.json")


def test_invalid_utf8_is_friendly(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"id,slug,title\np1,one,\xff\n")
    with pytest.raises(CatalogDataError, match="cannot read catalog"):
        load_items(path)


@pytest.mark.parametrize("character", ["\x00", "\x08", "\x0b", "\x0c", "\x1f", "\ufffe", "\uffff"])
def test_csv_rejects_characters_that_cannot_be_rendered_as_html(tmp_path, character):
    path = source(tmp_path, f"id,slug,title,description\np1,one,One,Text{character}here\n", ".csv")
    with pytest.raises(CatalogDataError, match="description.*unsupported text character"):
        load_items(path)


@pytest.mark.parametrize("escaped", [r"\0", r"\x0b", r"\uD800", r"\uFFFF"])
def test_yaml_escaped_invalid_characters_are_rejected_before_rendering(tmp_path, escaped):
    path = source(tmp_path, f'items:\n  - {{id: p1, slug: one, title: "Text{escaped}"}}\n')
    with pytest.raises(CatalogDataError, match="title.*unsupported text character"):
        load_items(path)
