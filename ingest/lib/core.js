// Pure helpers for the ingest pipeline. No network, no Steam login: unit-tested.
import { decodeMatchShareCode } from 'csgo-sharecode';

export const SHARECODE_API =
  'https://api.steampowered.com/ICSGOPlayers_730/GetNextMatchSharingCode/v1';

const SHARECODE_RE = /^CSGO(-[A-Za-z0-9]{5}){5}$/;

export function isShareCode(code) {
  return typeof code === 'string' && SHARECODE_RE.test(code);
}

export function decodeShareCode(code) {
  if (!isShareCode(code)) throw new Error(`not a match share code: ${code}`);
  const { matchId, reservationId, tvPort } = decodeMatchShareCode(code);
  return { matchId: String(matchId), reservationId: String(reservationId), tvPort };
}

/**
 * Walk Steam's match history forward from `knownCode`, returning every newer share code
 * in order. Steam answers one code per call; "n/a" (HTTP 202) means no newer match yet.
 * `fetchImpl` is injectable for tests. Never logs the key or auth code.
 */
export async function newerShareCodes({ fetchImpl = fetch, key, steamid, authCode, knownCode, max = 200 }) {
  const out = [];
  let current = knownCode;
  for (let i = 0; i < max; i++) {
    const url = new URL(SHARECODE_API);
    url.search = new URLSearchParams({ key, steamid, steamidkey: authCode, knowncode: current });
    const res = await fetchImpl(url.toString());
    if (res.status === 403) throw new Error('Steam rejected the API key or match auth code (403).');
    if (res.status === 412) throw new Error(`Steam does not recognise the known share code ${current} (412).`);
    if (res.status === 429) throw new Error('Steam rate limit hit (429); try again later.');
    if (res.status !== 200 && res.status !== 202) throw new Error(`Steam API error: HTTP ${res.status}`);
    const body = await res.json();
    const next = body?.result?.nextcode;
    if (res.status === 202 || !next || next === 'n/a') break;
    if (!isShareCode(next)) throw new Error(`Steam returned an unexpected code: ${next}`);
    out.push(next);
    current = next;
  }
  return out;
}

/** The demo URL from a GC match record: the `map` of its last round stats entry. */
export function demoUrlFromMatch(match) {
  const stats = match?.roundstatsall ?? [];
  for (let i = stats.length - 1; i >= 0; i--) {
    if (stats[i]?.map) return stats[i].map;
  }
  return match?.roundstats_legacy?.map || null;
}

const DEMO_URL_RE = /^https?:\/\/replay(\d+)\.valve\.net\/730\/(\d+)_(\d+)\.dem\.bz2$/;

/**
 * Same name the CS2 client uses for downloaded demos, so manual and automatic downloads match:
 * http://replay390.valve.net/730/003848141567361548483_1426637720.dem.bz2
 *   -> match730_003848141567361548483_1426637720_390.dem
 */
export function demoFileName(url) {
  const m = DEMO_URL_RE.exec(url);
  if (!m) throw new Error(`unexpected demo URL: ${url}`);
  const [, server, reservation, port] = m;
  return `match730_${reservation}_${port}_${server}.dem`;
}

/** Reservation id and TV port as they appear in a client demo file name.
 *  Note: a share code's tvPort is only the low 16 bits of this port (checked on a real match),
 *  so compare share codes to files by reservationId, or by `tvPort & 0xFFFF`. */
export function idsFromFileName(name) {
  const m = /^match730_(\d+)_(\d+)_\d+\.dem$/.exec(name);
  return m ? { reservationId: String(BigInt(m[1])), tvPort: Number(m[2]) } : null;
}

export function emptyState() {
  return { players: {} };
}

export function emptyPlayerState() {
  return { lastCode: null, matches: {} };
}

/** State is kept per player (keyed by steamid64). A state file from before several players
 *  were supported is one player's state at the top level: it belongs to the first player. */
export function migrateState(raw, primarySteamid) {
  if (raw?.players) return raw;
  if (raw?.matches) {
    return { players: { [primarySteamid]: { lastCode: raw.lastCode ?? null, matches: raw.matches } } };
  }
  return emptyState();
}

/** What the parser and the website need to know about each player. No secrets, no share codes.
 *  `fileExists` is injectable for tests. */
export function buildManifest(config, state, fileExists) {
  return {
    players: config.players.map((p) => {
      const ps = state.players[p.steamid] ?? emptyPlayerState();
      const entries = Object.values(ps.matches);
      return {
        steamid: p.steamid,
        name: p.name,
        demos: entries.filter((m) => m.status === 'downloaded' && fileExists(m.file)).map((m) => m.file).sort(),
        expired: entries.filter((m) => m.status === 'expired').length,
        failed: entries.filter((m) => m.status === 'error').length,
        history_error: ps.error ? ps.error.message.replace(/CSGO(-[A-Za-z0-9]{5}){5}/g, 'CSGO-…') : null,
      };
    }),
  };
}

/** Codes still to fetch for one player: the known code itself if never handled, then newer ones. */
export function pendingCodes(state, knownCode, newer) {
  const all = [knownCode, ...newer].filter((c, i, a) => c && a.indexOf(c) === i);
  return all.filter((c) => !state.matches[c] || state.matches[c].status === 'error');
}
