# Docker Compose Setup

The reference container deployment: **one matapand container per agent
model**, each with its own config, database, keys, and workspace root,
fronted by a single host-managed HTTPS tunnel. This page is the complete
end-to-end guide — topology, the full compose file, per-model config,
and the environment variable reference.

## Topology

```
ChatGPT connector ─┐                         ┌─ matapan-chatgpt ── /data (db, keys, workspaces)
                   │  HTTPS tunnel            │   127.0.0.1:18777
Claude connector ──┤── cloudflared (host) ────┤
                   │  one tunnel, two hosts   │   127.0.0.1:18778
                   │                         └─ matapan-claude  ── /data (db, keys, workspaces)
                   │
                   └─ both containers share the HOST docker.sock to spawn
                      agent run containers (never mounted into run containers)
```

- The tunnel runs on the **host** (`cloudflared`, or `tailscale funnel`),
  not in the compose project. One tunnel fronts both instances:
  `matapan.example.com → localhost:18777`,
  `claude.example.com → localhost:18778`.
- The `127.0.0.1` port publishes are both the tunnel path and the local
  CLI/debug path. `/api/health` answers loopback peers only (host curls
  through the Docker proxy get `403` by design; the tunnel fronts the
  authenticated MCP surface).
- Each model gets an isolated identity: own database, own `obol.key` /
  `secret.key` (both 0600), own workspace root. Nothing is shared between
  instances except the host Docker daemon.

## The three path-parity requirements

1. **Workspace root.** matapand bind-mounts a workspace's directory into
   run containers by absolute path. The workspace-root mount inside the
   matapand container MUST be the *same absolute path* as the host path
   (`./data/<model>/workspaces` is mounted at its full host absolute
   path). Otherwise nested run containers get a path that does not exist
   on the host.
2. **Source repos.** Git workspaces are linked worktrees of host repos:
   `git worktree add` writes administrative pointers containing absolute
   paths. Source trees are mounted at *identical* absolute paths inside
   and outside.
3. **docker.sock.** Mounted into the matapand containers ONLY. Agent run
   containers are refused any docker.sock mount by spec validation. The
   socket is full root on the host: matapand is trusted control-plane
   code — treat its host access accordingly.

## docker-compose.yml

