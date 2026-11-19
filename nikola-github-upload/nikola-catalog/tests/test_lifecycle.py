"""Ownership, failure recovery and cleanup tests for catalog output."""

import json

import pytest

from catalog_core.lifecycle import CatalogOutput, CatalogOutputError


@pytest.fixture
def output(tmp_path):
    return CatalogOutput(tmp_path / "output", "catalog")


def render(output, pages):
    for relative in pages:
        path = output.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<html>{relative}</html>", encoding="utf-8")


def build(output, pages):
    output.validate(pages)
    assert output.prepare(pages) is True
    render(output, pages)
    assert output.finalize(pages) is True


def test_validate_does_not_create_output(output):
    output.validate(["index.html", "chess-club/index.html"])
    assert not output.output_folder.exists()


def test_first_build_commits_manifest_and_removes_journal(output):
    pages = ["index.html", "chess-club/index.html"]
    build(output, pages)
    assert json.loads(output.manifest.read_text()) == {"version": 1, "paths": sorted(pages)}
    assert not output.pending.exists()


def test_rename_delete_and_empty_catalog_remove_stale_pages(output):
    build(output, ["index.html", "old-name/index.html", "deleted/index.html"])
    build(output, ["index.html", "new-name/index.html"])
    assert not (output.root / "old-name").exists()
    assert not (output.root / "deleted").exists()
    assert (output.root / "new-name/index.html").is_file()
    build(output, ["index.html"])
    assert not (output.root / "new-name").exists()
    assert (output.root / "index.html").is_file()


def test_pending_journal_recovers_partial_failed_build(output):
    initial = ["index.html", "original/index.html"]
    build(output, initial)
    output.prepare(["index.html", "partially-written/index.html", "never-written/index.html"])
    render(output, ["partially-written/index.html"])
    # No finalize: a renderer failed. The original successful state survives.
    assert json.loads(output.manifest.read_text())["paths"] == sorted(initial)
    restarted = CatalogOutput(output.output_folder, "catalog")
    build(restarted, ["index.html", "replacement/index.html"])
    assert not (output.root / "partially-written").exists()
    assert not (output.root / "original").exists()
    assert (output.root / "replacement/index.html").exists()
    assert not output.pending.exists()


def test_prepare_preserves_prior_pending_paths(output):
    output.prepare(["index.html", "first/index.html"])
    render(output, ["first/index.html"])
    output.prepare(["index.html", "second/index.html"])
    assert json.loads(output.pending.read_text())["paths"] == [
        "first/index.html", "index.html", "second/index.html"
    ]


def test_unrelated_files_and_nonempty_slug_directories_survive(output):
    build(output, ["index.html", "old/index.html"])
    unrelated = output.root / "old/notes.txt"
    unrelated.write_text("keep me")
    nested = output.root / "unrelated/subdir/file.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("also keep me")
    outside = output.output_folder / "another-page.html"
    outside.write_text("neighbor")
    build(output, ["index.html"])
    assert not (output.root / "old/index.html").exists()
    assert unrelated.read_text() == "keep me"
    assert nested.read_text() == "also keep me"
    assert outside.read_text() == "neighbor"


@pytest.mark.parametrize("relative", ["index.html", "other/index.html"])
def test_untracked_desired_file_is_never_overwritten(output, relative):
    render(output, [relative])
    before = (output.root / relative).read_bytes()
    with pytest.raises(CatalogOutputError, match="untracked.*fresh output"):
        output.prepare([relative])
    assert (output.root / relative).read_bytes() == before
    assert not output.pending.exists()


def test_missing_tracked_files_after_clean_rebuild_normally(output):
    pages = ["index.html", "club/index.html"]
    build(output, pages)
    for relative in pages:
        (output.root / relative).unlink()
    build(output, pages)
    assert all((output.root / relative).is_file() for relative in pages)


def test_success_manifest_mtime_does_not_change_on_noop(output):
    pages = ["index.html", "club/index.html"]
    build(output, pages)
    before = output.manifest.stat().st_mtime_ns
    output.prepare(pages)
    output.finalize(pages)
    assert output.manifest.stat().st_mtime_ns == before


