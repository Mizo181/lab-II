"""Exercise the actual Nikola command, dependency graph and generated HTML."""

import csv
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urljoin, urlsplit

from lxml import html
import pytest
import yaml


PROJECT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.integration


@pytest.fixture
def site(tmp_path):
    for name in ("catalog_core", "plugins", "templates", "files", "catalog_data"):
        shutil.copytree(PROJECT / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(PROJECT / "conf.py", tmp_path / "conf.py")
    return tmp_path


def cli(site, *args, source="catalog_data/items.csv", site_url="https://example.test/", ok=True):
    env = dict(os.environ, CATALOG_SOURCE=source, NIKOLA_SITE_URL=site_url)
    result = subprocess.run(
        [sys.executable, "-m", "nikola", *args], cwd=site, env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45,
    )
    if ok:
        assert result.returncode == 0, result.stdout
    else:
        assert result.returncode != 0, result.stdout
    return result


def write_csv(site, records):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=["id", "slug", "title", "description"])
    writer.writeheader()
    writer.writerows(records)
    (site / "catalog_data/items.csv").write_text(text.getvalue(), encoding="utf-8")


def record(slug="one", title="First project", description="A description"):
    return {"id": slug, "slug": slug, "title": title, "description": description}


def page(site, relative="index.html"):
    return site / "output/catalog" / relative


def assert_local_links(site, document, public_url):
    tree = html.parse(str(document))
    for value in tree.xpath("//a/@href | //link[@rel='stylesheet']/@href | //script[@src]/@src"):
        resolved = urlsplit(urljoin(public_url, value))
        if resolved.netloc != "example.test":
            continue
        assert resolved.path.startswith("/school/"), value
        target = site / "output" / resolved.path.removeprefix("/school/")
        if resolved.path.endswith("/"):
            target /= "index.html"
        assert target.is_file(), (value, target)


def test_csv_build_noop_links_and_yaml_equivalence(site):
    cli(site, "build")
    index = html.parse(str(page(site)))
    cards = index.xpath("//a[contains(@href, 'robotics')]")
    assert cards
    pages = sorted((site / "output/catalog").rglob("*.html"))
    assert len(pages) == 7
    before = {str(p): (p.stat().st_mtime_ns, p.read_bytes()) for p in pages}
    cli(site, "build")
    assert before == {str(p): (p.stat().st_mtime_ns, p.read_bytes()) for p in pages}
    cli(site, "check", "-l")
    csv_html = {str(p.relative_to(page(site).parent)): p.read_bytes() for p in pages}
    cli(site, "build", source="catalog_data/items.yaml")
    assert csv_html == {str(p.relative_to(page(site).parent)): p.read_bytes() for p in pages}


def test_updates_additions_renames_deletions_empty_and_neighbors(site):
    write_csv(site, [record()])
    cli(site, "build")
    neighbor = site / "output/keep.txt"
    neighbor.write_text("unrelated", encoding="utf-8")
    inside_neighbor = page(site, "readme.txt")
    inside_neighbor.write_text("also unrelated", encoding="utf-8")
    write_csv(site, [record(title="Updated title"), record("two", "Second project")])
    cli(site, "build")
    assert "Updated title" in page(site, "one/index.html").read_text()
    assert page(site, "two/index.html").is_file()
    write_csv(site, [record("renamed", "Updated title")])
    cli(site, "build")
    assert not page(site, "one/index.html").exists()
    assert not page(site, "two/index.html").exists()
    assert page(site, "renamed/index.html").is_file()
    write_csv(site, [])
    cli(site, "build")
    assert not page(site, "renamed/index.html").exists()
    assert page(site).is_file()
    assert neighbor.read_text() == "unrelated"
    assert inside_neighbor.read_text() == "also unrelated"


def test_invalid_data_preserves_previous_html(site):
    cli(site, "build")
    before = {p: p.read_bytes() for p in (site / "output").rglob("*.html")}
    write_csv(site, [record(), record()])
    result = cli(site, "build", ok=False)
    assert "duplicate" in result.stdout.lower()
    assert before == {p: p.read_bytes() for p in before}
    assert not page(site, ".catalog-pending.json").exists()


def test_template_changes_trigger_render_and_failure_does_not_cleanup(site):
    write_csv(site, [record("old")])
    cli(site, "build")
    template = site / "templates/catalog_item.tmpl"
    original = template.read_text()
    write_csv(site, [record("new")])
    template.write_text(original.replace("{% block content %}", "{% block content %}{{ 1 / 0 }}"), encoding="utf-8")
    cli(site, "build", ok=False)
    assert page(site, "old/index.html").is_file()
    assert page(site, ".catalog-pending.json").is_file()
    template.write_text(original.replace("{% block content %}", "{% block content %}<p>Template updated</p>"), encoding="utf-8")
    cli(site, "build")
    assert not page(site, "old/index.html").exists()
    assert "Template updated" in page(site, "new/index.html").read_text()
    assert not page(site, ".catalog-pending.json").exists()


@pytest.mark.parametrize("template_name, output_page", [
    ("catalog_index.tmpl", "index.html"),
    ("catalog_item.tmpl", "one/index.html"),
])
def test_template_change_rebuilds_without_data_change(site, template_name, output_page):
    write_csv(site, [record()])
    cli(site, "build")
    template = site / "templates" / template_name
    template.write_text(
        template.read_text().replace("{% block content %}", "{% block content %}<p>A template-only update</p>"),
        encoding="utf-8",
    )
    cli(site, "build")
    assert "A template-only update" in page(site, output_page).read_text()


