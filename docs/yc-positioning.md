# YC positioning — "software for agents"

**Source:** Y Combinator Requests for Startups, Fall 2026 page (verified 2026-09-06, https://www.ycombinator.com/rfs).
**Use:** framing for README / video / Devpost. Cite as "YC RFS Fall 2026".

## What YC is currently saying (relevant requests)

1. **Small Software** — purpose-built tools with 1–few users, easy to build
   now but "still hard to deploy and share"; incumbent clouds are built for
   Big Software. A cloud for small software should make it "as easy to share
   with your colleagues as a Google Doc."
2. **Multiplayer agents** — "AI hasn't had its multiplayer moment yet… working
   with AI is largely single-player." The ask: shared, live agent sessions
   a team can drop into, watch, redirect, and hand off — "the way they'd
   work with any other human team member."
3. **Dependabot for APIs** — "The application layer connecting API providers
   to their customers' codebases… When Stripe ships a breaking change or a
   new feature, an agent should scan customer codebases, identify affected
   usages, and open a PR with the fix."
4. **Crypto rails for agents** — "agents are going to use crypto networks as
   financial rails" (agentic commerce, stablecoins).
5. **OS for the physical world** — three kinds of workers: agents, robots,
   humans; the new operating systems manage all three and record work as it
   actually happens.

## What this means for Forge

- **The customer of software is shifting to agents.** YC's requests describe
  three agent-customer layers: where small software runs (infra), how teams
  collaborate with agents (shared sessions), and how agents keep their tools
  current (API-change agents). All three need the same substrate: **durable,
  testable, portable capability that outlives any single session or harness.**
- **Forge = the capability layer for agent fleets.** YC's multiplayer request
  assumes the agent has persistent context across the team; its API-agent
  request assumes the agent knows which APIs changed and how to fix them.
  Both assume a learning substrate. AO provides orchestration; Forge provides
  the substrate: gated skills, context packages, strategy notes, economics.
- **Positioning line (use in README/video):**
  > "YC's Fall 2026 RFS bets the next wave of software is built *for* agents.
  > Agents that build and share software need memory that is verified,
  > portable, and economical — not a transcript dump. Forge is that layer,
  > proven by a fleet that measurably improves across tasks and harnesses."
- **Do not overclaim:** YC's RFS is directional validation, not a product
  spec. Forge does not do cloud hosting for small software, multiplayer
  sessions, or API-change agents in this hackathon — those are the
  long-term product family. Say so once in the README, move on.
