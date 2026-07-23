# Matapan

Matapan is a **local-first transactional control plane for agent-produced
code**. Coding agents (ChatGPT, Claude, Codex) get disposable,
container-isolated workspaces and return work only as immutable,
evidence-bearing proposals, applied via compare-and-swap. **Your active
checkout is never in the agent's write path.**

The loop:

> import trusted source → disposable isolated workspace → scoped
> tools/runtime → capture edits + verification → seal immutable proposal
> against an expected base → review → compare-and-swap apply → revoke and
> destroy → redacted audit trail remains.

Matapan is a workspace transaction manager — not an IDE, not an agent, not
a generic sandbox, not a Git GUI.

## Status

**0.1.0-beta.1 + hardening rounds 3–6.** All eight planned sprints are
landed (security core, lifecycle, hardened runtime, MCP surface, proposal
engine, policy profiles, secrets broker, egress proxy, audit retention,
packaging), followed by an independent adversarial audit series that
closed every blocker-severity finding (B-03 host Git execution, B-05
snapshot backups, B-06/NB-01 run lifecycle, B-08 destructive storage
inputs). See `CHANGELOG.md` and the [Threat Model](threat-model.html).

## The trust model in one paragraph

The agent is untrusted code working on trusted source. Every git
invocation goes through one hardened runner (hooks dead, environment
scrubbed, external drivers refused, signing and signature verification
forced off). Every run executes in a locked-down container (capabilities
dropped, read-only rootfs, no network by default, resource clamps).
Agents never receive apply authority: work returns as a **sealed
proposal** whose content digest, policy digest, and target branch are
anchored in a hash-chained ledger and authenticated with an HMAC only the
daemon holds. Apply is a layered compare-and-swap — what you reviewed is
what lands, or nothing does.

## Key properties

- **Disposable workspaces** — git worktrees at an exact commit, defended
  snapshot copies of non-Git dirs, or fresh scaffolds. Leases and GC with
  sealed-work protection.
- **Scoped tool surface** — typed MCP tools with stable error codes,
  capability discovery, and an operation/state matrix enforced on every
  mutation.
- **Egress control** — network `none` by default; per-domain human grants
  through an allowlisting proxy with DNS-rebinding defense.
- **Secrets broker** — AES-256-GCM at rest, per-workspace grants, injected
  only into runs, revoked at seal and destroy, never ledgered.
- **Policy profiles** — image allowlists, command denylists, resource
  ceilings; the profile digest is sealed into every proposal.
- **Immutable audit** — every action lands in a redacted, hash-chained
  ledger with retention that preserves verifiability.

## Where to go next

- [Quickstart](quickstart.html) — zero to a sealed, applied proposal.
- [Docker Compose Setup](docker-compose.html) — the full per-model
  container deployment, end to end, with the environment variable
  reference.
- [Operations](operations.html) — day-to-day daemon and CLI operation.
- [Threat Model](threat-model.html) — the adversary classes and the
  defenses that hold against them.