```yaml
# Matapan per-model matapand instances.
# Path parity: ./data/<model>/workspaces is mounted at the HOST absolute
# path; the dev tree is mounted read-write at the identical path so git
# worktree sources resolve; docker.sock goes into matapand containers only.

services:
  matapan-chatgpt:
    build:
      context: /path/to/matapan          # the matapan repository
      dockerfile: Dockerfile
      args:
        VERSION: compose-dev
    image: matapan:compose
    container_name: matapan-chatgpt
    restart: unless-stopped
    environment:
      MATAPAN_OAUTH_OWNER_PASSWORD: ${MATAPAN_OAUTH_OWNER_PASSWORD:?set MATAPAN_OAUTH_OWNER_PASSWORD in .env}
      MATAPAN_OAUTH_ISSUER: ${MATAPAN_OAUTH_ISSUER_CHATGPT:?set MATAPAN_OAUTH_ISSUER_CHATGPT in .env}
    ports:
      - "127.0.0.1:18777:18777"
    volumes:
      - ./chatgpt.yaml:/etc/matapan/config.json:ro
      - ./data/chatgpt:/data
      - ./data/chatgpt/workspaces:/abs/host/path/to/data/chatgpt/workspaces
      - /abs/host/path/to/workspace:/abs/host/path/to/workspace
      - /var/run/docker.sock:/var/run/docker.sock
    healthcheck:
      test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/18777 && printf 'GET /api/health HTTP/1.0\r\n\r\n' >&3 && grep -q '\"ok\"' <&3"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

  matapan-claude:
    build:
      context: /path/to/matapan
      dockerfile: Dockerfile
      args:
        VERSION: compose-dev
    image: matapan:compose
    container_name: matapan-claude
    restart: unless-stopped
    environment:
      MATAPAN_OAUTH_OWNER_PASSWORD: ${MATAPAN_OAUTH_OWNER_PASSWORD:?set MATAPAN_OAUTH_OWNER_PASSWORD in .env}
      MATAPAN_OAUTH_ISSUER: ${MATAPAN_OAUTH_ISSUER_CLAUDE:?set MATAPAN_OAUTH_ISSUER_CLAUDE in .env}
    ports:
      - "127.0.0.1:18778:18778"
    volumes:
      - ./claude.yaml:/etc/matapan/config.json:ro
      - ./data/claude:/data
      - ./data/claude/workspaces:/abs/host/path/to/data/claude/workspaces
      - /abs/host/path/to/workspace:/abs/host/path/to/workspace
      - /var/run/docker.sock:/var/run/docker.sock
    healthcheck:
      test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/18778 && printf 'GET /api/health HTTP/1.0\r\n\r\n' >&3 && grep -q '\"ok\"' <&3"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

> The image runs as root: the docker group gid varies by host and Docker
> Desktop manages socket access differently, so a fixed non-root uid
> cannot open the socket out-of-the-box. On a rootless or group-managed
> host, run with `--user "$(id -u):$(getent group docker | cut -d: -f3)"`
> and the user-namespace socket instead.

## Per-model config (`<model>.yaml`)

Each instance mounts one JSON config at `/etc/matapan/config.json` (the
image's default `--config`). The two files differ only in listen port,
tool profile, and OAuth redirects:

```json
{
  "listen_addr": "0.0.0.0:18778",
  "allow_lan": true,
  "db_path": "/data/matapan.db",
  "workspace_root": "/abs/host/path/to/data/claude/workspaces",
  "docker_image": "alpine@sha256:<digest>",
  "obol_key_path": "/data/obol.key",
  "secret_key_path": "/data/secret.key",
  "runtime": {
    "timeout_sec": 300, "memory_mb": 512, "pids_limit": 256,
    "nano_cpus": 2000000000, "max_output_bytes": 1048576,
    "isolation": "docker"
  },
  "mcp": { "tool_profile": "full" },
  "ledger": { "retention_days": 90, "max_entries": 1000000 },
  "auth": {
    "mode": "oauth",
    "oauth_issuer": "https://claude.example.com",
    "oauth_redirects": [
      "https://claude.ai/api/mcp/auth_callback",
      "https://chatgpt.com/connector/oauth/*"
    ],
    "oauth_principal": "admin",
    "oauth_allow_admin": true
  },
  "gc": { "idle_hours": 72 }
}
```

Notes:

- `workspace_root` must equal the host absolute path (path parity rule 1).
- `listen_addr` binds `0.0.0.0` **inside** the container so the published
  port works; `allow_lan: true` permits the non-loopback bind. Everything
  except `/api/health` still requires authentication.
- `oauth_principal: "admin"` with `oauth_allow_admin: true` is an
  explicit operator opt-in: the connector principal carries admin scopes
  (including `proposal.apply`). For a least-privilege connector, omit
  both — the daemon auto-provisions `agent-<client_id>` with agent scopes
  and no workspace grants, and you grant workspaces to it explicitly.
- The runtime image is digest-pinned; `matapan runtime pull` fetches it.

## First boot: keys and admin obol

Bootstrap keys and the admin obol once per model (the image entrypoint
is `matapand`, so override it to run the CLI):

```sh
docker compose run --rm --no-deps --entrypoint matapan matapan-chatgpt \
  config init --home /data
```

This writes `config.json`, `obol.key`, `secret.key`, and the database
into `/data` and prints the admin obol **once** — store it somewhere
safe. Afterwards point `--config` at `/data/config.json` or keep the
mounted `<model>.yaml`.

Then:

```sh
docker compose up -d          # build + start both instances
docker compose ps             # both healthy
docker logs matapan-claude    # "listening on 0.0.0.0:18778 (mcp at /mcp …)"
```

## Tunnel

cloudflared runs on the host. `~/.cloudflared/config.yml`:

```yaml
tunnel: <your-tunnel-id>
credentials-file: /path/to/<id>.json
ingress:
  - hostname: matapan.example.com
    service: http://localhost:18777
  - hostname: claude.example.com
    service: http://localhost:18778
  - service: http_status:404
```

Point each connector at `https://<host>/mcp` and complete the OAuth flow
— the authorize page demands the owner password from
`MATAPAN_OAUTH_OWNER_PASSWORD`.

