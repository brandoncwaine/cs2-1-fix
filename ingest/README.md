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

Friends add themselves on the website: they sign in through Steam, enter the invite code you
gave them, and paste their own match history auth code and one recent share code (step 2
above, from their account). The site checks the codes with Steam, saves them in
`onefix.db` in the config folder, and starts a sync. One bot account and one Web API key serve
everyone. Demos are shared (friends in the same match use one file); parsed matches and cards
are per player. If one player's auth code stops working, the others still sync and that
player sees the problem on their page.

You can still list players by hand in `players` in `steam.json` (or `ONEFIX_PLAYERS` in the
cloud): `[{ "name", "steamid", "matchAuthCode", "firstShareCode" }]`. Those cannot be removed
from the site.

## Running on Railway (website + daily sync)

`Dockerfile` + `railway.json` at the repo root: one always-on service runs `python -m onefix.web`.
It serves the site and runs `scripts/sync.sh` every day at 06:00 UTC, at start-up if the data
is over a day old, and whenever someone joins or leaves. Mount a volume at `/data` (user
database, session secret, bot token, demos, parsed JSON, `web/data.json`). Give the service a
public domain (Settings > Networking) and set `PORT` to the domain's target port.

Variables on the service:

| Variable | Secret? | Value |
|---|---|---|
| `ONEFIX_INVITE_CODE` | **yes** | code a new person must enter to join (`ONEFIX_WEB_PASSWORD` is used if this is not set). Without either, nobody new can join |
| `ONEFIX_STEAMID` | no | your steamid64: the first player, and the site's owner |
| `ONEFIX_PLAYER_NAME` | no | your name on the site (default "Me") |
| `ONEFIX_FIRST_SHARE_CODE` | no | share code to start from |
| `STEAM_WEB_API_KEY` | **yes** | Web API key (also used to check a new person's codes) |
| `STEAM_MATCH_AUTH_CODE` | **yes** | your match history auth code |
| `BOT_REFRESH_TOKEN` | **yes** | contents of `~/.config/onefix/bot-refresh-token` |
| `PORT` | no | the port the public domain routes to (8080) |
| `ONEFIX_MAX_USERS` | no | optional: most people who may join by invite (default 10) |
| `ONEFIX_BASE_URL` | no | optional: public address; defaults to Railway's public domain |
| `ONEFIX_PLAYERS` | **yes** | optional: players listed by hand, as JSON on one line |
| `ONEFIX_SYNC_HOUR_UTC` | no | optional: hour of the daily sync (default 6), or `off` |

Set the secret ones yourself in the Railway dashboard. `BOT_REFRESH_TOKEN` only seeds the
first run: renewed tokens are saved to `/data/config/` and used from then on. Renewal makes
the old token invalid, so once the cloud job renews it, the local copy stops working: run the
sync in one place only (or `npm run login -- --fresh` locally for a separate session).

Who sees what: people sign in through Steam (the site never sees a Steam password). Each
person sees only their own cards; the owner (`ONEFIX_STEAMID`) can see everyone's and remove
people. Anyone can delete their own data from the page. The page carries no secrets, no share
codes, and no Steam IDs other than the viewer's own (the owner also sees members' IDs).

Preview the site locally (this machine only, no syncing, signed in as the given steamid64):

```
ONEFIX_LOCAL_USER=<steamid64> ONEFIX_STEAMID=<steamid64> ONEFIX_SYNC_HOUR_UTC=off \
  PYTHONPATH=src .venv/bin/python -m onefix.web   # http://127.0.0.1:8000
```

## Notes

- Whether Steam's terms allow a bot account for this is unchecked (DECISIONS D7). The risk
  falls on the bot account, which is why it must not be your main account.
- Demos are saved with the same names the CS2 client uses (`match730_<id>_<port>_<server>.dem`).
- `npm test` runs offline unit tests (share codes, URL and file-name handling, the API walk,
  several-player config and state).
