import json
import shutil
from datetime import datetime, UTC
from pathlib import Path
from xml.sax.saxutils import escape
from jinja2 import Environment, FileSystemLoader, select_autoescape

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


def gen_rss(site, posts):
    """Generate a minimal RSS feed from posts."""
    base = site.get("base_url", "").rstrip("/")
    items = []
    for post in posts:
        url = f"{base}/posts/{post['slug']}/"
        desc = ""
        if post.get("sections"):
            first = post["sections"][0]
            desc = first.get("text", "") if first.get("type") == "p" else ""
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
    """Generate a sitemap.xml for SEO."""
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
    """Main build pipeline: copy assets, render templates, emit dist/."""
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

    # Load posts
    posts = []
    for p in sorted((CONTENT / "posts").glob("*.json")):
        post = load_json(p)
        if post.get("draft"):
            continue
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

    # Optional: About page
    about_src = CONTENT / "about.json"
    if about_src.exists():
        about = load_json(about_src)
        write(OUT / "about.html", tmpl_post.render(title=about["title"], post=about))

    # Feeds and sitemap
    gen_rss(site, posts)
    gen_sitemap(site, posts)

    # Optional: custom domain CNAME
    cname = site.get("cname")
    if cname:
        write(OUT / "CNAME", cname.strip() + "\n")

    print("Built to", OUT)


if __name__ == "__main__":
    build()