## Environment variables

Precedence is **env > config file > defaults**. The compose file passes
secrets/hosts through `environment:`; everything else lives in the
per-model config file.

### Required in `.env` (compose fails fast without them)

| Variable | Used by | Purpose |
|---|---|---|
| `MATAPAN_OAUTH_OWNER_PASSWORD` | both instances | Owner password demanded by the OAuth authorize gate. Never stored in the config file. |
| `MATAPAN_OAUTH_ISSUER_CHATGPT` | `matapan-chatgpt` | Public tunnel URL of the ChatGPT instance, e.g. `https://matapan.example.com`. JWT issuer claim. |
| `MATAPAN_OAUTH_ISSUER_CLAUDE` | `matapan-claude` | Public tunnel URL of the Claude instance, e.g. `https://claude.example.com`. |

### Agent credentials

| Variable | Purpose |
|---|---|
| `MATAPAN_OBOL` | Bearer token for `matapand --stdio` (local agent MCP over stdio). Mint with `matapan config obol`. |

### Config-file overrides (all optional)

| Variable | Overrides | Purpose |
|---|---|---|
| `MATAPAN_LISTEN_ADDR` | `listen_addr` | HTTP bind address (default `127.0.0.1:18777`). |
| `MATAPAN_ALLOW_LAN` | `allow_lan` | Permit non-loopback bind. Auth still required everywhere except `/api/health`. |
| `MATAPAN_DB_PATH` | `db_path` | SQLite database path. |
| `MATAPAN_WORKSPACE_ROOT` | `workspace_root` | Workspace root — must keep host path parity in containers. |
| `MATAPAN_DOCKER_IMAGE` | `docker_image` | Digest-pinned runtime image for agent runs. |
| `MATAPAN_OBOL_KEY_PATH` | `obol_key_path` | 0600 HMAC key file — signs obols, OAuth JWTs, and sealed-proposal anchors. |
| `MATAPAN_SECRET_KEY_PATH` | `secret_key_path` | 0600 AES-256-GCM key for the secrets broker. |
| `MATAPAN_AUTH_MODE` | `auth.mode` | `oauth` (default), `charon`, or local obol. |
| `MATAPAN_CHARON_URL` | `auth.charon_url` | Charon validate endpoint when `auth.mode: charon`. |
| `MATAPAN_OAUTH_ISSUER` | `auth.oauth_issuer` | JWT issuer (usually passed per-instance via `.env`). |
| `MATAPAN_OAUTH_CLIENT_ID` | `auth.oauth_client_id` | Public PKCE client id (default `chatgpt-mcp`). |
| `MATAPAN_OAUTH_REDIRECTS` | `auth.oauth_redirects` | Comma-separated allowed redirect URIs. |
| `MATAPAN_TOOL_PROFILE` | `mcp.tool_profile` | `minimal` (core 12 tools) or `full` (+ typed glob/grep). |
| `MATAPAN_RUNTIME_UID` / `MATAPAN_RUNTIME_GID` | `runtime.uid/gid` | Identity agent run containers execute as. |
| `MATAPAN_RUNTIME_ISOLATION` | `runtime.isolation` | `docker` (default) or `gvisor` (requires runsc; fails hard without it). |
| `MATAPAN_GC_IDLE_HOURS` | `gc.idle_hours` | Idle expiry for GC (default 72). |
| `MATAPAN_LEDGER_RETENTION_DAYS` | `ledger.retention_days` | Audit retention (default 90). |
| `MATAPAN_LEDGER_MAX_ENTRIES` | `ledger.max_entries` | Audit entry cap (default 1,000,000). |

## Operate

```sh
docker compose build                # rebuild after pulling new code
docker compose up -d                # recreate changed instances
docker compose logs -f matapan-chatgpt
docker compose exec matapan-chatgpt matapan --config /data/config.json doctor
```

On upgrade, the database migrates forward automatically and idempotently
at open. Pre-v14 workspaces are conservatively marked `ever_ran` (their
destroys require Docker visibility), and proposals sealed before the v2
seal anchor must be re-sealed before they can apply — see
[Operations](operations.html).
