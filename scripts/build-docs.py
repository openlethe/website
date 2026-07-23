#!/usr/bin/env python3
"""Build the openlethe project wikis from vendored markdown sources.

Three projects, three themes (matching the landing pages):
  lethe   -> docs/<slug>.html          (cyan,  URL-stable legacy paths)
  charon  -> docs/charon/<slug>.html   (gold)
  matapan -> docs/matapan/<slug>.html  (green)

Sources live in docs/src/, docs/src-charon/, docs/src-matapan/ and mirror
each repo's /docs. Run with a python that has the `markdown` package:

    python3 scripts/build-docs.py
"""
import html
import pathlib
import re
import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# ---------------------------------------------------------------- themes
THEMES = {
    "lethe": {
        "accent": "#39d0e8", "soft": "rgba(57,208,232,.12)", "rgb": "57,208,232",
        "bg": "#05070a", "bg2": "#080d12", "ink": "#e8f2f5", "dim": "#7d99a3",
        "faint": "#41565e", "line": "#12242c", "pre": "#03080a", "preink": "#9fc3cd",
        "onaccent": "#04141a",
    },
    "charon": {
        "accent": "#d9a441", "soft": "rgba(217,164,65,.12)", "rgb": "217,164,65",
        "bg": "#070604", "bg2": "#0d0a06", "ink": "#f5efe4", "dim": "#a3988a",
        "faint": "#5c5344", "line": "#2a2214", "pre": "#0a0805", "preink": "#cbb693",
        "onaccent": "#1a1204",
    },
    "matapan": {
        "accent": "#3ddc97", "soft": "rgba(61,220,151,.12)", "rgb": "61,220,151",
        "bg": "#040806", "bg2": "#081209", "ink": "#e6f5ec", "dim": "#82a392",
        "faint": "#3f5c4c", "line": "#122a1c", "pre": "#030a06", "preink": "#9fcdb2",
        "onaccent": "#04140c",
    },
}

PROJECT_ORDER = ["lethe", "charon", "matapan"]
PROJECT_TITLES = {"lethe": "Lethe", "charon": "Charon", "matapan": "Matapan"}
PROJECT_GITHUB = {
    "lethe": "https://github.com/openlethe/lethe",
    "charon": "https://github.com/openlethe/charon",
    "matapan": "https://github.com/openlethe/matapan",
}
PROJECT_TAGLINE = {
    "lethe": "Agent memory layer",
    "charon": "MCP authorization gateway",
    "matapan": "Agent execution broker",
}

# (slug, source file, display title, nav group)
TOPICS = {
    "lethe": [
        ("overview",       "overview.md",       "Overview",              "Start"),
        ("installation",   "installation.md",   "Installation",          "Start"),
        ("runtime-modes",  "runtime-modes.md",  "Runtime Modes",         "Start"),
        ("memory-git",     "memory-git.md",     "Memory Git",            "Memory Systems"),
        ("legacy-mode",    "legacy-mode.md",    "Legacy Mode",           "Memory Systems"),
        ("architecture",   "architecture.md",   "Architecture",          "Platform"),
        ("configuration",  "configuration.md",  "Configuration",         "Platform"),
        ("deployment",     "deployment.md",     "Deployment & Ops",      "Platform"),
        ("docker-compose", "docker-compose.md", "Compose Variations",    "Platform"),
        ("api",            "api.md",            "HTTP API Reference",    "Reference"),
        ("openclaw",       "openclaw.md",       "OpenClaw",              "Integrations"),
        ("integrations",   "integrations.md",   "Client Integrations",   "Integrations"),
        ("migration",      "migration.md",      "Migration & Upgrading", "Project"),
        ("faq",            "faq.md",            "FAQ",                   "Project"),
        ("memory-git-v1",  "memory-git-v1.md",  "Protocol · memory_git/v1", "Deep Dive"),
        ("memory-context-bridge", "memory-context-bridge.md", "Context Projection", "Deep Dive"),
        ("observability",  "observability.md",  "Observability",         "Deep Dive"),
    ],
    "charon": [
        ("overview",   "overview.md",   "Overview",                 "Start"),
        ("full-run",   "full-run.md",   "Full Run: End to End",     "Start"),
        ("operations", "operations.md", "Operations",               "Platform"),
        ("reviewer",   "local-memory-reviewer.md", "Local Reviewer Setup", "Platform"),
    ],
    "matapan": [
        ("overview",          "overview.md",          "Overview",              "Start"),
        ("quickstart",        "quickstart.md",        "Quickstart",            "Start"),
        ("docker-compose",    "docker-compose.md",    "Docker Compose Setup",  "Deploy"),
        ("operations",        "operations.md",        "Operations",            "Deploy"),
        ("docker-limitations","docker-limitations.md","Docker Limitations",    "Deploy"),
        ("threat-model",      "threat-model.md",      "Threat Model",          "Security"),
        ("comparison-devspace","comparison-devspace.md","vs DevSpace",         "Project"),
    ],
}

