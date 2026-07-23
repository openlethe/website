# Docker isolation: guarantees and limitations

Sprint 8. What Matapan's hardened Docker profile actually guarantees — and
what it does not. This document is the honest reference; the threat model
summarizes it.

## What the hardened profile guarantees (per `workspace_run`)

Enforced by `internal/runtime` (ValidateSpec + container config):

- **Non-root**: the container user is the daemon-resolved runtime identity
  (see the ownership model below); root users (including numeric aliases)
  are refused at spec validation.
- **No capabilities**: `CapDrop: ALL`.
- **No privilege escalation**: `no-new-privileges` security option; Docker's
  default seccomp profile (not custom, not unconfined).
- **Read-only root filesystem**; only `/tmp` is a small noexec/nosuid tmpfs
  and `/workspace` is the bind-mounted workspace.
- **Resource limits**: memory, CPU, and PID limits with hard clamps
  (constants: ≤ 10 min, ≤ 4 GiB, ≤ 4 MiB output).
- **Network denied by default**: `NetworkMode: none` unless a human granted
  egress.
- **No Docker socket, ever**: any spec mounting a `docker.sock` path is
  refused; privileged mode and host PID/IPC namespaces are refused.
- **Digest-pinned images**, verified after every pull; provenance recorded.
- **No ambient host env**: container env is an explicit allowlist (granted
  secrets + proxy vars only).
- **Bounded evidence**: exit code, OOM-kill flag, reason, capped output
  with truncation markers.
- **Lifecycle**: containers are named and labeled; destroy and
  reconciliation kill them; cleanup is verified by re-listing.

## What it does NOT guarantee

- **Kernel isolation.** Containers share the host kernel. A kernel exploit
  or a container-runtime (runc) escape breaks the boundary. This is
  *hardened container isolation*, not a VM. Upgrade path: gVisor
  (`runtime.isolation: gvisor`, experimental, fails hard without runsc) or
  Kata/microVM profiles (future).
- **userns-remap.** Docker userns-remap is NOT assumed; the container uid
  maps to the same host uid. That is exactly why the ownership model
  below exists: the container user must MATCH the owner of workspace
  content, or native Linux bind mounts refuse every read and write.

## Workspace ownership model (B-01)

Native Linux bind mounts preserve host ownership and mode bits. The
workspace tree is `0750`/`0640`, so a container running as a uid that
does not own it cannot list, read, or write it (Docker Desktop's
ownership translation masks this entirely — it is NOT a safe test of the
behavior). Matapan resolves one runtime identity per daemon and makes
ownership match it:

- **Daemon non-root** (native Linux dev): containers run as the daemon's
  own uid:gid. The daemon owns every workspace it creates, so no chown is
  needed (or possible). `runtime.uid`/`runtime.gid` are ignored.
- **Daemon root** (the Docker container deployment): containers run as
  the configured `runtime.uid`/`runtime.gid` (env
  `MATAPAN_RUNTIME_UID`/`MATAPAN_RUNTIME_GID`, default `65534:65534`),
  and the daemon CHOWNS workspace content to that identity at every
  moment it writes: workspace create (git/fresh/snapshot), MCP file edit
  (file + new parent dirs), `workspace_commit`, and proposal revise.
  Container-created files are born runtime-owned because the container
  runs as that uid.

Modes stay `0750`/`0640`; ownership now matches the container user, so
reads AND writes work on native Linux. **The chown excludes `.git`
entirely** (directories, their contents, and linked-worktree `.git`
pointer files): git metadata stays daemon-owned, so the runtime identity
can never write hooks or config the daemon's git would honor, and daemon
git keeps working on its own metadata. `matapan doctor` reports the
resolved identity and, in root mode, verifies the chown capability with
a real probe (a clear FAIL on rootless or read-only setups). The
`...NativeLinux` integration tests exercise this for real on the ubuntu
CI leg: read a daemon-written `0640` file, create a nested artifact, and
seal it into a proposal.
- **Docker Desktop (macOS/Windows VM) specifics.**
  - The daemon runs in a VM; bind mounts cross a filesystem translation
    layer with weaker semantics (case-insensitivity, ownership mapping).
  - Internal networks cannot reach the host gateway, so the egress proxy
    runs in **degraded mode**: HTTP(S) through the proxy is
    domain-allowlisted, but a process that ignores the proxy env has raw
    egress. Full enforcement exists on native Linux Docker (internal
    network + host-side proxy). Sidecar-proxy upgrade is planned.
- **Hardlink residual.** A file inside a workspace may share an inode with
  a file outside it (hardlinks are invisible to path checks). Mitigation:
  workspace file tools refuse files with link count > 1 (`ErrHardlink`).
  Residual: content created via *other* channels (e.g. `cp --link` inside a
  run's mounted workspace is still just files the agent made; the refusal
  covers the file-tool read/write path).
- **The Docker daemon itself is trusted.** Docker API access equals root on
  the host. Matapan never mounts the socket into workloads and never lets a
  workload reach the daemon, but the host's daemon is part of the TCB.
- **Egress proxy = HTTP(S) only.** It filters CONNECT/plain-HTTP by domain
  and port (80/443). Non-HTTP protocols are blocked at the network layer on
  Linux and are unfiltered-but-unprivileged on Docker Desktop degraded mode.
- **Denylists are advisory depth.** Profile command denylists (argv[0])
  stop casual use, not determined evasion (a copied binary renamed).
  Enforcement comes from the runtime boundary, not name matching.

## gVisor (experimental)

`runtime.isolation: gvisor` runs containers under `runsc` when the daemon
offers it (detected via `docker info` runtimes; `matapan doctor` reports).
If runsc is absent, runs fail with a typed error — never a silent fallback
to runc. gVisor adds a userspace-kernel boundary that materially raises the
cost of container escape; it is experimental in Sprint 8 and off by
default.
