// Fetch any new CS2 match demos for the configured player.
//   cd ingest && npm run sync
// 1. Steam Web API: walk the player's share codes forward from the last one handled.
// 2. Bot account (saved session from `npm run login`) asks the CS2 game coordinator for each
//    match's demo URL.
// 3. Download from replay*.valve.net, decompress, save under demoDir with the client's file name.
// State is saved after every match, so an interrupted run resumes where it stopped.
import { spawnSync } from 'node:child_process';
import { createWriteStream, existsSync, mkdirSync, renameSync, statSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

import GlobalOffensive from 'globaloffensive';
import SteamUser from 'steam-user';

import { loadConfig, loadState, loadToken, saveState, saveToken } from './lib/config.js';
import { decodeShareCode, demoFileName, demoUrlFromMatch, newerShareCodes, pendingCodes } from './lib/core.js';

const GC_TIMEOUT_MS = 60_000;
const MATCH_TIMEOUT_MS = 30_000;
const BETWEEN_REQUESTS_MS = 2_000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function withTimeout(promise, ms, what) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out waiting for ${what}`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function connectBot() {
  const user = new SteamUser({ renewRefreshTokens: true });
  const csgo = new GlobalOffensive(user);
  user.on('refreshToken', saveToken);
  const ready = new Promise((resolve, reject) => {
    user.once('error', (err) => reject(new Error(`bot login failed: ${err.message} (run npm run login again?)`)));
    csgo.once('connectedToGC', resolve);
    user.once('loggedOn', () => user.gamesPlayed([730]));
  });
  user.logOn({ refreshToken: loadToken(), machineName: 'onefix-ingest' });
  await withTimeout(ready, GC_TIMEOUT_MS, 'the CS2 game coordinator');
  return { user, csgo };
}

function requestMatch(csgo, code) {
  const { matchId } = decodeShareCode(code);
  return withTimeout(new Promise((resolve) => {
    const onList = (matches) => {
      const m = (matches ?? []).find((x) => String(x.matchid) === matchId);
      if (m) {
        csgo.removeListener('matchList', onList);
        resolve(m);
      }
    };
    csgo.on('matchList', onList);
    csgo.requestGame(code);
  }), MATCH_TIMEOUT_MS, `match info for ${code}`);
}

async function download(url, demoDir) {
  const name = demoFileName(url); // also validates the URL is a Valve replay server
  const dest = join(demoDir, name);
  if (existsSync(dest)) return { path: dest, skipped: true };
  mkdirSync(demoDir, { recursive: true });
  const bz2 = `${dest}.bz2.part`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`download failed: HTTP ${res.status}`);
  await pipeline(Readable.fromWeb(res.body), createWriteStream(bz2));
  // bunzip2 ships with macOS and Linux. -c writes to stdout so we control the output name.
  const out = `${dest}.part`;
  const r = spawnSync('sh', ['-c', 'bunzip2 -c "$1" > "$2"', 'sh', bz2, out]);
  unlinkSync(bz2);
  if (r.status !== 0) {
    if (existsSync(out)) unlinkSync(out);
    throw new Error(`bunzip2 failed: ${r.stderr}`);
  }
  renameSync(out, dest);
  return { path: dest, skipped: false };
}

async function main() {
  const config = loadConfig();
  const demoDir = config.demoDir.replace(/^~(?=\/)/, process.env.HOME);
  const state = loadState();
  const knownCode = state.lastCode || config.firstShareCode;

  console.log(`Checking Steam for matches after ${knownCode}...`);
  const newer = await newerShareCodes({
    key: config.webApiKey, steamid: config.steamid, authCode: config.matchAuthCode, knownCode,
  });
  if (newer.length) state.lastCode = newer[newer.length - 1];
  else if (!state.lastCode) state.lastCode = knownCode;
  saveState(state);

  const todo = pendingCodes(state, knownCode, newer);
  console.log(`${newer.length} new match(es) on Steam; ${todo.length} to fetch.`);
  if (!todo.length) return;

  const { user, csgo } = await connectBot();
  console.log('Connected to the CS2 game coordinator.');
  const fetched = [];
  try {
    for (const code of todo) {
      try {
        const match = await requestMatch(csgo, code);
        const url = demoUrlFromMatch(match);
        if (!url) {
          state.matches[code] = { status: 'expired', at: new Date().toISOString() };
          console.log(`  ${code}: no demo (Valve deletes demos after a few weeks)`);
        } else {
          const { path, skipped } = await download(url, demoDir);
          state.matches[code] = { status: 'downloaded', file: path, at: new Date().toISOString() };
          console.log(`  ${code}: ${skipped ? 'already have' : 'saved'} ${path} (${(statSync(path).size / 1e6).toFixed(0)} MB)`);
          if (!skipped) fetched.push(path);
        }
      } catch (err) {
        state.matches[code] = { status: 'error', error: err.message, at: new Date().toISOString() };
        console.log(`  ${code}: failed, will retry next run (${err.message})`);
      }
      saveState(state);
      await sleep(BETWEEN_REQUESTS_MS);
    }
  } finally {
    user.logOff();
  }
  console.log(`Done: ${fetched.length} new demo(s).`);
  for (const f of fetched) console.log(`NEW ${f}`);
}

main().then(() => setTimeout(() => process.exit(0), 500)).catch((err) => {
  console.error(err.message);
  process.exit(1);
});
