// Config, secrets and state live OUTSIDE the repo, in ~/.config/onefix/, readable only by the user.
import { chmodSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

import { emptyState, isShareCode } from './core.js';

export const DIR = process.env.ONEFIX_CONFIG_DIR || join(homedir(), '.config', 'onefix');
export const CONFIG = join(DIR, 'steam.json');
export const TOKEN = join(DIR, 'bot-refresh-token');
export const STATE = join(DIR, 'ingest-state.json');

export const CONFIG_TEMPLATE = {
  steamid: 'your main account steamid64 (17 digits)',
  webApiKey: 'from https://steamcommunity.com/dev/apikey',
  matchAuthCode: 'XXXX-XXXXX-XXXX from Steam Support > CS2 > Access to Your Match History',
  firstShareCode: 'CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx (any recent match of yours)',
  demoDir: join(homedir(), 'Documents', 'cs2-demos', 'own'),
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

/** Config from environment variables (cloud), or null if ONEFIX_STEAMID is not set. */
export function configFromEnv(env = process.env) {
  if (!env.ONEFIX_STEAMID) return null;
  return {
    steamid: env.ONEFIX_STEAMID,
    webApiKey: env.STEAM_WEB_API_KEY,
    matchAuthCode: env.STEAM_MATCH_AUTH_CODE,
    firstShareCode: env.ONEFIX_FIRST_SHARE_CODE,
    demoDir: env.ONEFIX_DEMO_DIR || '/data/demos',
  };
}

export function loadConfig() {
  const fromEnv = configFromEnv();
  if (!fromEnv && !existsSync(CONFIG)) {
    writePrivate(CONFIG, JSON.stringify(CONFIG_TEMPLATE, null, 2) + '\n');
    throw new Error(`Created ${CONFIG}. Fill it in, then run again.`);
  }
  const c = fromEnv ?? JSON.parse(readFileSync(CONFIG, 'utf8'));
  return validateConfig(c, fromEnv ? 'the environment variables' : CONFIG);
}

export function validateConfig(c, where) {
  const problems = [];
  if (!/^7656\d{13}$/.test(c.steamid ?? '')) problems.push('steamid must be a 17-digit steamid64');
  if (!/^[0-9A-F]{32}$/i.test(c.webApiKey ?? '')) problems.push('webApiKey must be the 32-character key');
  if (!/^[0-9A-Z]{4}-[0-9A-Z]{5}-[0-9A-Z]{4}$/i.test(c.matchAuthCode ?? '')) problems.push('matchAuthCode must look like XXXX-XXXXX-XXXX');
  if (!isShareCode(c.firstShareCode)) problems.push('firstShareCode must look like CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx');
  if (!c.demoDir) problems.push('demoDir is missing');
  if (problems.length) throw new Error(`Fix ${where}:\n  - ${problems.join('\n  - ')}`);
  return c;
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

export function loadState() {
  return existsSync(STATE) ? JSON.parse(readFileSync(STATE, 'utf8')) : emptyState();
}

export function saveState(state) {
  writePrivate(STATE, JSON.stringify(state, null, 2) + '\n');
}
