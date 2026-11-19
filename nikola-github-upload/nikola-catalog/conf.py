"""Site settings. Start here, then read plugins/catalog/catalog.py."""

import os
import sys
from pathlib import Path

# Make the small, local Python package importable by Nikola's plugin loader.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Site name, address, and appearance.
BLOG_AUTHOR = "Campus Collection team"
BLOG_TITLE = "Campus Collection"
BLOG_DESCRIPTION = "Student projects, shared ideas, and things worth joining."
SITE_URL = os.environ.get("NIKOLA_SITE_URL", "http://localhost:8000/")
DEFAULT_LANG = "en"
TRANSLATIONS = {"en": ""}
TIMEZONE = "Europe/Berlin"
THEME = "bootstrap4-jinja"
THEME_COLOR = "#132c37"

# Our plugin's settings. Edit this CSV by default, or select a YAML file.
# os.environ.get allows a temporary choice without editing this configuration.
CATALOG_SOURCE = os.environ.get("CATALOG_SOURCE", "catalog_data/items.csv")
CATALOG_PATH = "catalog"
CATALOG_TITLE = BLOG_TITLE
CATALOG_DESCRIPTION = BLOG_DESCRIPTION

# Standard Nikola settings: keep generated HTML separate from source files.
OUTPUT_FOLDER = "output"
CACHE_FOLDER = "cache"
POSTS = ()
PAGES = ()
COMPILERS = {"rest": (".rst",)}
FILES_FOLDERS = {"files": ""}
GALLERY_FOLDERS = {}
LISTINGS_FOLDERS = {}
IMAGE_FOLDERS = {}
DISABLE_INDEXES = True
GENERATE_RSS = False
GENERATE_ATOM = False
ENABLE_AUTHOR_PAGES = False
PRETTY_URLS = True
STRIP_INDEXES = True
URL_TYPE = "rel_path"
USE_BUNDLES = False
USE_CDN = False
FAVICONS = (("icon", "/favicon.svg", "any"),)
COPY_SOURCES = False
SEARCH_FORM = ""
# Send visitors to our catalog instead of a blog index.
NAVIGATION_LINKS = {"en": ((f"/{CATALOG_PATH}/", "The collection"),)}
NAVIGATION_ALT_LINKS = {"en": ()}
REDIRECTIONS = [("index.html", f"{CATALOG_PATH}/")]
CONTENT_FOOTER = "<span>Campus Collection</span> · A space for shared ideas."
