# Operations

Day-to-day running of matapand and the matapan CLI.

## Daemon management

- **Start:** `matapand` (HTTP on `127.0.0.1:18777`) or `matapand --stdio`
  (MCP over stdio for a local agent, requires `MATAPAN_OBOL`).
- **Stop:** SIGTERM/SIGINT — graceful: in-flight containers are swept by
  label, then the HTTP server drains.
- **Logs:** stderr. Lifecycle transitions, reconciliation reports, GC
  collections, and errors — never command output or secret values (command
  output goes only to the authenticated caller).
- **Startup reconciliation:** every start runs a pass — stuck transitional
  states fail or resume, orphan dirs/rows are reported (or cleaned with
  `--reconcile-clean`), stale git worktree metadata is pruned, orphaned
  labeled containers and lock files are removed. All actions are ledgered.
- **Health:** `curl http://127.0.0.1:18777/api/health` (loopback only).

## Inspection and repair

- `matapan doctor` — environment: git, config, runtime user (resolved
  runtime uid:gid + root-mode chown probe), database + schema version,
  reconciliation status, obol key, Docker, runtime image (digest match),
  runtime spawn (as the resolved identity), daemon reachability, ledger
  size + retention.
- `matapan workspace diagnose <id>` — one workspace: state, source
  identity, head/dirty, dir usage, lock holder (+liveness), labeled
  containers, egress grants, manifest drift, degraded run leases,
  issues list.
- `matapan workspace rebind <id> [--yes]` — rebind a git workspace whose
  source identity is missing or changed (legacy rows, operator-moved
  repos). Prints recorded vs live identity; `--yes` records it after
  content proof (base commit must resolve). Without `--yes` it changes
  nothing.
- `matapan workspace purge-backups <id> [--yes]` — remove the retained
  snapshot recovery backup home for the workspace's source. Lists what
  will be removed and requires `--yes`; reconciliation NEVER removes
  backups automatically.
- `matapan workspace repair <id>` — preview; `--yes` to execute (mark
  stuck states failed, kill orphan containers, re-derive manifests).
  Ledgered.

## Garbage collection

- Leases: `workspace create --lease 24h` (or `7d`). Idle expiry:
  `gc.idle_hours` config (default 72).
- `matapan workspace protect <id>` exempts a workspace (`--clear` to undo).
- Sweeper: daemon startup + hourly; manual preview with `matapan gc
  --dry-run`, collect with `matapan gc`.
- **Never collected:** workspaces with sealed-but-unapplied proposals
  (marked stale instead) and protected workspaces. Collection always uses
  the verified destroy path and is ledgered.
- Audit retention: `ledger.retention_days` (90) and `ledger.max_entries`
  (1e6), swept at startup + daily with compaction anchors so the retained
  hash chain still verifies.

## Backup and upgrade

- **State:** everything lives in `~/.matapan/` — `matapan.db` (SQLite,
  WAL), `obol.key`, `secret.key`, `config.json`, `workspaces/`.
- **Backup:** stop the daemon (or use `sqlite3 matapan.db ".backup
  backup.db"`), then copy the directory. Keys are irreplaceable — losing
  `obol.key` invalidates all obols; losing `secret.key` loses all secrets.
  `obol.key` also authenticates sealed-proposal anchors (round 6): losing
  it makes every sealed proposal unapplyable (re-seal to recover).
- **Upgrade:** install the new binaries over the old. The DB migrates
  forward automatically and idempotently at open (v1→current verified in
  tests). Downgrades are not supported. Notes for the v14+ upgrade:
  pre-existing workspaces are conservatively marked `ever_ran` (Docker
  required for their destroys), and proposals sealed before the v2 seal
  anchor must be re-sealed before they can apply.
- **Version:** `matapan version`, `matapand --version`.

## Failure modes

- **Daemon dies mid-operation:** restart — reconciliation fails or resumes
  the operation. Destroy operations resume to completion.
- **Docker unavailable:** the daemon runs normally; `workspace_run` returns
  typed `unavailable`. Reads and edits work. Destroys are different
  (round 5/6): without container visibility, destroy REFUSES any
  workspace that has ever run (durable `ever_ran` evidence,
  `ErrContainerKillUnavailable`) — never-run workspaces (e.g.
  create-rollback) still clean up. Retry destroys from a process with
  Docker access.
- **Daemon startup aborts on sweep errors:** if the startup lease sweep
  cannot read or write the store (e.g. a failed degradation write), the
  daemon logs FATAL and refuses to serve — a store that cannot record
  safety state is never run around.
- **Sealed proposals are ledger-anchored (round 5/6):** apply requires
  the proposal's HMAC-authenticated seal anchor. Proposals sealed before
  the anchor existed fail closed (`ErrSealedEvidenceMissing`) — `proposal
  revise` + re-seal to apply them.
- **Stale base on apply:** the target moved — `proposal revise <id>` seeds
  a fresh workspace from the proposal and re-seals.

## Container deployment

matapand ships as an image (`scripts/docker-build.sh matapan:local`). One
container per agent model, each with its own config, database, keys, and
workspace root.

### The three path-parity requirements

1. **Workspace root.** matapand bind-mounts a workspace's directory into
   run containers by its absolute path. The workspace root mount inside
   the matapand container MUST be the *same absolute path* as the host
   path (e.g. `-v /data/ws-chatgpt:/data/ws-chatgpt`). Otherwise nested
   run containers get a path that does not exist on the host.
