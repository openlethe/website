# Quickstart

From zero, on macOS or Linux. Requires git, Go 1.25.12+ (to build from
source), and a local Docker daemon for `workspace_run`.

## 1. Install and verify

```sh
# Install (builds and installs to /usr/local/bin, or --user for ~/.local/bin)
scripts/install.sh

# Verify the environment
matapan doctor
# git                    ok   git version 2.50.1
# config                 ok   ~/.matapan/config.json
# database               ok   ~/.matapan/matapan.db (schema current)
# obol key               ok   ~/.matapan/obol.key (perms 600)
# docker                 ok   daemon reachable
# runtime image          ok   present, digest matches
# runtime spawn          ok   hardened container ran, exit 0

# Pre-pull the digest-pinned runtime image
matapan runtime pull
```

## 2. Create a workspace

```sh
# From a git repo — a linked worktree at an exact commit
matapan workspace create --repo ~/src/my-app --base main
# {"ID": "019f…", "State": "ready", "Branch": "matapan/019f…", …}
```

Other source types: `--source snapshot --path /dir` (defended copy of a
non-Git directory), `--source fresh [--git-init]` (empty scaffold).
Useful flags: `--profile restricted` (policy profile), `--lease 24h`
(GC expiry), `--egress proxy.example.com` (human egress grant).

## 3. Start the daemon and connect an agent

```sh
matapand &   # HTTP on 127.0.0.1:18777
```

- **Claude Code / local agents (stdio):** `matapand --stdio` with
  `MATAPAN_OBOL` set. Mint one with `matapan config obol` — use it as a
  bearer token for `/mcp`, or export it as `MATAPAN_OBOL` for stdio mode.
- **ChatGPT / remote connectors (HTTPS):** put a user-managed tunnel
  (cloudflared, tailscale funnel) in front of the loopback listener and
  complete the OAuth flow — see
  [Docker Compose Setup](docker-compose.html) for the full deployment.

The agent then drives `workspace_file_edit` / `workspace_run` /
`workspace_commit` against the workspace ID.

## 4. Seal, review, apply

```sh
# The agent seals the workspace into an immutable proposal. Review it:
matapan proposal list
matapan proposal show <id>            # diff, digests, evidence, lineage

# Apply with compare-and-swap against the expected base:
matapan proposal apply <id> --expected-base <commit>
# {"ProposalID": "019f…", "AppliedHead": "7f84…", "Strategy": "auto",
#  "Rollback": "git -C ~/src/my-app reset --hard <commit>"}
```

Apply verifies the sealed content digest, the HMAC-authenticated target
anchor, and the source identity before anything moves. A stale base is a
typed error — `matapan proposal revise <id>` seeds a fresh workspace from
the proposal and re-seals.

## 5. Housekeeping

```sh
matapan workspace destroy <id>        # verified teardown
matapan gc --dry-run                  # what idle/expired GC would collect
matapan workspace diagnose <id>       # one workspace, full detail
```

Destroy requires verified container absence: labeled containers are
killed and re-listed before anything is deleted, and a process without
Docker visibility refuses workspaces that have ever run.