SRC_DIRS = {"lethe": DOCS / "src", "charon": DOCS / "src-charon", "matapan": DOCS / "src-matapan"}
OUT_DIRS = {"lethe": DOCS, "charon": DOCS / "charon", "matapan": DOCS / "matapan"}

# ---------------------------------------------------------------- style
STYLE = """
:root{--bg:%%BG%%;--bg2:%%BG2%%;--ink:%%INK%%;--dim:%%DIM%%;--faint:%%FAINT%%;--cyan:%%ACC%%;--cyan-soft:%%SOFT%%;--line:%%LINE%%;--serif:'Cormorant Garamond',serif}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font-family:'Space Grotesk',sans-serif;overflow-x:hidden;font-size:15px;line-height:1.65}
::selection{background:var(--cyan);color:%%ONACC%%}
nav.top{position:fixed;top:0;left:0;right:0;z-index:50;display:flex;align-items:center;justify-content:space-between;padding:18px 40px;background:%%BGNAV%%;backdrop-filter:blur(14px);border-bottom:1px solid rgba(%%RGB%%,.08)}
.logo{font-weight:700;font-size:20px;letter-spacing:-.02em;text-decoration:none;color:var(--ink)}
.logo i{font-style:normal;color:var(--cyan)}
.navlinks{display:flex;gap:32px;align-items:center}
.navlinks a{color:var(--dim);text-decoration:none;font-size:13px;letter-spacing:.08em;transition:color .25s}
.navlinks a:hover{color:var(--cyan)}
.navlinks a.here{color:var(--cyan)}
.cta{border:1px solid var(--cyan);color:var(--cyan)!important;padding:9px 20px;font-size:12px!important;letter-spacing:.15em!important;text-transform:uppercase;text-decoration:none;transition:all .25s}
.cta:hover{background:var(--cyan);color:%%ONACC%%!important}
.dd{position:relative}
.ddt{cursor:pointer}
.ddm{display:none;position:absolute;top:calc(100%% + 16px);left:50%%;transform:translateX(-50%%);min-width:200px;background:var(--bg2);border:1px solid var(--line);padding:6px;z-index:60;box-shadow:0 24px 60px rgba(0,0,0,.5)}
.dd:hover .ddm,.dd:focus-within .ddm{display:block}
.ddm a{display:flex;align-items:center;gap:10px;padding:9px 12px;font-size:13px;color:var(--dim);text-decoration:none;letter-spacing:.04em}
.ddm a:hover{background:var(--bg);color:var(--ink)}
.ddm .sw{width:8px;height:8px;border-radius:50%%;flex:none}
.wiki{display:grid;grid-template-columns:270px minmax(0,1fr);gap:64px;max-width:1320px;margin:0 auto;padding:110px 32px 60px}
aside{position:sticky;top:96px;align-self:start;max-height:calc(100vh - 126px);overflow-y:auto;padding-right:14px;scrollbar-width:thin}
aside .proj{display:flex;gap:6px;margin-bottom:22px}
aside .proj a{flex:1;text-align:center;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;text-decoration:none;padding:7px 4px;border:1px solid var(--line);color:var(--faint);transition:all .2s}
aside .proj a:hover{color:var(--ink);border-color:var(--dim)}
aside .proj a.onl{color:#39d0e8;border-color:#39d0e8}
aside .proj a.onc{color:#d9a441;border-color:#d9a441}
aside .proj a.onm{color:#3ddc97;border-color:#3ddc97}
aside .grp{margin-bottom:26px}
aside .gt{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.3em;color:var(--faint);text-transform:uppercase;margin-bottom:10px}
aside a{display:block;color:var(--dim);text-decoration:none;font-size:13px;padding:5px 0 5px 16px;border-left:1px solid var(--line);transition:all .2s;line-height:1.4}
aside a:hover{color:var(--cyan)}
aside a.on{color:var(--cyan);border-left-color:var(--cyan)}
main{min-width:0;max-width:860px}
main h1{font-family:var(--serif);font-weight:400;font-size:clamp(32px,4.5vw,46px);line-height:1.1;margin:14px 0 18px}
main h2{font-family:var(--serif);font-weight:400;font-size:clamp(24px,3vw,32px);line-height:1.15;margin:40px 0 12px;padding-top:22px;border-top:1px solid var(--line)}
main h2:first-of-type{border-top:none;padding-top:0}
main h3{font-size:18px;font-weight:600;margin:28px 0 8px}
main p{color:var(--dim);margin:12px 0;font-weight:300}
main b,main strong{color:var(--ink);font-weight:500}
main a{color:var(--cyan)}
main ul,main ol{color:var(--dim);margin:12px 0 16px 22px;font-weight:300}
main li{margin:6px 0}
main code{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--cyan);background:var(--cyan-soft);padding:2px 7px;border-radius:4px}
main pre{background:%%PRE%%;border:1px solid var(--line);border-radius:6px;padding:18px 20px;overflow-x:auto;margin:16px 0}
main pre code{font-family:'JetBrains Mono',monospace;font-size:12.5px;line-height:1.8;color:%%PREINK%%;background:none;padding:0}
main table{width:100%%;border-collapse:collapse;margin:16px 0;font-size:13px}
main th{font-family:'JetBrains Mono',monospace;font-size:9.5px;letter-spacing:.25em;text-transform:uppercase;color:var(--faint);text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}
main td{padding:11px 12px;border-bottom:1px solid var(--line);color:var(--dim);line-height:1.55;vertical-align:top;font-weight:300}
main td code{white-space:nowrap}
main tr:hover td{background:rgba(%%RGB%%,.03)}
main blockquote{border-left:2px solid var(--cyan);padding:8px 0 8px 18px;margin:16px 0;color:var(--dim);font-weight:300}
main hr{border:none;border-top:1px solid var(--line);margin:28px 0}
.kick{font-family:'JetBrains Mono',monospace;font-size:10.5px;letter-spacing:.28em;color:var(--cyan);text-transform:uppercase}
.pn{display:flex;justify-content:space-between;gap:16px;margin-top:56px;padding-top:20px;border-top:1px solid var(--line);font-size:13px}
.pn a{color:var(--dim);text-decoration:none}
.pn a:hover{color:var(--cyan)}
.pn .n{margin-left:auto}
footer{border-top:1px solid var(--line);padding:40px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;margin-top:40px}
footer .fl{font-weight:700;font-size:18px}
footer .fl i{font-style:normal;color:var(--cyan)}
footer a{color:var(--faint);text-decoration:none;font-size:13px;margin-left:24px;transition:color .25s}
footer a:hover{color:var(--cyan)}
footer .fc{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--faint);letter-spacing:.15em}
@media(max-width:1000px){.wiki{grid-template-columns:1fr;gap:0;padding-top:100px}aside{position:static;max-height:none;display:flex;flex-wrap:wrap;gap:8px;margin-bottom:26px}aside .grp{margin:0}aside .gt{display:none}aside a{border:1px solid var(--line);padding:6px 12px;font-size:12px}.navlinks a:not(.cta){display:none}.ddm{position:static;transform:none;display:block;box-shadow:none;background:none;border:none;padding:0}}
"""

