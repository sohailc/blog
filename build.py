#!/usr/bin/env python3
import json, shutil, re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

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
    """Render a Markdown file to HTML with useful extensions, including attr_list for image classes."""
    text = path.read_text(encoding="utf-8")
    return md.markdown(
        text,
        extensions=[
            # Core ergonomics:
            "extra",        # tables, fenced code, etc.
            "sane_lists",
            "smarty",
            "toc",
            # Enable `{.class #id key=val}` on images, links, etc.
            "attr_list",
        ]
    )

def slugify(text: str) -> str:
    s = text.strip().lower()
    s = s.replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-") or "chapter"

# ---------- Section normalization (preserve extras) ----------

EXTRA_KEYS = (
    "left_margin_image","left_margin_alt","left_margin_caption",
    "right_margin_image","right_margin_alt","right_margin_caption",
    "left_note","left_note_html","right_note","right_note_html",
    "label","title","section_slug",
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
            return keep_extras(section, section)

    return keep_extras(section, section)

# ---------- Load posts ----------

def load_site() -> Dict[str, Any]:
    site_json = CONTENT / "site.json"
    if site_json.exists():
        return read_json(site_json)
    return {"title": "My Blog", "description": "", "base_url": ""}

def load_posts() -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []
    if POSTS.exists():
        for pdir in sorted(POSTS.iterdir()):
            if pdir.is_dir() and (pdir / "post.json").exists():
                post = read_json(pdir / "post.json")
                # normalize sections
                sections = []
                for s in post.get("sections", []):
                    ns = load_section(pdir, s)
                    # derive a per-section slug if title present (for chapter URLs)
                    if "section_slug" in ns and ns["section_slug"]:
                        sec_slug = slugify(ns["section_slug"])
                    else:
                        title = ns.get("title")
                        sec_slug = slugify(title) if title else f"section-{len(sections)+1}"
                    ns["section_slug"] = sec_slug
                    sections.append(ns)
                post["sections"] = sections
                post["dir"] = pdir
                posts.append(post)

    # sort newest first
    def _key(p):
        try:
            return datetime.fromisoformat(p.get("date", "1970-01-01"))
        except Exception:
            return datetime(1970,1,1)
    posts.sort(key=_key, reverse=True)
    return posts

# ---------- Jinja ----------

def jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"])
    )
    return env

# ---------- Renderers ----------

def render_series_landing(env: Environment, site: Dict[str, Any], post: Dict[str, Any]):
    """Landing page at /posts/<series-slug>/ with TOC and optional intro sections."""
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

def render_chapter_page(env: Environment, site: Dict[str, Any], post: Dict[str, Any], idx: int):
    """Per-chapter page at /posts/<series-slug>/<chapter-slug>/"""
    sections = post["sections"]
    section = sections[idx]

    # compute prev/next
    prev_info: Optional[Dict[str, str]] = None
    next_info: Optional[Dict[str, str]] = None
    if idx > 0:
        prev_section = sections[idx-1]
        prev_info = {
            "slug": prev_section["section_slug"],
            "title": prev_section.get("title", f"Chapter {idx}"),
        }
    if idx < len(sections)-1:
        next_section = sections[idx+1]
        next_info = {
            "slug": next_section["section_slug"],
            "title": next_section.get("title", f"Chapter {idx+2}"),
        }

    tmpl = env.get_template("chapter.html")
    base_url = site.get("base_url","").rstrip("/")
    ctx = {
        "site": site,
        "base": base_url,
        "post": post,          # series metadata
        "section": section,    # this chapter
        "index": idx,
        "prev": prev_info,
        "next": next_info,
        "now": datetime.now(timezone.utc),
    }
    html = tmpl.render(**ctx)
    out = DIST / "posts" / post["slug"] / section["section_slug"] / "index.html"
    write_text(out, html)

def render_index(env: Environment, site: Dict[str, Any], posts: List[Dict[str, Any]]):
    tmpl = env.get_template("index.html")
    base_url = site.get("base_url","").rstrip("/")
    ctx = {"site": site, "base": base_url, "posts": posts, "now": datetime.now(timezone.utc)}
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

# ---------- Build ----------

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

    # For each series post:
    for post in posts:
        # 1) Series landing (TOC)
        render_series_landing(env, site, post)
        # 2) Per-chapter pages
        for i in range(len(post.get("sections", []))):
            render_chapter_page(env, site, post, i)

    # Index + About
    render_index(env, site, posts)
    render_about(env, site)

if __name__ == "__main__":
    build()
    print("Built site into", DIST)
