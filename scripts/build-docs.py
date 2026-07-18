#!/usr/bin/env python3
"""Build the Lethe wiki from docs/src/*.md into docs/<slug>.html pages.

Reads the vendored markdown sources (mirrored from the lethe repo's /docs)
and emits one page per topic in README table-of-contents order, wrapped in
the shared wiki layout: left sidebar with clickable topic nav, active state,
and prev/next links. Run with a python that has the `markdown` package:

    python3 scripts/build-docs.py
"""
import html
import pathlib
import re
import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "src"
OUT = ROOT / "docs"

# (slug, source file, display title, nav group) — README table-of-contents order.
TOPICS = [
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
]

STYLE = """
:root{--bg:#05070a;--bg2:#080d12;--ink:#e8f2f5;--dim:#7d99a3;--faint:#41565e;--cyan:#39d0e8;--cyan-soft:rgba(57,208,232,.12);--line:#12242c;--serif:'Cormorant Garamond',serif;--gold:#d9a441;--gold-soft:rgba(217,164,65,.12)}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font-family:'Space Grotesk',sans-serif;overflow-x:hidden;font-size:15px;line-height:1.65}
::selection{background:var(--cyan);color:#04141a}
nav.top{position:fixed;top:0;left:0;right:0;z-index:50;display:flex;align-items:center;justify-content:space-between;padding:18px 40px;background:rgba(5,7,10,.55);backdrop-filter:blur(14px);border-bottom:1px solid rgba(57,208,232,.08)}
.logo{font-weight:700;font-size:20px;letter-spacing:-.02em;text-decoration:none;color:var(--ink)}
.logo i{font-style:normal;color:var(--cyan)}
.navlinks{display:flex;gap:32px;align-items:center}
.navlinks a{color:var(--dim);text-decoration:none;font-size:13px;letter-spacing:.08em;transition:color .25s}
.navlinks a:hover{color:var(--cyan)}
.navlinks a.here{color:var(--cyan)}
.cta{border:1px solid var(--cyan);color:var(--cyan)!important;padding:9px 20px;font-size:12px!important;letter-spacing:.15em!important;text-transform:uppercase;text-decoration:none;transition:all .25s}
.cta:hover{background:var(--cyan);color:#04141a!important}
.wiki{display:grid;grid-template-columns:270px minmax(0,1fr);gap:64px;max-width:1320px;margin:0 auto;padding:110px 32px 60px}
aside{position:sticky;top:96px;align-self:start;max-height:calc(100vh - 126px);overflow-y:auto;padding-right:14px;scrollbar-width:thin}
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
main pre{background:#03080a;border:1px solid var(--line);border-radius:6px;padding:18px 20px;overflow-x:auto;margin:16px 0}
main pre code{font-family:'JetBrains Mono',monospace;font-size:12.5px;line-height:1.8;color:#9fc3cd;background:none;padding:0}
main table{width:100%;border-collapse:collapse;margin:16px 0;font-size:13px}
main th{font-family:'JetBrains Mono',monospace;font-size:9.5px;letter-spacing:.25em;text-transform:uppercase;color:var(--faint);text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}
main td{padding:11px 12px;border-bottom:1px solid var(--line);color:var(--dim);line-height:1.55;vertical-align:top;font-weight:300}
main td code{white-space:nowrap}
main tr:hover td{background:rgba(57,208,232,.03)}
main blockquote{border-left:2px solid var(--gold);padding:8px 0 8px 18px;margin:16px 0;color:var(--dim);font-weight:300}
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
@media(max-width:1000px){.wiki{grid-template-columns:1fr;gap:0;padding-top:100px}aside{position:static;max-height:none;display:flex;flex-wrap:wrap;gap:8px;margin-bottom:26px}aside .grp{margin:0}aside .gt{display:none}aside a{border:1px solid var(--line);padding:6px 12px;font-size:12px}.navlinks a:not(.cta){display:none}}
"""

def nav(active):
    out, group = [], None
    for slug, _, title, grp in TOPICS:
        if grp != group:
            group = grp
            out.append(f'<div class="grp"><div class="gt">{html.escape(grp)}</div>')
        cls = ' class="on"' if slug == active else ""
        out.append(f'<a href="{slug}.html"{cls}>{html.escape(title)}</a>')
    out.append("</div>")
    return "\n".join(out)

def page(slug, title, body):
    idx = [t[0] for t in TOPICS]
    i = idx.index(slug) if slug in idx else -1
    prev_html = next_html = ""
    if i > 0:
        s, _, t, _ = TOPICS[i - 1]
        prev_html = f'<a class="p" href="{s}.html">← {html.escape(t)}</a>'
    if 0 <= i < len(TOPICS) - 1:
        s, _, t, _ = TOPICS[i + 1]
        next_html = f'<a class="n" href="{s}.html">{html.escape(t)} →</a>'
    active = slug if slug in idx else "overview"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — Lethe Docs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;1,400&family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{STYLE}</style>
</head>
<body>
<nav class="top">
  <a class="logo" href="../index.html">Lethe<i>.</i></a>
  <div class="navlinks">
    <a href="../index.html">Lethe</a>
    <a href="../charon.html">Charon</a>
    <a href="index.html" class="here">Docs</a>
    <a href="https://github.com/openlethe/lethe">GitHub</a>
    <a class="cta" href="installation.html">Get started</a>
  </div>
</nav>
<div class="wiki">
<aside>
{nav(active)}
</aside>
<main>
<div class="kick">Lethe docs · {html.escape(title)}</div>
{body}
<div class="pn">{prev_html}{next_html}</div>
</main>
</div>
<footer>
  <div class="fl">Lethe<i>.</i></div>
  <div>
    <a href="https://github.com/openlethe/lethe" style="margin-left:0">GitHub</a>
    <a href="../index.html">Lethe</a>
    <a href="../charon.html">Charon</a>
  </div>
  <div class="fc">openlethe.com · 2026</div>
</footer>
</body>
</html>
"""

def render(md_text):
    return markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "sane_lists"]
    )

def main():
    OUT.mkdir(exist_ok=True)
    for slug, src, title, _ in TOPICS:
        body = render((SRC / src).read_text())
        (OUT / f"{slug}.html").write_text(page(slug, title, body))
    # Landing TOC page
    cards = "\n".join(
        f'<a class="toc" href="{slug}.html"><span class="n">{i+1:02d}</span><b>{html.escape(title)}</b><span class="g">{html.escape(grp)}</span></a>'
        for i, (slug, _, title, grp) in enumerate(TOPICS)
    )
    landing_body = f"""
<h1>Documentation.</h1>
<p style="max-width:640px">Everything about running and integrating Lethe — read in order, or jump to a topic. These pages mirror <code>docs/</code> in the <a href="https://github.com/openlethe/lethe">lethe repository</a>; regenerate them with <code>scripts/build-docs.py</code>.</p>
<div class="tocwrap">{cards}</div>
"""
    landing_extra = """
.tocwrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:2px;background:var(--line);border:1px solid var(--line);margin-top:28px}
a.toc{display:flex;align-items:center;gap:12px;background:var(--bg);padding:16px 18px;text-decoration:none;color:var(--ink)}
a.toc:hover{background:var(--bg2)}
a.toc b{font-weight:600;font-size:14px}
a.toc .n{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--cyan)}
a.toc .g{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--faint);letter-spacing:.12em;text-transform:uppercase}
"""
    (OUT / "index.html").write_text(
        page("index", "Documentation", landing_body).replace("</style>", landing_extra + "</style>")
    )
    print(f"built {len(TOPICS)} topic pages + index")

if __name__ == "__main__":
    main()