TOC_EXTRA = """
.tocwrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:2px;background:var(--line);border:1px solid var(--line);margin-top:28px}
a.toc{display:flex;align-items:center;gap:12px;background:var(--bg);padding:16px 18px;text-decoration:none;color:var(--ink)}
a.toc:hover{background:var(--bg2)}
a.toc b{font-weight:600;font-size:14px}
a.toc .n{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--cyan)}
a.toc .g{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--faint);letter-spacing:.12em;text-transform:uppercase}
"""


def style_for(project):
    t = THEMES[project]
    return (STYLE
            .replace("%%BGNAV%%", t["bg"] + "d9")
            .replace("%%BG2%%", t["bg2"]).replace("%%BG%%", t["bg"])
            .replace("%%INK%%", t["ink"]).replace("%%DIM%%", t["dim"])
            .replace("%%FAINT%%", t["faint"]).replace("%%LINE%%", t["line"])
            .replace("%%SOFT%%", t["soft"]).replace("%%ONACC%%", t["onaccent"])
            .replace("%%ACC%%", t["accent"])
            .replace("%%RGB%%", t["rgb"])
            .replace("%%PREINK%%", t["preink"]).replace("%%PRE%%", t["pre"])
            .replace("%%", "%"))


# ---------------------------------------------------------------- helpers
def dd_links(prefix):
    """Docs dropdown menu items with per-project color swatches."""
    items = []
    for p in PROJECT_ORDER:
        href = f"{prefix}index.html" if p == "lethe" else f"{prefix}{p}/index.html"
        items.append(
            f'<a href="{href}"><span class="sw" style="background:{THEMES[p]["accent"]}"></span>{PROJECT_TITLES[p]} docs</a>'
        )
    return "\n".join(items)


