# DevSpace vs Matapan — the same task through both tools

A documented walkthrough from the original product plan: the same small
task — "update the README badge URL in this repo" — driven through DevSpace
and through Matapan, step by step, with the trust-model deltas at each one.

## The task

Repo: a small web app on `main`. Task: change one URL in `README.md`, run
the link check, hand the change back for review.

## Through DevSpace

1. **Open.** `devspace` opens a worktree (or the checkout) for the agent.
   The agent gets opaque `workspace_id`-scoped tools. AGENTS.md/CLAUDE.md
   load at open — nice ergonomics.
2. **Edit.** Agent calls `write`/`edit` on the file. The change lands in
   the worktree. If checkout mode is on, **the user's real files are
   already modified** — there is no review gate between the agent's write
   and the user's code.
3. **Run.** Agent runs the link check via `bash` — **as the local user,
   uncontained**. The command has full host env, network, and credentials.
   DevSpace's own docs: worktrees are "not a security boundary".
4. **Return.** The diff is shown in the chat. The user reviews after the
   fact — the write path already touched the checkout, and the command
   already ran with ambient authority. There is no proposal object, no
   stale-base concept, no evidence record.

## Through Matapan

1. **Open.** `matapan workspace create --repo . --base main` — a linked
   worktree at an exact commit. The user's checkout is untouched and stays
   outside the agent's write path.
2. **Edit.** Agent calls `workspace_file_edit` — guard chain:
   authenticate → scope check → workspace grant → canonical path defense
   (symlink/`..` rejected) → ledger entry. The change lands only in the
   workspace.
3. **Run.** `workspace_run` executes argv in a hardened container:
   non-root, cap-drop ALL, no-new-privileges, read-only rootfs, memory/CPU/
   PID limits, network **none** unless a human granted egress — no ambient
   host env. Exit code, OOM flag, bounded output come back as evidence.
4. **Return.** The agent (or human) seals `proposal_create`: immutable
   diff, base/head commits, content digest, instruction + image + policy
   digests, parsed test evidence. The user reviews the sealed artifact,
   then `proposal apply <id> --expected-base <commit>` — compare-and-swap
   against the expected base. Target moved? Typed `stale_base`, nothing
   changes; revise instead. Rollback hint included.
5. **Aftermath.** `workspace destroy` is verified (dir gone, worktree list
   clean, containers dead). The hash-chained ledger holds the whole story,
   redacted.

## Trust-model deltas

| Step | DevSpace | Matapan |
|---|---|---|
| Where the write lands | checkout or worktree, user-visible immediately | workspace only, never the checkout |
| Command execution | local user, uncontained | hardened container, deny-net default |
| Review gate | conversational diff | immutable sealed proposal, CAS apply |
| Stale base | n/a | typed rejection + revise workflow |
| Secrets/env | ambient | explicit human grants, injected, revoked at seal |
| Teardown | manual | verified destroy + GC + reconciliation |
| Audit | session log | hash-chained, redacted, verifiable |

## Where DevSpace is genuinely better (and what Matapan adopted)

- Onboarding ergonomics: root AGENTS.md/CLAUDE.md loading, tool cards,
  `doctor`. Matapan adopts the instruction manifest (with digests sealed
  into proposals), tool profiles (minimal/full), capability discovery, and
  the doctor/diagnose/repair split.
- The single-obol tunnel path for ChatGPT. Matapan ships the same interim
  posture (user-managed tunnel + bearer) with a fixed audience for the
  Charon OAuth seam.

The short version: DevSpace optimizes agent ergonomics with a local-trust
model; Matapan keeps the ergonomics that matter and moves every
authority-bearing step behind a boundary.
