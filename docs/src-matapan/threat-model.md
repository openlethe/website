# Matapan Threat Model

Sprint 1, **reviewed at Sprint 8** (see the review section at the end).
This document defines what Matapan protects, from whom, and how —
and what it explicitly does not claim.

## Assets

1. **The user's source code** — the active checkout and its branches.
2. **Host integrity** — the machine matapand runs on: filesystem, other
   processes, credentials in the environment, the Docker daemon.
3. **Secrets** — obol tokens, the HMAC signing key, any future granted
   secrets.
4. **Audit integrity** — the ledger must faithfully record what happened.
5. **Proposal integrity** — a proposal must be immutable once sealed, and an
   apply must land exactly the reviewed content on exactly the expected base.

## Trust boundaries

```
user's checkout ──(git, human-only writes)── matapand ──(MCP, obol-auth)── agents
                       │                        │
                  git worktrees            Docker hardened container
                  (collision-avoidance     (isolation boundary)
                   only, NOT a boundary)        │
                                          network: denied by default
```

- **Worktrees are collision-avoidance, not a security boundary.** Isolation
  comes from the container runtime, never from directory separation.
- **The MCP listener** is a boundary: everything except `/api/health`
  (loopback-only) requires a valid obol of audience `matapan`.
- **The Docker daemon** is trusted infrastructure; the workload inside the
  container is not.

## Attacker model

1. **Malicious agent output.** A compromised or prompt-injected agent issues
   tool calls designed to escape the workspace, read host files, exfiltrate
   data, or alter the user's checkout directly.
2. **Malicious repository content.** Checked-in files (hooks, `.gitconfig`
   includes, binaries, symlinks) weaponize the tools the agent or Matapan
   runs against them.
3. **Prompt injection via instruction files.** `AGENTS.md`/`CLAUDE.md` and
   nested instructions in the source are untrusted input. **Source
   instructions must never loosen policy**: they cannot widen scopes, grant
   egress, mount paths, or alter the runtime profile. They inform the agent;
   they configure nothing.
4. **Stale-base / race attackers** (including accident-as-adversary): the
   target branch moves between review and apply.
5. **Token theft and replay.** A leaked obol is used from an unexpected
   context; a request is replayed.

Explicitly out of scope for Sprint 1: a fully malicious host (the daemon
runs as the user and trusts the local git, Docker, and OS), kernel/container
escape zero-days (mitigation path: gVisor/Kata/microVM profiles, post-MVP),
and multi-user adversaries (single-user MVP; Charon adapter later).

## Mitigations, mapped to mechanisms