def nav_for(project, active):
    out, group = [], None
    for slug, _, title, grp in TOPICS[project]:
        if grp != group:
            group = grp
            out.append(f'<div class="grp"><div class="gt">{html.escape(grp)}</div>')
        cls = ' class="on"' if slug == active else ""
        out.append(f'<a href="{slug}.html"{cls}>{html.escape(title)}</a>')
    out.append("</div>")
    return "\n".join(out)


def proj_switcher(project):
    """Sidebar project switcher with correct relative paths per wiki depth."""
    depth = "" if project == "lethe" else "../"
    links = []
    for p in PROJECT_ORDER:
        if p == project:
            cls = {"lethe": "onl", "charon": "onc", "matapan": "onm"}[p]
            href = "index.html"
        else:
            cls = ""
            href = f"{depth}index.html" if p == "lethe" else f"{depth}{p}/index.html"
        links.append(f'<a class="{cls}" href="{href}">{PROJECT_TITLES[p]}</a>')
    return '<div class="proj">' + "\n".join(links) + "</div>"


def page(project, slug, title, body):
    topics = TOPICS[project]
    idx = [t[0] for t in topics]
    i = idx.index(slug) if slug in idx else -1
    prev_html = next_html = ""
    if i > 0:
        s, _, t, _ = topics[i - 1]
        prev_html = f'<a class="p" href="{s}.html">← {html.escape(t)}</a>'
    if 0 <= i < len(topics) - 1:
        s, _, t, _ = topics[i + 1]
        next_html = f'<a class="n" href="{s}.html">{html.escape(t)} →</a>'
    active = slug if slug in idx else topics[0][0]
    t = THEMES[project]
    home_prefix = "../" if project == "lethe" else "../../"
    docs_prefix = "" if project == "lethe" else "../"
    name = PROJECT_TITLES[project]
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — {name} Docs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;1,400&family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{style_for(project)}</style>
</head>
<body>
<nav class="top">
  <a class="logo" href="{home_prefix}index.html">{name}<i>.</i></a>
  <div class="navlinks">
    <a href="{home_prefix}index.html">Lethe</a>
    <a href="{home_prefix}charon.html">Charon</a>
    <a href="{home_prefix}matapan.html">Matapan</a>
    <div class="dd">
      <a class="ddt here" href="{home_prefix}docs.html">Docs ▾</a>
      <div class="ddm">
{dd_links(docs_prefix)}
      </div>
    </div>
    <a href="{docs_prefix}skills/index.html">Skills</a>
    <a href="{PROJECT_GITHUB[project]}">GitHub</a>
    <a class="cta" href="{topics[1][0] if len(topics) > 1 else 'index'}.html">Get started</a>
  </div>
