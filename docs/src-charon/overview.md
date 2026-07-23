# Charon

> Lethe remembers. Charon carries.

Charon is a self-hosted **MCP policy gateway** for
[Lethe](https://github.com/openlethe/lethe). It gives AI clients scoped,
auditable access to Lethe memory while Lethe itself stays private.

## Architecture

```
MCP Client (ChatGPT, Claude, etc.)
  |
  | HTTPS
  v
Cloudflare Tunnel / cloudflared
  |
  | HTTP
  v
Charon (MCP Gateway + Auth)
  |
  | Private Network
  v
Lethe / Lethe Git (memory store)
```

No client ever talks to the memory store directly. Every call passes
through Charon's principal model: who you are, which projects you can see,
which scopes you hold, and which refs you own.

## What it provides

- **Project-scoped authorization** — per-principal project grants, exact
  and case-sensitive. A wildcard grant is read-only; mutations need an
  exact project grant.
- **Actor-owned refs** — `refs/agents/<actor>/main`,
  `refs/sessions/<actor>/<session>`, `refs/topics/<topic>`. Principals
  commit only to refs they own.
- **Compare-and-swap changesets** — every write is an immutable,
  digest-chained changeset with explicit ordered semantic operations and
  idempotency keys.
- **Protected shared memory** — `refs/shared/*` moves only by proposal,
  **independent review** (the originator can never review its own work),
  and a signed merge envelope verified by Lethe.
- **Auditable proposals** — every review decision and merge lands in a
  hash-chained ledger.
- **Two credential surfaces** — OAuth (PKCE) for browser connectors like
  ChatGPT, and Obol bearer tokens for local agents and reviewer
  automation. Obols are audience-bound and minted per gateway.

## Principals and scopes

| Principal profile | Scopes | Purpose |
|---|---|---|
| Author (proposer) | `memory.read` `memory.search` `memory.branch` `memory.commit` `memory.propose` | Writes owned refs, proposes merges |
| Reviewer | `memory.read` `memory.search` `memory.review` `memory.merge` `proposal.review` | Independent review and merge |
| Reader | `memory.read` `memory.search` `thread.read` | Accepted-memory recall only |

The review-separation property is structural: the gateway identifies the
principal and refuses self-review no matter what the client asks.

## Where to go next

- [Full Run: End to End](full-run.html) — bootstrap, credentials, three
  agent roles, and a complete propose → review → merge cycle.
- [Operations](operations.html) — running and maintaining the gateway.
- [Local Reviewer Setup](reviewer.html) — the isolated reviewer
  deployment used for protected-ref merges.