def test_missing_render_blocks_cleanup_and_keeps_journal(output):
    build(output, ["index.html", "old/index.html"])
    pages = ["index.html", "missing/index.html"]
    output.prepare(pages)
    with pytest.raises(CatalogOutputError, match="rendered catalog page is missing"):
        output.finalize(pages)
    assert (output.root / "old/index.html").exists()
    assert output.pending.exists()


@pytest.mark.parametrize("name", [CatalogOutput.MANIFEST_NAME, CatalogOutput.PENDING_NAME])
@pytest.mark.parametrize("state", [
    "not json",
    '{"version": 1, "version": 1, "paths": []}',
    '{"version": true, "paths": []}',
    '{"version": 2, "paths": []}',
    '{"version": 1, "paths": [], "unexpected": true}',
    '{"version": 1, "paths": "index.html"}',
    '{"version": 1, "paths": ["index.html", "index.html"]}',
    '{"version": 1, "paths": ["../outside.html"]}',
    '{"version": 1, "paths": ["/outside/index.html"]}',
    '{"version": 1, "paths": ["club\\\\index.html"]}',
    '{"version": 1, "paths": ["club/nested/index.html"]}',
    '{"version": 1, "paths": [null]}',
])
def test_invalid_metadata_blocks_all_cleanup(output, name, state):
    build(output, ["index.html", "old/index.html"])
    (output.root / name).write_text(state)
    with pytest.raises(CatalogOutputError):
        output.finalize(["index.html"])
    assert (output.root / "old/index.html").exists()


@pytest.mark.parametrize("path", ["../index.html", "club/../index.html", "/index.html", "club\\index.html"])
def test_invalid_desired_path_does_not_create_output(output, path):
    with pytest.raises(CatalogOutputError, match="unsafe page path"):
        output.prepare([path])
    assert not output.output_folder.exists()


@pytest.mark.parametrize("part", ["output", "namespace", "subdirectory", "page", "manifest", "pending"])
@pytest.mark.parametrize("dangling", [False, True])
def test_symlinks_block_operations_without_touching_external_files(tmp_path, part, dangling):
    output = CatalogOutput(tmp_path / "output", "catalog")
    external = tmp_path / "external"
    external.mkdir()
    external_page = external / "index.html"
    external_page.write_text("external page")
    target = external / "missing" if dangling else external
    pages = ["index.html", "club/index.html"]
    if part == "output":
        output.output_folder.symlink_to(target, target_is_directory=True)
    elif part == "namespace":
        output.output_folder.mkdir()
        output.root.symlink_to(target, target_is_directory=True)
    else:
        build(output, pages)
        if part == "subdirectory":
            (output.root / "club/index.html").unlink()
            (output.root / "club").rmdir()
            (output.root / "club").symlink_to(target, target_is_directory=True)
        else:
            if part == "page":
                link = output.root / "club/index.html"
            elif part == "manifest":
                link = output.manifest
            else:
                link = output.pending
            link.unlink(missing_ok=True)
            link.symlink_to(external / "missing" if dangling else external_page)
    with pytest.raises(CatalogOutputError, match="symbolic link"):
        output.prepare(pages)
    assert external_page.read_text() == "external page"


def test_stale_symlink_is_detected_before_any_other_page_is_deleted(output, tmp_path):
    build(output, ["index.html", "a-first/index.html", "z-last/index.html"])
    external = tmp_path / "external.html"
    external.write_text("outside")
    stale = output.root / "z-last/index.html"
    stale.unlink()
    stale.symlink_to(external)
    with pytest.raises(CatalogOutputError, match="symbolic link"):
        output.finalize(["index.html"])
    assert (output.root / "a-first/index.html").exists()
    assert external.read_text() == "outside"


def test_namespace_and_state_cannot_be_regular_directory_or_file_swaps(output):
    output.output_folder.mkdir()
    output.root.write_text("not a directory")
    with pytest.raises(CatalogOutputError, match="Expected a directory"):
        output.validate(["index.html"])
    output.root.unlink()
    output.root.mkdir()
    output.manifest.mkdir()
    with pytest.raises(CatalogOutputError, match="regular file"):
        output.validate(["index.html"])
