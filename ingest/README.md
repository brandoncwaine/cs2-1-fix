# ingest: fetch your CS2 demos automatically

Finds your new matches through Steam's official match-history API, asks the CS2 game
coordinator for each demo through a separate "bot" Steam account, downloads and decompresses
it. `scripts/sync.sh` then parses new demos and builds the cards for the website.

Node 20+ (Steam libraries: `steam-user`, `globaloffensive`). Kept apart from `src/onefix`,
which stays stdlib Python.

## One-time setup (you do these; nothing here handles your main account's password)

1. **Web API key** (main account): https://steamcommunity.com/dev/apikey
2. **Match history auth code + a recent share code** (main account): Steam Support >
   Counter-Strike 2 > "Access to Your Match History"
   (https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid=730&issueid=128).
   Copy the authentication code (`XXXX-XXXXX-XXXX`) and your most recent match's share code.
3. **Fill in the config**: run `npm install` then `npm run sync` once in `ingest/`. It creates
   `~/.config/onefix/steam.json` (readable only by you). Fill in `steamid` (your main
   steamid64), `webApiKey`, `matchAuthCode`, `firstShareCode`. `demoDir` defaults to
   `~/Documents/cs2-demos/own`.
4. **Bot account**: a separate Steam account, never your main. In `ingest/` run
   `npm run login` and type its name and password; Steam Guard is prompted there too. Only a
   session token is saved (`~/.config/onefix/bot-refresh-token`); the password is not stored.
   It adds the free CS2 licence to the bot if missing.

## Every time

```
scripts/sync.sh          # from the repo root
```

Re-running only fetches new matches. Cards are written to `parsed/web/data.json`. Progress is in `~/.config/onefix/ingest-state.json`.
Valve deletes demos after a few weeks, so run it at least weekly.

## More players (friends)

One bot account and one Web API key serve everyone. Each friend sends you three things from
their own account: their steamid64, their match history auth code and one recent share code
(step 2 above). Add them to `players` in `steam.json` (the top-level fields stay as the first
player; `name` is what the site shows):

```json
"players": [
  { "name": "Sam", "steamid": "7656...", "matchAuthCode": "XXXX-XXXXX-XXXX", "firstShareCode": "CSGO-..." }
]
```

Demos are shared (friends in the same match use one file); parsed matches and cards are per
player. If one player's auth code stops working, the others still sync and the site shows the
problem on that player's page. A friend can revoke access at any time by making a new auth code.

## Running on Railway (website + daily sync)

`Dockerfile` + `railway.json` at the repo root: one always-on service runs `python -m onefix.web`.
It serves the private site and runs `scripts/sync.sh` every day at 06:00 UTC (and at start-up
if the data is over a day old). Mount a volume at `/data` (config/token, demos, parsed JSON,
`web/data.json`). Give the service a public domain in Railway (Settings > Networking).

Variables on the service:

| Variable | Secret? | Value |
|---|---|---|
| `ONEFIX_WEB_PASSWORD` | **yes** | shared password for the site; without it the site is not reachable |
| `ONEFIX_STEAMID` | no | main account steamid64 |
| `ONEFIX_PLAYER_NAME` | no | your name on the site (default "Me") |
| `ONEFIX_FIRST_SHARE_CODE` | no | share code to start from |
| `STEAM_WEB_API_KEY` | **yes** | Web API key |
| `STEAM_MATCH_AUTH_CODE` | **yes** | match history auth code |
| `ONEFIX_PLAYERS` | **yes** | optional: friends, as the JSON list shown above (on one line) |
| `BOT_REFRESH_TOKEN` | **yes** | contents of `~/.config/onefix/bot-refresh-token` |
| `ONEFIX_SYNC_HOUR_UTC` | no | optional: hour of the daily sync (default 6), or `off` |

Set the secret ones yourself in the Railway dashboard. `BOT_REFRESH_TOKEN` only seeds the
first run: renewed tokens are saved to `/data/config/` and used from then on. Renewal makes
the old token invalid, so once the cloud job renews it, the local copy stops working: run the
sync in one place only (or `npm run login -- --fresh` locally for a separate session).

Everyone with the password sees every player's cards. The page shows cards, counts and sync
problems only: no secrets, no share codes, and no Steam IDs other than the listed players' own.

Preview the site locally (no password, this machine only, no syncing):

```
ONEFIX_SYNC_HOUR_UTC=off PYTHONPATH=src .venv/bin/python -m onefix.web   # http://127.0.0.1:8000
```

## Notes

- Whether Steam's terms allow a bot account for this is unchecked (DECISIONS D7). The risk
  falls on the bot account, which is why it must not be your main account.
- Demos are saved with the same names the CS2 client uses (`match730_<id>_<port>_<server>.dem`).
- `npm test` runs offline unit tests (share codes, URL and file-name handling, the API walk,
  several-player config and state).
