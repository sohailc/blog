#!/usr/bin/env python3
import json, shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown as md

ROOT = Path(__file__).parent.resolve()
CONTENT = ROOT / "content"
POSTS = CONTENT / "posts"
DIST = ROOT / "dist"
STATIC = ROOT / "static"
TEMPLATES = ROOT / "templates"

# ---------- Utilities ----------

def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(text)

def copy_static():
    out = DIST / "static"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC, out)

def render_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return md.markdown(
        text,
        extensions=["extra", "sane_lists", "smarty", "toc"]
    )

# ---------- Section normalization (preserve extras!) ----------

EXTRA_KEYS = (
    # per-section margin images/notes
    "left_margin_image","left_margin_alt","left_margin_caption",
    "right_margin_image","right_margin_alt","right_margin_caption",
    "left_note","left_note_html","right_note","right_note_html",
    # expander label
    "label",
    # chapter title (NEW)
    "title",
)

def keep_extras(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for k in EXTRA_KEYS:
        if k in src:
            dst[k] = src[k]
    return dst

def load_section(post_dir: Path, section: Dict[str, Any]) -> Dict[str, Any]:
    stype = section.get("type")
    if stype == "markdown":
        html = render_markdown(post_dir / section["file"])
        return keep_extras({"type": "html", "html": html}, section)

    if stype == "expander":
        if "file" in section:
            html = render_markdown(post_dir / section["file"])
            return keep_extras({"type": "expander_html", "label": section.get("label","More"), "html": html}, section)
        else:
            # plain-text expander passthrough
            return keep_extras(section, section)

    # passthrough other types (already 'html', 'p', etc.)
    return keep_extras(section, section)

# ---------- Load posts ----------

def load_site() -> Dict[str, Any]:
    site_json = CONTENT / "site.json"
    if site_json.exists():
        return read_json(site_json)
    return {
        "title": "My Blog",
        "description": "",
        "base_url": "",
    }

def load_posts() -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []
    if POSTS.exists():
        for pdir in sorted(POSTS.iterdir()):
            if pdir.is_dir() and (pdir / "post.json").exists():
                post = read_json(pdir / "post.json")
                # normalize sections
                sections = []
                for s in post.get("sections", []):
                    sections.append(load_section(pdir, s))
                post["sections"] = sections
                post["dir"] = pdir
                posts.append(post)
    # sort newest first by date if present
    def _key(p):
        try:
            return datetime.fromisoformat(p.get("date", "1970-01-01"))
        except Exception:
            return datetime(1970,1,1)
    posts.sort(key=_key, reverse=True)
    return posts

# ---------- Render ----------

def jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"])
    )
    return env

def render_post(env: Environment, site: Dict[str, Any], post: Dict[str, Any]):
    tmpl = env.get_template("post.html")
    base_url = site.get("base_url","").rstrip("/")
    ctx = {
        "site": site,
        "base": base_url,
        "post": post,
        "now": datetime.now(timezone.utc),
    }
    html = tmpl.render(**ctx)
    out = DIST / "posts" / post["slug"] / "index.html"
    write_text(out, html)

def render_index(env: Environment, site: Dict[str, Any], posts: List[Dict[str, Any]]):
    tmpl = env.get_template("index.html")
    base_url = site.get("base_url","").rstrip("/")
    ctx = {
        "site": site,
        "base": base_url,
        "posts": posts,
        "now": datetime.now(timezone.utc),
    }
    html = tmpl.render(**ctx)
    out = DIST / "index.html"
    write_text(out, html)

def render_about(env: Environment, site: Dict[str, Any]):
    about_tmpl = TEMPLATES / "about.html"
    if about_tmpl.exists():
        tmpl = env.get_template("about.html")
        base_url = site.get("base_url","").rstrip("/")
        ctx = {"site": site, "base": base_url, "now": datetime.now(timezone.utc)}
        html = tmpl.render(**ctx)
        write_text(DIST / "about.html", html)

def clean_dist():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

def build():
    clean_dist()
    copy_static()
    site = load_site()
    posts = load_posts()
    env = jinja_env()

    # Render posts
    for post in posts:
        render_post(env, site, post)

    # Index + About
    render_index(env, site, posts)
    render_about(env, site)

if __name__ == "__main__":
    build()
    print("Built site into", DIST)
