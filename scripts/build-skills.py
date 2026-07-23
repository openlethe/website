#!/usr/bin/env python3
"""Build the skills section: copy raw SKILL.md files from each project
repo and generate docs/skills/index.html (docs-wiki layout).

Run after scripts/build-docs.py, with a python that has `markdown`:
    python3 scripts/build-skills.py
"""
import html
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Reuse themes/order/style from the docs builder (no duplication).
spec = importlib.util.spec_from_file_location("build_docs", ROOT / "scripts" / "build-docs.py")
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)

PROJECT_ORDER = bd.PROJECT_ORDER
PROJECT_TITLES = bd.PROJECT_TITLES
THEMES = bd.THEMES
style_for = bd.style_for

# (skill id, source repo-relative path, one-line blurb)
SKILLS = {
    "lethe": [
        ("lethe-memory", "skills/lethe-memory/SKILL.md",
         "Startup orientation, recall, logging, flags, and session compaction with Lethe memory."),
    ],
    "charon": [
        ("charon", "skills/charon/SKILL.md",
         "Versioned Lethe memory through the Charon gateway: recall, record, owned refs, CAS changesets."),
        ("charon-proposer", "skills/charon-proposer/SKILL.md",
         "Author durable memory as a proposer: branches, commits, merge proposals."),
        ("charon-reviewer", "skills/charon-reviewer/SKILL.md",
         "Independently review and merge protected-ref proposals."),
        ("charon-maintainer", "skills/charon-maintainer/SKILL.md",
         "Operate a local Charon + Lethe Memory Git deployment end to end."),
    ],
    "matapan": [
        ("matapan", "skills/matapan/SKILL.md",
         "Work inside a Matapan workspace: scoped edits, hardened runs, seal a proposal, hand off."),
    ],
}
REPO_DIRS = {"lethe": "lethe", "charon": "charon", "matapan": "matapan"}

EXTRA = """
.skillgrp{margin-top:36px}
.skillgrp h2{margin-top:0;border-top:none;padding-top:0}
.skgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:2px;background:var(--line);border:1px solid var(--line);margin-top:16px}
a.sk{display:block;background:var(--bg);padding:20px 22px;text-decoration:none;color:var(--ink)}
a.sk:hover{background:var(--bg2)}
a.sk .skname{font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:500}
a.sk .skp{color:var(--dim);font-size:13px;line-height:1.6;margin-top:8px;font-weight:300;display:block}
a.sk .skopen{display:inline-block;margin-top:12px;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.2em;text-transform:uppercase}
aside a .sw{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:8px}
"""


def main():
    out_dir = DOCS / "skills"
    out_dir.mkdir(parents=True, exist_ok=True)
    sections = []
    sidebar = []
    for project in PROJECT_ORDER:
        accent = THEMES[project]["accent"]
        sidebar.append(f'<div class="grp"><div class="gt">{PROJECT_TITLES[project]}</div>')
        cards = []
        for skill_id, rel_src, blurb in SKILLS[project]:
            src = ROOT.parent / REPO_DIRS[project] / rel_src
            (out_dir / project).mkdir(exist_ok=True)
            (out_dir / project / f"{skill_id}.md").write_text(src.read_text())
            sidebar.append(
                f'<a href="#{project}-{skill_id}"><span class="sw" style="background:{accent}"></span>{skill_id}</a>'
            )
            cards.append(
                f'<a class="sk" id="{project}-{skill_id}" href="{project}/{skill_id}.md" target="_blank" rel="noopener">'
                f'<span class="skname" style="color:{accent}">{skill_id}</span>'
                f'<span class="skp">{html.escape(blurb)}</span>'
                f'<span class="skopen" style="color:{accent}">Open raw SKILL.md &nearr;</span>'
                f'</a>'
            )
        sections.append(
            f'<div class="skillgrp"><h2 style="color:{accent}">{PROJECT_TITLES[project]}</h2>'
            f'<div class="skgrid">{"".join(cards)}</div></div>'
        )
        sidebar.append("</div>")
    sidebar_html = (
        '<div class="grp"><div class="gt">Projects</div>'
        '<a href="../index.html">Lethe docs</a>'
        '<a href="../charon/index.html">Charon docs</a>'
        '<a href="../matapan/index.html">Matapan docs</a></div>'
        + "\n".join(sidebar)
    )
    body = f"""
<h1>Skills.</h1>
<p style="max-width:640px">Agent-facing skills for the openlethe projects — drop-in <code>SKILL.md</code> files that teach an agent how to use each product. Every skill follows the same structure: frontmatter (name, description, metadata), then the workflow, rules, and recovery playbook. Each opens as raw markdown in a new tab.</p>
{''.join(sections)}
"""
    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skills — openlethe</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;1,400&family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{style_for("lethe")}{EXTRA}</style>
</head>
<body>
<nav class="top">
  <a class="logo" href="../../index.html">Lethe<i>.</i></a>
  <div class="navlinks">
    <a href="../../index.html">Lethe</a>
    <a href="../../charon.html">Charon</a>
    <a href="../../matapan.html">Matapan</a>
    <a href="../../docs.html">Docs</a>
    <a href="index.html" class="here">Skills</a>
    <a href="https://github.com/openlethe">GitHub</a>
  </div>
</nav>
<div class="wiki">
<aside>
{sidebar_html}
</aside>
<main>
<div class="kick">openlethe · skills</div>
{body}
</main>
</div>
<footer>
  <div class="fl">Lethe<i>.</i></div>
  <div>
    <a href="https://github.com/openlethe" style="margin-left:0">GitHub</a>
    <a href="../../index.html">Lethe</a>
    <a href="../../charon.html">Charon</a>
    <a href="../../matapan.html">Matapan</a>
  </div>
  <div class="fc">openlethe.com · 2026</div>
</footer>
</body>
</html>
"""
    (out_dir / "index.html").write_text(page_html)
    total = sum(len(v) for v in SKILLS.values())
    print(f"[skills] copied {total} raw skill files + index -> docs/skills")


if __name__ == "__main__":
    main()