| Threat | Mechanism |
|---|---|
| Agent writes user's checkout | Checkout is never in the agent write path; agents only reach worktrees via workspace-scoped tools. The only mutation of user code is the human's explicit `proposal_apply`, which fast-forwards ref+checkout after CAS. |
| Path escape via `..`/symlinks | Every file tool call re-canonicalizes with `filepath.EvalSymlinks`, rejects `..` and symlink components pointing outside the workspace root. TOCTOU is closed by construction on both directions (B-02): **writes** install via descriptor-pinned atomic rename (temp file + `renameat` relative to the pinned parent dirfd, parent identity re-verified after install); **reads** open through a descriptor-pinned walk — every component opened relative to the parent dirfd with `O_NOFOLLOW`, final component `O_RDONLY|O_NOFOLLOW`, opened inode identity (dev+ino) compared against what resolution observed, so a symlink raced in after resolve fails the open instead of redirecting it outside. The same pinned read covers `OpenFile` (file read/search/grep, instruction loading, proposal staging/revision), snapshot import's source opens, and manifest hashing. Residual: Windows has no dev+inode identity — read paths skip the identity comparison (containment stays lexical via the canonical contract; the race window is a documented degraded-platform residual). Snapshot import stays fail-closed there (its stricter source-identity contract is unchanged). |
| Malicious argv / shell injection | No shell anywhere: `os/exec` argv arrays only, in Matapan and in the container spec. |
| Container breakout attempt | Non-root user (the daemon-resolved runtime identity: the daemon's own uid:gid when non-root, or the configured `runtime.uid`/`gid` — default nobody — with workspace content chowned to match, B-01), `CapDrop: ALL`, no-new-privileges, default seccomp, read-only rootfs, tmpfs `/tmp` (noexec/nosuid), memory/CPU/PID limits with hard clamps (constants, not config), digest-pinned images **verified after every pull** (the daemon must report the exact requested repo digest, else a typed mismatch error), named+labeled containers, verified cleanup (kill+remove is re-listed, residuals block destroy). Spec refuses privileged, host PID/IPC, root users (incl. numeric aliases), mounts outside the workspace, and any docker.sock mount — fail-closed in `ValidateSpec`. |
| Silent failures as evidence | Post-run inspect records exit code and the **OOM-killed flag** — a silently OOMed test run can never look like a pass. Termination reason distinguishes spec timeout from caller cancellation. Output is bounded with explicit truncation flags and markers; live streaming sinks are bounded too. |
| Data exfiltration | `NetworkMode: none` by default; egress requires an explicit per-call grant. No ambient host env, SSH agent, or credentials enter the container — env is an explicit allowlist. |
| Secret leakage into audit | The ledger redacts registered secret values and obol-shaped tokens before persistence (`ledger.Redact`). `secret_grants` stores metadata only — never values. |
| Stale base / TOCTOU on apply | CAS: target head must equal proposal base **and** caller's `expected_base`; merge validated in a temp worktree; ref moved by atomic `update-ref <new> <old>` (or a fail-safe `--ff-only` in the checked-out case). Typed `StaleBaseError` carries the current head. Conflicts (cherry-pick / 3-way patch) **abort cleanly — the abort itself is verified**: target head unchanged, `git status --porcelain` empty, no partial files. The proposal goes to state `conflict` with the file list; the fix path is `proposal revise`, never silent resolution. Post-apply verification re-reads the target head; rollback hints are recorded at apply time. **Content verification (B-07):** a git proposal's `ContentDigest` is computed from git's own tree model (`git ls-tree -r -l` of the sealed head) — tracked file blobs with git's filemode, tracked symlinks as mode-120000 link-text blobs (repointing a tracked link changes the digest; a filesystem manifest cannot see that). Ignored files, untracked files, and empty dirs are outside the contract (snapshot proposals keep the full-filesystem contract their staged apply can reproduce). After any git apply strategy, the applied head's tree digest must equal the sealed digest, verified in the temp worktree BEFORE the ref moves; mismatch = typed `state_conflict`, proposal apply-failed, target untouched. Pre-B-07 sealed git proposals (full-filesystem digest) fail this check closed — revise them. **Snapshot apply (B-05) — operator contract, not a CAS guarantee:** snapshot apply requires the source to be QUIESCED BY THE OPERATOR for the exchange. Matapan detects concurrent modification within the capture window via double digest (capture-time and pre-install re-hash of the backup) and aborts safely with restoration, and it re-verifies the backup's device+inode at the seam — but the final digest is a non-atomic tree scan, so a write racing the scan (or arriving via an already-open fd) cannot be detected; this is a documented operator contract, never a filesystem CAS. To make the residual recoverable rather than silent, the pre-apply backup is RETAINED on success (the apply result names its exact path) and is NEVER auto-deleted: reconciliation reports it forever, and removal is the operator's explicit act via `matapan workspace purge-backups <id> --yes` (lists the backup, refuses symlinked homes). Backups live in per-source dirs (`<parent>/.matapan-snapshot-backups/<basename>/`, created with symlink refusal on every new component — a pre-planted link is a typed error, never followed); on rollback failure the backup is never deleted and the error names its exact path. The reconciler sweeps a source's backup home only when ALL proposals of EVERY workspace bound to that source are terminal (NB-02); the container, unmatched entries, and legacy flat backups are report-only forever. A concurrent swap of the backup container AFTER its verified creation is the remaining timed residual — detected at worst as a digest-mismatch abort, never silent. |
| Replay | Idempotency keys (principal+operation+key, hash-matched) and idempotent apply replay returning the prior result. |
| Audit tampering | Append-only hash-chained ledger; `Verify` detects modified or deleted entries. |
| Token misuse | HMAC-SHA256 obols, audience hardcoded to `matapan`, revocable, expirable; wrong-audience tokens never verify. In `auth.mode=charon`, validation delegates to the Charon endpoint (5s, fail-closed, same audience contract) — identity becomes Charon's; policy, proposals, and audit stay local. |
| Open enrollment via OAuth | The OAuth authorization server has **no auto-approve**: `/oauth/authorize` presents an approval form requiring the owner password (env-only, SHA-256-compared in memory, startup refuses without it, POST rate-limited alongside `/oauth/token`). Only the configured public PKCE client and allowlisted redirect URIs are accepted — no client auto-registration. Without the gate, any internet client reaching the tunnel hostname could mint admin tokens. JWTs are 24h HS256 with the same obol HMAC key; `/mcp` accepts obols and JWTs with identical principal resolution. The tunnel is still untrusted transport: TLS terminates at cloudflared, Matapan auth is required regardless. |
| Self-approval | In charon AND oauth modes (`review.prevent_self_approval`, default on for both), a proposal's creator cannot apply or reject it — typed `self_approval` error. Independent review is enforced at the guard, not by convention. |
| Connector authority (OAuth) | OAuth tokens map to a connector-SPECIFIC `agent-<client_id>` principal (auto-provisioned with AgentScopes — no `workspace.grant`, no `proposal.apply`), never admin by default. Token exchange issues exactly that principal's scopes; the approval page renders them verbatim. Apply stays human-only by scope: connectors cannot grant egress/secrets and cannot apply proposals. Workspaces reach connectors only via explicit human grants (CLI `--grant`, default grant to the connector in oauth mode). **Existing principals are verified, not trusted (B-04):** provisioning and startup require the row's scopes to stay within the agent set — a stale over-scoped row is a hard error; `auth.oauth_principal` may not name an admin-capable principal unless `auth.oauth_allow_admin: true` is explicitly set (documented as suspending this boundary). |
| Destructive paths from storage | Workspace IDs are validated at insert (no empty/dot/dot-dot/separator/NUL) and destroy independently requires the computed target to be a STRICT child of the workspace root plus an exact stored-path match — a collapsing or corrupted row is orphaned, never deleted (B-08). Git sources are bound to the common-dir AND worktree-root device+inode recorded at create (create fails closed when identity cannot be established): destroy and apply re-verify both at entry AND immediately before the destructive boundary (branch/worktree removal, ref move), and a row re-pointed at another clone or a different linked worktree fails typed (`ErrGitSourceRebind`). Rows with NO recorded identity (legacy/v9-v10-era) are REFUSED with `ErrGitSourceRebindRequired` — never silently backfilled, because content proof cannot distinguish a substituted linked worktree; the operator rebinds explicitly via `matapan workspace rebind <id> --yes` (prints recorded vs live identity, content proof first, then records). Destructive selectors are derived/validated, never trusted: branch deletion uses the derived `matapan/<id>` (a corrupted stored branch is refused), and apply uses the PROPOSAL's sealed-time `target_branch` (migration v13 — proposal-time evidence), requiring the workspace row's current value to match (`ErrTargetBranchMismatch` → rebind path). Identity revalidation is the LAST step before EACH destructive mutation — after the drain and container kill in destroy, and again immediately before worktree removal AND branch deletion (round 5); a FAILED verification at a destroy boundary suppresses the git subprocess entirely (round 6) — cleanup continues with the strict-child workspace dir and an orphan residual, never a destructive call against an unverified path; after the merge/digest work and strategy read in apply, and again immediately before the checked-out fast-forward merge (round 5). The apply target is additionally bound to hash-chained ledger evidence written at seal (`proposal_seal_evidence`: base, head, content digest, target branch — round 5): apply verifies the proposal row against that anchor BEFORE any value is used, so a jointly substituted workspaces+proposals pair mismatches (`ErrSealedEvidenceMismatch`), and proposals sealed before the anchor existed are REFUSED (`ErrSealedEvidenceMissing` — fail-closed legacy policy; re-seal to apply). The anchor is HMAC-SHA256 authenticated with the 0600 daemon key (`mac=` field, domain-separated `matapan-seal-evidence/v2`, constant-time compared at apply — round 6): a same-DB writer can rewrite rows and recompute the unkeyed chain but cannot forge the MAC, so the sealed selector is tamper-PROOF, not just tamper-evident. The workspace ID is INSIDE the authenticated message (v2, round-6 recheck): the ledger row's and proposal row's workspace columns are mutable outside the MAC, and without the binding an intact anchor could be replayed onto another workspace — relocation now mismatches and fails closed. Key rotation rides the domain version. Syscall-level residual (documented): the re-opened source pathname could still be swapped between that final check and the mutation itself; closing it needs descriptor-pinned git operations, which git does not offer. Snapshot apply verifies the source dir's device+inode at import (migration v9), RECHECKS it on the captured backup right before install (a same-content rebind at the seam is refused), and legacy backfill is fail-closed. |
| Network exposure of the daemon | Loopback bind by default; non-loopback refused without `--allow-lan`; even then all routes except loopback-only `/api/health` require obol auth. Remote agents (ChatGPT) arrive through a user-managed HTTPS tunnel — see ADR 0003. |
| Malicious repo content | Setup hooks/devcontainer execution are not performed in Sprint 1. **Every git invocation goes through one hardened runner (`internal/gitruntime`, B-03)**: hooks are disabled unconditionally (`-c core.hooksPath=<dev-null>` — command-line config outranks repo, included, and global config, so `.git/hooks` executables and hostile `core.hooksPath` settings never run); the environment is a fixed allowlist (no inherited vars, HOME is a daemon-controlled empty dir, system+global config nulled, no pager/prompts/editor, credential helpers reset); `safe.directory` is set to the exact canonical dir per invocation (never `*`). **No external programs:** `diff.external` is overridden AND every diff passes `--no-ext-diff`, fsmonitor is off, all signing AND signature verification is off (`commit.gpgSign`/`tag.gpgSign` false, `merge.verifySignatures` false, and every format-specific program selector neutralized: `gpg.program`, `gpg.openpgp.program`, `gpg.x509.program`, `gpg.ssh.program`, `gpg.ssh.defaultKeyCommand` — Matapan never signs and integrity comes from the sealed content digest, not git signatures, so overriding is unconditionally safe; round 5 closed the X.509/merge-verify surface), and repositories configuring ANY per-driver program git cannot disable generically (filters, merge drivers, external diff drivers, textconv) are REFUSED — preflighted before EVERY attribute-reading operation (create, status, commit, seal, apply) and evaluated in the EXACT execution context (the worktree or temp worktree the commands run in, not just the source repo), so `includeIf gitdir:` conditions cannot evade it. The runtime ownership chown excludes `.git` entirely, and the MCP file-edit API refuses any path crossing `.git` BEFORE writing (typed `path_escape`, case-folded comparison — canonicalization is lexical and APFS is case-insensitive), in every ownership mode, and a seal whose run drain times out rolls the workspace back to its prior live state rather than wedging it in sealing. Workspace file tools never execute what they read. Snapshot import adds its own boundary: non-Git sources are **copied, never referenced** — the source root is canonicalized with EvalSymlinks, symlinks escaping the source are skipped (recorded), FIFOs/sockets/devices fail the import, byte/file counts are capped, and source opens are TOCTOU-defended. The import never follows the source after the copy; snapshot CAS apply re-manifests the source dir and refuses to write if it drifted. Residual (documented in `internal/gitruntime`): repo-config `include.path`/`includeIf` are always processed by git, but they can only add config — `-c` still wins for every execution knob. |
| Prompt injection via AGENTS.md | Policy lives in the daemon (principals/scopes/grants), not in the repo. **Instruction content is data for the agent, never control input**: it is loaded verbatim (size-capped, through the path defense), never parsed for configuration, and can never alter policy, scopes, grants, limits, mounts, egress, or the runtime profile. Root-only discovery in Sprint 4 (nested discovery is a follow-up that will inherit the same rule); case-variant duplicates are deduped by inode; symlinked instruction files escaping the root are refused. Every load records path + SHA-256 + size + trigger into the instruction manifest, and instruction digests are sealed into proposals. |
| Secret exfiltration via env/logs | Secrets are AES-256-GCM at rest (daemon key 0600, never plaintext on disk), set via stdin/`--env` (never argv — ps/shell history). Grants are human-only (`workspace.grant`), injection is env-only (`MATAPAN_SECRET_<NAME>`, granted secrets only), and grants are revoked at seal and destroy. Every injected value is registered with the ledger redactor at run time so accidental echoes are caught. **Residual risk (documented):** a malicious agent can read its own container env — env injection means the agent gets the value while granted. Daytona-style proxy substitution (plaintext never enters the sandbox) is the P1 upgrade; until then, grant narrowly and rely on seal/destroy revocation. |
| Egress via agent request | Network is `none` unless the workspace has an allowlist grant. Grants are **human-only** (`workspace.grant`; agents can't self-grant) and ledgered. Granted runs use the **egress proxy**: an allowlisting CONNECT/HTTP proxy per run; denials are ledgered with destination. **Enforcement honesty:** native Linux Docker attaches the container to an internal network with no route out (full enforcement); Docker Desktop cannot reach host-gateway from internal networks, so containers run on the default bridge with the proxy as configured path — HTTP(S) is filtered but raw-IP egress is open there (sidecar proxy is the full-enforcement upgrade). Denied-command profiles (argv[0] denylists) are advisory depth, not a sandbox. |
| Concurrent mutation / lock races | Per-workspace exclusive lock: in-process mutex map (ref-counted, no leak) plus a non-blocking flock on `<root>/.locks/<id>.lock`. flock releases automatically on process death, so a crashed daemon cannot wedge a workspace; the CLI and MCP server share the same lock files, so cross-process mutations serialize too. **Operation/state matrix** (`workspace.CheckOpState`): every guard-mediated op is checked against the workspace's CURRENT state — mutations (edit/run/commit/grants) on live states only, seal on ready/active/sealed, decisions on sealed, status on any non-terminal state, read-only ops (file_read/search/glob/grep) on live states plus sealed so the exact tree a proposal will apply can be reviewed pre-apply — and mutating ops re-verify under the lock so a stale read never authorizes a write. Lock discipline: file edit holds the lock across the whole write; commit re-checks state inside its lock; seal holds it across the ENTIRE evidence + manifest + commit + store sequence; apply/reject hold it across the decision. Runs take a counted **run lease** (state check + ready→active under the lock, lease held for the container's duration without holding the flock) **persisted in the store with a heartbeat (NB-01): every process — daemon or CLI — sees live leases, EVERY retained lease row counts as live for seal/destroy drains (round 6 — read-side aging could make a failed-degradation-write container invisible; only verified cleanup deletes a row), and daemon startup sweeps stale rows**; destroy marks the workspace destroying (new runs refused), drains active leases across processes, kills labeled containers (the CLI installs the same killer), then sweeps. **Seal drains too: proposal_create refuses new runs (sealing state) and waits for active runs to reach zero before manifest/commit; on drain timeout it rolls back to the prior live state.** Lease-store READ errors fail closed (`ErrLeaseStoreUnavailable` — never a silent zero); lease-store WRITE failures on the safety paths fail closed too (round 5): a failed degradation write sets a NEVER-pruned in-process tombstone (liveRuns unions it, so the workspace stays live for that process), the startup sweep returns degradation/deletion write failures as errors and the daemon REFUSES to serve with a store that cannot record safety state, and destroy refuses when no container killer/lister is installed AND the workspace has durable ever_ran evidence (`ErrContainerKillUnavailable` — unavailable visibility is not permission to delete; round 6: ever_ran is set transactionally at lease insert and never cleared, backfilled true for pre-v14 rows, so unlike the transient lease table it distinguishes never-run workspaces — e.g. create-rollback cleanup, which may destroy without container visibility — from ran ones); a heartbeat failure kills the workspace's containers and tombstones the lease ONLY after the kill is verified (kill + re-list); an unverifiable kill marks the lease DEGRADED — counted live regardless of heartbeat age, blocking destroy/seal until the container is confirmed gone (the startup sweep verifies per stale row: containers killed+verified before any row deletion, unverifiable kills degraded, degraded rows kept whenever the container state can't be read; surfaced at startup and in `workspace diagnose`); a degradation WRITE failure is logged loudly and covered by the in-process live-set (`liveRuns` unions the store count with this manager's own runs, so a write-failing store can never zero out a run this process still holds); release deletes the lease row only after container absence is verified (survivors → degraded instead); destroy aborts typed when the container kill is unavailable (killer present but failing) or leaves survivors. Daemon startup kills/reconciles containers BEFORE sweeping stale leases or running GC. Proposal decisions are compare-and-swap in the store (`DecideProposal … WHERE state IN (expected)`): a racing second decision loses with a typed `state_conflict` — reject can never land after apply. |
| Residual state after teardown | Destroy works from any non-terminal state, kills Matapan-labeled containers first, revokes secret-grant metadata, then **verifies** removal (dir gone, `git worktree list` clean) and reports precise residuals instead of trusting delete calls. Daemon startup reconciles: transitional states from a dead process fail or resume, row/dir orphans are detected in both directions, stale git worktree metadata is pruned, orphaned labeled containers are removed — all ledgered. |

## Honest isolation language

Matapan provides **hardened container isolation**, not "safe execution".
A determined adversary with a kernel or container-runtime exploit can escape
any runc-based boundary. The higher-assurance path (gVisor, Kata, microVM
isolation profiles) is a planned runtime adapter, not Sprint 1.

## Known gaps (tracked to later sprints)

- Egress enforcement is full (internal network + proxy) on native Linux
  Docker only; Docker Desktop gets proxy-only HTTP(S) filtering until the
  sidecar proxy lands.
- Env-injected secrets are readable by the agent while granted; proxy
  substitution (plaintext never enters the sandbox) is the P1 upgrade.
- Instruction discovery is tree-wide with a 64-file flooding cap; per-file
  256 KiB cap.
- Test parsing is best-effort JUnit XML + TAP, always marked matapan-parsed
  (observed evidence, never agent narration).
- Charon mode is the adapter boundary only: no Charon-issued scope
  narrowing yet, no centralized audit forwarding.
- No rate limiting on the MCP listener beyond loopback + auth (acceptable
  for local single-user MVP).
- Snapshot apply is one-way (workspace → source dir); conflict-aware
  three-way merge for non-Git sources is not attempted.
- Manifest format note (empty-directory fix): manifests now record empty
  directories so staged applies preserve them. Trees WITHOUT empty dirs
  digest identically to the old format. Pre-fix proposals whose base digest
  was computed file-only FAIL SAFE as typed `stale_base` under the new
  semantics (never a silent drop) — destroy + re-import (or revise) such
  workspaces.

## Reviewed at Sprint 8

Full re-review against the code as it exists at beta. Verified claims and
the residual risks that remain:

**Verified mitigations (claim → code).** Every row in the mitigations table
above was re-checked: path defense (`internal/workspace/paths.go`,
fuzz-tested), runtime guards (`internal/runtime` — `ValidateSpec` plus the
Sprint-3..6 profile), CAS apply with verified conflict aborts
(`internal/proposal`), hash-chained redacted ledger with retention anchors
(`internal/ledger`), obol auth with the fixed audience (`internal/obol`,
`internal/auth`), lock/destroy/reconcile lifecycle (`internal/workspace`,
`internal/reconcile`), policy profiles with digests sealed into proposals
(`internal/policy`, `internal/proposal`), secrets broker with
seal/destroy revocation (`internal/secrets`), egress grants via
human-scope and the per-run credentialed proxy (`internal/egressproxy`).

**New since last review.**
- Hardlinks: file tools now refuse link count > 1 (`ErrHardlink`) — an
  inode shared with an outside file can't be read or written through the
  workspace tools. Residual: other channels (container writes) produce
  only agent-authored content; documented in `docs/docker-limitations.md`.
- Worktree `.git` pointer validation: seal and commit refuse a pointer
  resolving outside the source repo's `.git/worktrees` area.
- Git ref flag injection: refs/branch names starting with `-` are refused
  before reaching git argv.
- Egress proxy: per-run random credential required (407 without it) and
  non-wildcard bind — the Sprint-6 open-proxy finding is closed.
- Run output is redacted through the ledger's registered-secret set before
  any response — granted secrets can't be echoed back by `printenv`.
- GC races: collection re-checks eligibility under the workspace lock
  (seal race closed); upgrade backfill prevents legacy idle-collection.
- Post-beta audit (B-06/M-02): the operation/state matrix
  (`workspace.CheckOpState`) now gates every workspace op at the guard and
  re-verifies under the lock for mutations; edit/commit/seal/apply/reject
  hold the workspace lock across the whole compound operation; runs take a
  counted lease that destroy drains before container sweep; proposal
  decisions are store-level CAS (`WHERE state IN (expected)`), so a racing
  reject/apply loses with a typed `state_conflict`.
- Post-beta audit (B-01): the runtime user is a daemon-resolved identity
  (`runtime.ResolveIdentity`) instead of a hardcoded `nobody`. Non-root
  daemons run containers as their own uid:gid; root daemons (container
  deployment) run them as configured `runtime.uid`/`gid` (default 65534)
  and chown workspace content to match at every write moment — native
  Linux bind mounts can now read AND write the workspace. Doctor reports
  the identity and probes the chown capability.
- Post-beta audit (B-01 follow-up + B-03): the ownership chown now
  EXCLUDES `.git` (dirs, contents, and worktree pointer files) — the
  runtime identity can never write hooks or git config. And every git
  invocation routes through one hardened runner (`internal/gitruntime`):
  hooks dead via `-c core.hooksPath=<dev-null>` (beats repo/included/
  global config), scrubbed allowlist env with an isolated HOME, nulled
  system/global config, credential helpers reset, no pager/prompts,
  per-invocation exact `safe.directory` (handles root-mode
  split-ownership worktrees; never `*`). External filter drivers — the
  one code-execution channel git cannot disable — are refused outright
  at create/commit/seal/apply.
- Post-beta audit (B-02): read-side TOCTOU is now closed by construction
  (`openPinned`): every read open (file tools, instruction loading,
  snapshot import, manifest hashing, proposal staging/revision) walks
  from a pinned root descriptor with `O_NOFOLLOW` on every component and
  compares the opened inode's identity against the resolve-time
  observation — a raced symlink swap fails the open instead of reading a
  host file. Deterministic hook tests swap at the exact pre-open window.
- Post-beta audit (B-05/B-07): snapshot apply re-verifies the captured
  backup immediately before install (concurrent writes abort typed, never
  silently deleted; backup retained and named on rollback failure;
  reconciler sweeps stale backups only for terminal proposals). Git
  proposals now seal a CONTRACT digest — git-tracked content with git's
  filemode model — and every git apply verifies the applied tree's digest
  in the temp worktree BEFORE the ref moves (mismatch = apply-failed,
  target untouched). The open-fd residual of rename-based exchange is
  documented in the CAS row.

**Residual risks (explicit).** Kernel/runc escape (gVisor experimental,
Kata/microVM future); Docker Desktop degraded egress (raw-IP bypass until
sidecar proxy); env-injected secrets readable by the agent while granted
(proxy substitution is the upgrade); the host Docker daemon is trusted
infrastructure; argv[0] denylists are advisory; MCP listener has no rate
limit beyond loopback+auth. Details: `docs/docker-limitations.md`.

**Adversarial testing at Sprint 8.** Go-native fuzzers cover path
resolution, manifest parsing, snapshot import, and the full MCP argument
surface (all clean at ~100k+ execs); a hand-written edge matrix covers
TOCTOU swaps, symlink loops, hardlinks, fake git pointers, force-push CAS,
dirty checkouts, submodules, detached HEAD, env injection, flag-shaped
argv, case-variant paths, and mount escapes.