</nav>
<div class="wiki">
<aside>
{proj_switcher(project)}
{nav_for(project, active)}
</aside>
<main>
<div class="kick">{name} docs · {html.escape(title)}</div>
{body}
<div class="pn">{prev_html}{next_html}</div>
</main>
</div>
<footer>
  <div class="fl">{name}<i>.</i></div>
  <div>
    <a href="{PROJECT_GITHUB[project]}" style="margin-left:0">GitHub</a>
    <a href="{home_prefix}index.html">Lethe</a>
    <a href="{home_prefix}charon.html">Charon</a>
    <a href="{home_prefix}matapan.html">Matapan</a>
  </div>
  <div class="fc">openlethe.com · 2026</div>
</footer>
</body>
</html>
"""


def render(md_text):
    # Repo-relative doc links (foo.md, foo.md#frag) become on-site .html
    # links; absolute URLs are left alone.
    md_text = re.sub(r"\]\((?!https?://)([A-Za-z0-9_./-]+)\.md(#[A-Za-z0-9_-]+)?\)",
                     lambda m: f"]({m.group(1)}.html{m.group(2) or ''})", md_text)
    return markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "sane_lists", "toc"]
    )


def build_project(project):
    out_dir = OUT_DIRS[project]
    out_dir.mkdir(parents=True, exist_ok=True)
    topics = TOPICS[project]
    src = SRC_DIRS[project]
    for slug, srcfile, title, _ in topics:
        body = render((src / srcfile).read_text())
        (out_dir / f"{slug}.html").write_text(page(project, slug, title, body))
    # Landing TOC page
    cards = "\n".join(
        f'<a class="toc" href="{slug}.html"><span class="n">{i+1:02d}</span><b>{html.escape(title)}</b><span class="g">{html.escape(grp)}</span></a>'
        for i, (slug, _, title, grp) in enumerate(topics)
    )
    name = PROJECT_TITLES[project]
    landing_body = f"""
<h1>{name} documentation.</h1>
<p style="max-width:640px">{PROJECT_TAGLINE[project]} — read in order, or jump to a topic. These pages mirror <code>docs/</code> in the <a href="{PROJECT_GITHUB[project]}">{project} repository</a>; regenerate them with <code>scripts/build-docs.py</code>.</p>
<div class="tocwrap">{cards}</div>
"""
    (out_dir / "index.html").write_text(
        page(project, "index", "Documentation", landing_body).replace("</style>", TOC_EXTRA + "</style>")
    )
    print(f"[{project}] built {len(topics)} topic pages + index -> {out_dir.relative_to(ROOT)}")


def main():
    for project in PROJECT_ORDER:
        build_project(project)


if __name__ == "__main__":
    main()