2. **Source repos.** Git workspaces are linked worktrees of host repos:
   `git worktree add` writes administrative pointers containing absolute
   paths. Source roots must be mounted at *identical* absolute paths
   inside and outside (e.g. `-v /Users/me/dev:/Users/me/dev`).
3. **docker.sock.** matapand needs `/var/run/docker.sock` to run agent
   workloads — mount it into the matapand container ONLY. Agent run
   containers are refused any docker.sock mount by spec validation. The
   socket is full root on the host: matapand is trusted control-plane
   code; treat its host access accordingly.

### Config and secrets provisioning

Mount the model's config JSON at `/etc/matapan/config.json` (the image's
default `--config`). Bootstrap keys and the admin obol once per model:

```sh
docker compose run --rm --no-deps --entrypoint matapan matapan-chatgpt \
  config init --home /data
```

(The image's entrypoint is `matapand`, so `--entrypoint matapan` is
required to run the CLI. `/data` is the per-model volume; config init
writes config.json, obol.key, secret.key, and the db, then prints the
admin obol ONCE. Point `--config` at `/data/config.json` afterwards, or
mount that file at `/etc/matapan/config.json`.) Override any setting
per-instance with the `MATAPAN_*` env vars — env > file > defaults.

### User model

The image runs as root (see the Dockerfile comment): the docker group gid
varies by host and Docker Desktop manages socket access differently, so a
fixed non-root uid cannot open the socket out-of-the-box. On a rootless
or group-managed host you can instead run:

```sh
docker run --user "$(id -u):$(getent group docker | cut -d: -f3)" \
  -v "$XDG_RUNTIME_DIR/docker.sock:/var/run/docker.sock" ...
```

### Runtime user and workspace ownership (B-01)

Native Linux bind mounts preserve host ownership, so the container user
must MATCH the owner of workspace content (`0750`/`0640`). The daemon
resolves one runtime identity at startup:

- **Daemon non-root** (native Linux dev): containers run as the daemon's
  own uid:gid; workspace content is already owned by it. No chown.
- **Daemon root** (this container deployment): containers run as
  `runtime.uid`:`runtime.gid` (env `MATAPAN_RUNTIME_UID` /
  `MATAPAN_RUNTIME_GID`, default `65534:65534`), and the daemon chowns
  workspace content to that identity at every write moment (create, MCP
  edit, commit, revise). Container-created files are born runtime-owned.

`matapan doctor` reports the resolved identity under `runtime user` and,
in root mode, fails loudly if the chown probe fails (rootless daemon,
read-only fs). Modes never change — only ownership.

### Compose layout

See the per-model deployment folder (two services: one per model). Each
service mounts its config, its data dir, its workspace dir at the
identical absolute path, the docker socket, and the host dev tree at its
identical absolute path; ports are published on 127.0.0.1 only.

## OAuth authorization-server mode

`auth.mode: oauth` turns the instance into an OAuth 2.0 authorization
server for connectors that require OAuth (ChatGPT, Claude).

Config (`auth` section):

| Field | Meaning |
|---|---|
| `oauth_issuer` | Public base URL (REQUIRED, https — the tunnel hostname). Metadata endpoints and JWT `iss` derive from it. |
| `oauth_redirects` | Redirect-URI allowlist (REQUIRED). Must cover ChatGPT's and Claude's callbacks. |
| `oauth_client_id` | Public client_id (default `chatgpt-mcp`; printable ASCII, no spaces; override via `MATAPAN_OAUTH_CLIENT_ID`). |
| `oauth_principal` | Principal tokens map to (default `agent-<oauth_client_id>`; must exist and stay within the agent scope set at startup). |
| `oauth_allow_admin` | Escape hatch: permit `oauth_principal` to name an admin-capable principal (default false — refused). Suspends the connector authority boundary; operator use only. |
| `oauth_owner_password_hash` | SHA-256 hex of the approval-gate password. Prefer the env var. |

Owner password: set `MATAPAN_OAUTH_OWNER_PASSWORD` in the daemon's
environment (compose: `.env`). It is hashed in memory at startup and never
stored; the daemon REFUSES to start in oauth mode without it (or the
config hash). The approval form cannot be bypassed — every authorization
code is issued only after the owner types it.

Flow: connector discovers `/.well-known/oauth-protected-resource` →
`/oauth/authorize` renders the approval form (exact effective scopes +
token principal shown) → owner password → code → `/oauth/token` (PKCE) →
24h HS256 JWT. `/mcp` accepts both JWTs and obols. No refresh tokens;
connectors re-authorize daily. Per-client and global rate limits cover
`/oauth/token` and the approval POST.

Token authority: tokens map to `agent-<oauth_client_id>` (auto-provisioned
with AgentScopes — no `workspace.grant`, no `proposal.apply`), NOT admin.
The connector can't grant egress/secrets and can't apply proposals; apply
is human-only (CLI or a proposal.apply-scoped principal). Grant workspaces
to the connector at create: oauth mode auto-grants `agent-<client_id>`;
add more with `matapan workspace create --grant <principal>` (repeatable).
Self-approval prevention defaults ON in oauth and charon modes.

Per-model setup: `docker compose run --rm --no-deps matapan-chatgpt \
matapan config oauth-setup --config /data/config.json` prints the exact
connector instructions.
