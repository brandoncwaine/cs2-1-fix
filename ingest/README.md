# ingest: fetch your CS2 demos automatically

Finds your new matches through Steam's official match-history API, asks the CS2 game
coordinator for each demo through a separate "bot" Steam account, downloads and decompresses
it. `scripts/sync.sh` then parses new demos and prints your cards.

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

Re-running only fetches new matches. Progress is in `~/.config/onefix/ingest-state.json`.
Valve deletes demos after a few weeks, so run it at least weekly.

## Running on Railway (daily cron)

`Dockerfile` + `railway.json` at the repo root: a cron service runs `scripts/sync.sh` every day
at 06:00 UTC. Mount a volume at `/data` (config/token, demos, parsed JSON, `cards.json`).

Variables on the service:

| Variable | Secret? | Value |
|---|---|---|
| `ONEFIX_STEAMID` | no | main account steamid64 |
| `ONEFIX_FIRST_SHARE_CODE` | no | share code to start from |
| `STEAM_WEB_API_KEY` | **yes** | Web API key |
| `STEAM_MATCH_AUTH_CODE` | **yes** | match history auth code |
| `BOT_REFRESH_TOKEN` | **yes** | contents of `~/.config/onefix/bot-refresh-token` |

Set the secret ones yourself in the Railway dashboard. `BOT_REFRESH_TOKEN` only seeds the
first run: renewed tokens are saved to `/data/config/` and used from then on. Renewal makes
the old token invalid, so once the cloud job renews it, the local copy stops working: run the
sync in one place only (or `npm run login -- --fresh` locally for a separate session).

Cards print to the deploy logs and are written to `/data/cards.json`.

## Notes

- Whether Steam's terms allow a bot account for this is unchecked (DECISIONS D7). The risk
  falls on the bot account, which is why it must not be your main account.
- Demos are saved with the same names the CS2 client uses (`match730_<id>_<port>_<server>.dem`).
- `npm test` runs offline unit tests (share codes, URL and file-name handling, the API walk).
