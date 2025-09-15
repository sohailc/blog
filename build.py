import json
import shutil
from datetime import datetime, UTC
from pathlib import Path
from xml.sax.saxutils import escape
from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown  # NEW

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
OUT = ROOT / "dist"


def load_json(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_markdown(md_path: Path) -> str:
    text = md_path.read_text(encoding="utf-8")
    return markdown.markdown(text, extensions=[])  # add extensions if you want


def load_section(post_dir: Path, section: dict) -> dict:
    """Normalize section dicts and PRESERVE extra fields (margin images, captions)."""
    stype = section.get("type")

    def keep_extras(dst: dict):
        extras = (
            "left_margin_image", "left_margin_alt", "left_margin_caption",
            "right_margin_image", "right_margin_alt", "right_margin_caption",
            "note_html"  # if you ever pre-render notes
        )
        for k in extras:
            if k in section:
                dst[k] = section[k]
        return dst

    if stype == "markdown":
        html = render_markdown(post_dir / section["file"])
        return keep_extras({"type": "html", "html": html})

    if stype == "expander":
        # Support expander with markdown file OR plain text content
        if "file" in section:
            html = render_markdown(post_dir / section["file"])
            return keep_extras({"type": "expander_html", "label": section.get("label", "More"), "html": html})
        else:
            return keep_extras(section)

    # pass-through for other types (e.g., 'p', already 'html', notes, etc.)
    return keep_extras(section)


def gen_rss(site, posts):
    base = site.get("base_url", "").rstrip("/")
    items = []
    for post in posts:
        url = f"{base}/posts/{post['slug']}/"
        # try to grab a textual summary from first section if possible
        desc = ""
        if post.get("sections"):
            first = post["sections"][0]
            if first.get("type") == "p":
                desc = first.get("text", "")
        items.append(
            f"<item><title>{escape(post['title'])}</title>"
            f"<link>{escape(url)}</link>"
            f"<guid>{escape(url)}</guid>"
            f"<pubDate>{post['date']}</pubDate>"
            f"<description>{escape(desc)}</description></item>"
        )
    rss = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        f"<rss version=\"2.0\"><channel><title>{site['title']}</title>"
        f"<link>{base}/</link><description>{site['description']}</description>"
        + "".join(items)
        + "</channel></rss>"
    )
    write(OUT / "feed.xml", rss)


def gen_sitemap(site, posts):
    base = site.get("base_url", "").rstrip("/")
    urls = [f"{base}/"]
    if (CONTENT / "about.json").exists():
        urls.append(f"{base}/about.html")
    urls += [f"{base}/posts/{p['slug']}/" for p in posts]
    body = "".join([f"<url><loc>{u}</loc></url>" for u in urls])
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"
        + body
        + "</urlset>"
    )
    write(OUT / "sitemap.xml", xml)


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    site = load_json(CONTENT / "site.json")
    base_url = site.get("base_url", "").rstrip("/")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals.update(site=site, base=base_url, now=datetime.now(UTC))

    # Copy static assets
    if STATIC.exists():
        shutil.copytree(STATIC, OUT / "static")

    # Load posts (support both flat .json files and per-post folders with post.json)
    posts = []
    posts_dir = CONTENT / "posts"

    # 1) Per-post folders with post.json
    for post_json in sorted(posts_dir.glob("*/post.json")):
        post = load_json(post_json)
        if post.get("draft"):
            continue
        post_dir = post_json.parent
        post["sections"] = [load_section(post_dir, s) for s in post.get("sections", [])]
        posts.append(post)

    # 2) Back-compat: flat files like content/posts/*.json
    for p in sorted(posts_dir.glob("*.json")):
        if p.name == "post.json":
            continue
        post = load_json(p)
        if post.get("draft"):
            continue
        # sections may reference no files here; keep as-is
        posts.append(post)

    # Render index
    tmpl_index = env.get_template("index.html")
    write(OUT / "index.html", tmpl_index.render(title="Home", posts=list(reversed(posts))))

    # Render posts
    tmpl_post = env.get_template("post.html")
    for post in posts:
        write(
            OUT / "posts" / post["slug"] / "index.html",
            tmpl_post.render(title=post["title"], post=post),
        )

    # Optional: About page (still JSON for now)
    about_src = CONTENT / "about.json"
    if about_src.exists():
        about = load_json(about_src)
        write(OUT / "about.html", tmpl_post.render(title=about["title"], post=about))

    # Feeds and sitemap
    gen_rss(site, posts)
    gen_sitemap(site, posts)

    # Optional custom domain
    cname = site.get("cname")
    if cname:
        write(OUT / "CNAME", cname.strip() + "\n")

    print("Built to", OUT)


if __name__ == "__main__":
    build()