def test_pending_journal_is_finished_without_data_change(site):
    write_csv(site, [record()])
    cli(site, "build")
    # Simulate a page and ownership journal left by an interrupted earlier build.
    unfinished = page(site, "unfinished/index.html")
    unfinished.parent.mkdir()
    unfinished.write_text("unfinished output", encoding="utf-8")
    pending = page(site, ".catalog-pending.json")
    pending.write_text(json.dumps({
        "version": 1,
        "paths": ["index.html", "one/index.html", "unfinished/index.html"],
    }), encoding="utf-8")
    cli(site, "build")
    assert not unfinished.exists()
    assert not pending.exists()
    assert page(site, "one/index.html").is_file()


def test_escaping_unicode_and_subpath(site):
    title = '<script>alert("title")</script> Робототехника'
    description = '<img src=x onerror="alert(1)"> & привет'
    write_csv(site, [record(title=title, description=description)])
    cli(site, "build", site_url="https://example.test/school/")
    assert_local_links(site, site / "output/index.html", "https://example.test/school/")
    root = html.parse(str(site / "output/index.html"))
    refresh = root.xpath("//meta[@http-equiv='refresh']/@content")[0]
    assert urljoin("https://example.test/school/", refresh.split("url=", 1)[1]) == "https://example.test/school/catalog/"
    for document, public_url in (
        (page(site), "https://example.test/school/catalog/"),
        (page(site, "one/index.html"), "https://example.test/school/catalog/one/"),
    ):
        tree = html.parse(str(document))
        assert not tree.xpath("//img[@onerror]")
        assert not tree.xpath("//script[contains(text(), 'alert')]")
        assert title in tree.getroot().text_content()
        assert description in tree.getroot().text_content()
        assert_local_links(site, document, public_url)


def test_managed_pages_are_in_native_sitemap(site):
    write_csv(site, [record("old")])
    cli(site, "build")
    write_csv(site, [record("new")])
    cli(site, "build")
    xml = (site / "output/sitemap.xml").read_text()
    assert "/catalog/new/" in xml
    assert "/catalog/old/" not in xml


@pytest.mark.parametrize("build_args", [("-n", "4", "-P", "thread"), ("sitemap",)])
def test_sitemap_scans_after_finalize_in_parallel_and_targeted_builds(site, build_args):
    write_csv(site, [record("old")])
    cli(site, "build", *build_args)
    assert "/catalog/old/" in (site / "output/sitemap.xml").read_text()
    write_csv(site, [record("new")])
    cli(site, "build", *build_args)
    xml = (site / "output/sitemap.xml").read_text()
    assert "/catalog/new/" in xml
    assert "/catalog/old/" not in xml
    assert not page(site, "old/index.html").exists()


def test_untracked_target_is_not_overwritten(site):
    write_csv(site, [record()])
    page(site).parent.mkdir(parents=True)
    page(site).write_text("hand written page", encoding="utf-8")
    cli(site, "build", ok=False)
    assert page(site).read_text() == "hand written page"


def test_custom_catalog_namespace_updates_home_navigation_and_pages(site):
    conf = site / "conf.py"
    conf.write_text(conf.read_text().replace('CATALOG_PATH = "catalog"', 'CATALOG_PATH = "products"'), encoding="utf-8")
    write_csv(site, [record()])
    cli(site, "build", site_url="https://example.test/school/")
    assert (site / "output/products/one/index.html").is_file()
    assert_local_links(site, site / "output/index.html", "https://example.test/school/")
    assert_local_links(site, site / "output/products/index.html", "https://example.test/school/products/")
    assert not (site / "output/catalog").exists()


def wait_for(predicate, process, log, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        if process.poll() is not None:
            break
        time.sleep(0.15)
    raise AssertionError(f"Nikola auto did not reach the expected state.\n{log.read_text()}")


@pytest.mark.watcher
@pytest.mark.parametrize("source", ["catalog_data/items.csv", "catalog_data/items.yaml"])
def test_auto_rebuilds_on_atomic_save_and_recovers_from_bad_input(site, source):
    def save(items, atomic=False, invalid=False):
        target = site / source
        if source.endswith("yaml"):
            content = "items: [broken" if invalid else yaml.safe_dump({"items": items}, allow_unicode=True)
        else:
            text = io.StringIO(newline="")
            writer = csv.DictWriter(text, fieldnames=["id", "slug", "title", "description"])
            writer.writeheader()
            writer.writerows(items if not invalid else [record(), record()])
            content = text.getvalue()
        if atomic:
            temporary = target.with_suffix(".tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(target)
        else:
            target.write_text(content, encoding="utf-8")

    save([record()])
    cli(site, "build", source=source)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = site / "auto.log"
    env = dict(os.environ, CATALOG_SOURCE=source)
    with log.open("w") as output:
        process = subprocess.Popen(
            [sys.executable, "-m", "nikola", "auto", "--port", str(port), "--address", "127.0.0.1"],
            cwd=site, env=env, stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            wait_for(lambda: "Serving on" in log.read_text(), process, log)
            save([record("two", "Automatically updated")], atomic=True)
            wait_for(lambda: page(site, "two/index.html").exists() and not page(site, "one/index.html").exists(), process, log)
            successful = page(site).read_bytes()
            save([], invalid=True)
            wait_for(lambda: "ERROR" in log.read_text() or "error" in log.read_text(), process, log)
            assert page(site).read_bytes() == successful
            save([record("three", "Recovered after invalid input")], atomic=True)
            wait_for(lambda: page(site, "three/index.html").exists() and not page(site, "two/index.html").exists(), process, log)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
