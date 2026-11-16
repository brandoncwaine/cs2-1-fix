// Config, secrets and state live OUTSIDE the repo, in ~/.config/onefix/, readable only by the user.
import { chmodSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

import { isShareCode, migrateState } from './core.js';

export const DIR = process.env.ONEFIX_CONFIG_DIR || join(homedir(), '.config', 'onefix');
export const CONFIG = join(DIR, 'steam.json');
export const TOKEN = join(DIR, 'bot-refresh-token');
export const STATE = join(DIR, 'ingest-state.json');

export const CONFIG_TEMPLATE = {
  name: 'Me',
  steamid: 'your main account steamid64 (17 digits)',
  webApiKey: 'from https://steamcommunity.com/dev/apikey',
  matchAuthCode: 'XXXX-XXXXX-XXXX from Steam Support > CS2 > Access to Your Match History',
  firstShareCode: 'CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx (any recent match of yours)',
  demoDir: join(homedir(), 'Documents', 'cs2-demos', 'own'),
  players: [],
};

function ensureDir() {
  mkdirSync(DIR, { recursive: true, mode: 0o700 });
  chmodSync(DIR, 0o700);
}

export function writePrivate(path, text) {
  ensureDir();
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, text, { mode: 0o600 });
  renameSync(tmp, path);
  chmodSync(path, 0o600);
}

/** Config from environment variables (cloud), or null if none of them name a player.
 *  ONEFIX_PLAYERS is a JSON list of further players: [{name, steamid, matchAuthCode, firstShareCode}]. */
export function configFromEnv(env = process.env) {
  if (!env.ONEFIX_STEAMID && !env.ONEFIX_PLAYERS) return null;
  let players;
  if (env.ONEFIX_PLAYERS) {
    try {
      players = JSON.parse(env.ONEFIX_PLAYERS);
    } catch {
      throw new Error('ONEFIX_PLAYERS is not valid JSON.'); // never echo it: it holds auth codes
    }
  }
  return {
    name: env.ONEFIX_PLAYER_NAME,
    steamid: env.ONEFIX_STEAMID,
    webApiKey: env.STEAM_WEB_API_KEY,
    matchAuthCode: env.STEAM_MATCH_AUTH_CODE,
    firstShareCode: env.ONEFIX_FIRST_SHARE_CODE,
    demoDir: env.ONEFIX_DEMO_DIR || '/data/demos',
    players,
  };
}

export function loadConfig() {
  const fromEnv = configFromEnv();
  if (!fromEnv && !existsSync(CONFIG)) {
    writePrivate(CONFIG, JSON.stringify(CONFIG_TEMPLATE, null, 2) + '\n');
    throw new Error(`Created ${CONFIG}. Fill it in, then run again.`);
  }
  const c = fromEnv ?? JSON.parse(readFileSync(CONFIG, 'utf8'));
  // People who joined on the website (scripts/sync.sh exports them from the user database).
  const file = process.env.ONEFIX_PLAYERS_FILE;
  if (file && existsSync(file)) c.invitedPlayers = JSON.parse(readFileSync(file, 'utf8'));
  const config = validateConfig(c, fromEnv ? 'the environment variables' : CONFIG);
  for (const note of config.skipped) console.log(`Skipping invited player: ${note}`);
  return config;
}

function playerProblems(p, seen) {
  if (!p || typeof p !== 'object') return ['must be an object'];
  const out = [];
  if (typeof p.name !== 'string' || !p.name.trim() || p.name.length > 40) out.push('name must be 1-40 characters');
  if (!/^7656\d{13}$/.test(p.steamid ?? '')) out.push('steamid must be a 17-digit steamid64');
  else if (seen.has(p.steamid)) out.push('steamid is listed twice');
  if (!/^[0-9A-Z]{4}-[0-9A-Z]{5}-[0-9A-Z]{4}$/i.test(p.matchAuthCode ?? '')) out.push('matchAuthCode must look like XXXX-XXXXX-XXXX');
  if (!isShareCode(p.firstShareCode)) out.push('firstShareCode must look like CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx');
  return out;
}

/**
 * Check the raw config and return it in one shape: { webApiKey, demoDir, players: [...] }.
 * The top-level steamid / matchAuthCode / firstShareCode are the first player; `players`
 * lists any others. One Web API key reads every player's match history.
 * `invitedPlayers` joined through the website: a bad or repeated one is skipped (listed in
 * `skipped`) instead of stopping everyone's sync.
 * Error messages name the field, never its value.
 */
export function validateConfig(c, where) {
  const problems = [];
  if (!/^[0-9A-F]{32}$/i.test(c.webApiKey ?? '')) problems.push('webApiKey must be the 32-character key');
  if (!c.demoDir) problems.push('demoDir is missing');

  const players = [];
  if (c.steamid || c.matchAuthCode || c.firstShareCode) {
    players.push({ name: c.name || 'Me', steamid: c.steamid, matchAuthCode: c.matchAuthCode, firstShareCode: c.firstShareCode });
  }
  if (c.players !== undefined && !Array.isArray(c.players)) problems.push('players must be a list');
  else players.push(...(c.players ?? []));
  if (!players.length) problems.push('no players: set steamid, matchAuthCode and firstShareCode');

  const seen = new Set();
  players.forEach((p, i) => {
    const who = players.length > 1 ? `player ${i + 1}: ` : '';
    problems.push(...playerProblems(p, seen).map((x) => `${who}${x}`));
    if (p && typeof p === 'object') seen.add(p.steamid);
  });
  const skipped = [];
  for (const [i, p] of (Array.isArray(c.invitedPlayers) ? c.invitedPlayers : []).entries()) {
    const found = playerProblems(p, seen);
    if (found.length) {
      skipped.push(`#${i + 1}: ${found.join('; ')}`);
    } else {
      seen.add(p.steamid);
      players.push(p);
    }
  }
  if (problems.length) throw new Error(`Fix ${where}:\n  - ${problems.join('\n  - ')}`);
  return {
    webApiKey: c.webApiKey,
    demoDir: c.demoDir,
    skipped,
    players: players.map((p) => ({
      name: p.name.trim(), steamid: p.steamid, matchAuthCode: p.matchAuthCode, firstShareCode: p.firstShareCode,
    })),
  };
}

/** Saved token file first (it holds any renewed token), then BOT_REFRESH_TOKEN (cloud seed). */
export function loadToken() {
  if (existsSync(TOKEN)) return readFileSync(TOKEN, 'utf8').trim();
  if (process.env.BOT_REFRESH_TOKEN) return process.env.BOT_REFRESH_TOKEN.trim();
  throw new Error('No bot session yet. Run `npm run login` in ingest/ first (or set BOT_REFRESH_TOKEN).');
}

export function saveToken(token) {
  writePrivate(TOKEN, token + '\n');
}

export function loadState(primarySteamid) {
  const raw = existsSync(STATE) ? JSON.parse(readFileSync(STATE, 'utf8')) : null;
  return migrateState(raw, primarySteamid);
}

export function saveState(state) {
  writePrivate(STATE, JSON.stringify(state, null, 2) + '\n');
}
