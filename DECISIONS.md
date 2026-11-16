# DECISIONS.md — CS2 One-Fix Coach

Settled decisions only. Change one by adding a new entry that supersedes it, not by editing silently.

## D1 — No in-game overlays (2026-11-13)
Nothing reads the screen or hooks the game during matches. Everything runs after the match or on practice servers. Reason: grey area with Valve's anti-cheat stance; a VAC ban would hit customers.

## D2 — Detectors are deterministic, tested code; the LLM only writes up (2026-11-13)
The LLM never invents tactical claims. Every claim on a card links to specific rounds. Prescriptions are fixed human-written templates per detector, filled with counted facts.

## D3 — One fix per map and side; refuse when data is thin (2026-11-13)
Show a single top fix per map and side. Below the minimum sample the card says so. No guessing.

## D4 — No Valve / Counter-Strike logos or implied affiliation (2026-11-13)
Check trademarks and domains before naming the product.

## D5 — The project brief (13 Nov 2026) is the source of truth (2026-11-13)
Changes to it are explicit, logged updates here.

## D6 — Player-facing product only; no coach copilot (2026-11-13)
Coaches may be used as research labellers for detector output, but are not customers.

## D7 — Ingestion: share codes + a Steam bot account (2026-11-16)
Demos are fetched automatically: Steam's match-history API gives the player's share codes, a separate bot Steam account asks the CS2 game coordinator for each demo URL, and the demo is downloaded from Valve's replay servers. Brandon's call: manual download is too much friction for the product to work. Steam's terms for bot accounts are still unchecked; the risk falls on the bot account, never a user's main account. Built in `ingest/` (Node, because the maintained game-coordinator libraries are Node).

## D3 reaffirmed (2026-11-16)
Kept one fix per map and side after the pro-demo results showed it needs ~15 maps of one map per player. Not to be revisited without a new entry.

## D8 — Frontend: private site for Brandon and a few friends, one always-on service (2026-11-16)
A small website shows each player's cards. Audience is Brandon plus 3-5 friends (the validation group from the handoff), not the public: one shared password, everyone sees every player. Friends are added by Brandon in the config (steamid64, match auth code, one share code each); there is no sign-up. The Railway cron became one always-on service that serves the site and runs the daily sync itself, because a Railway volume attaches to one service and a cron service is off between runs. Stdlib Python server, no framework, no database. Public sign-up (Steam login, per-user storage, privacy policy) is deliberately not built yet.

## D9 — Real accounts: Steam sign-in, invite only (2026-11-16)
Supersedes the shared password and "no sign-up" parts of D8. People sign in through Steam (OpenID), which gives a verified steamid64 and means the site never handles a password. A new person needs an invite code, then enters their own match auth code and share code, which are checked with Steam before saving. Each person sees only their own cards; the owner sees everyone's (needed to ask each player whether their card is right) and this is stated on the join form. Anyone can delete their own data. Built ourselves on the standard library with SQLite on the volume: hosted auth services were rejected because they do not provide Steam identity, so the Steam step would still be ours. Capped at 10 invited people by default. Still not public: opening it up needs a privacy policy, the bot-account terms check (D7) and a storage plan.

## Open (not decided)
- Check Steam's terms on bot accounts (D7). FACEIT auto-import looks unlikely.
- Benchmarks from a rank-matched or pro demo corpus as a v2 evidence base (source and licensing unresearched).
