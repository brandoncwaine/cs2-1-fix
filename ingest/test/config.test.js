import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

// Point the module at a throwaway config dir before importing it.
const dir = mkdtempSync(join(tmpdir(), 'onefix-cfg-'));
process.env.ONEFIX_CONFIG_DIR = dir;
const { configFromEnv, loadToken, validateConfig, TOKEN } = await import('../lib/config.js');

const ENV = {
  ONEFIX_STEAMID: '76561190000000000',
  STEAM_WEB_API_KEY: '0123456789ABCDEF0123456789ABCDEF',
  STEAM_MATCH_AUTH_CODE: 'ABCD-EFGHI-JKLM',
  ONEFIX_FIRST_SHARE_CODE: 'CSGO-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA',
};

test('no ONEFIX_STEAMID means no env config (fall back to the file)', () => {
  assert.equal(configFromEnv({}), null);
});

test('env config validates, with /data/demos as the default demo dir', () => {
  const c = configFromEnv(ENV);
  assert.equal(c.demoDir, '/data/demos');
  assert.doesNotThrow(() => validateConfig(c, 'env'));
});

test('missing secret in env config is reported without echoing values', () => {
  const c = configFromEnv({ ...ENV, STEAM_WEB_API_KEY: undefined });
  assert.throws(() => validateConfig(c, 'the environment variables'), (e) =>
    /webApiKey/.test(e.message) && !e.message.includes(ENV.STEAM_MATCH_AUTH_CODE));
});

test('saved token file wins over BOT_REFRESH_TOKEN (it holds renewed tokens)', () => {
  process.env.BOT_REFRESH_TOKEN = 'from-env';
  assert.equal(loadToken(), 'from-env');
  writeFileSync(TOKEN, 'renewed\n');
  assert.equal(loadToken(), 'renewed');
  delete process.env.BOT_REFRESH_TOKEN;
});

test('the top-level player comes first, then the players list', () => {
  const friend = { name: ' Sam ', steamid: '76561190000000001', matchAuthCode: 'ABCD-EFGHI-JKLM', firstShareCode: ENV.ONEFIX_FIRST_SHARE_CODE };
  const c = validateConfig(configFromEnv({ ...ENV, ONEFIX_PLAYER_NAME: 'Brandon', ONEFIX_PLAYERS: JSON.stringify([friend]) }), 'env');
  assert.deepEqual(c.players.map((p) => [p.name, p.steamid]), [['Brandon', ENV.ONEFIX_STEAMID], ['Sam', friend.steamid]]);
  assert.equal(c.webApiKey, ENV.STEAM_WEB_API_KEY);
});

test('a bad or repeated player is reported by position, without echoing values', () => {
  const dup = { name: 'Dup', steamid: ENV.ONEFIX_STEAMID, matchAuthCode: 'bad-code-value', firstShareCode: ENV.ONEFIX_FIRST_SHARE_CODE };
  const raw = configFromEnv({ ...ENV, ONEFIX_PLAYERS: JSON.stringify([dup]) });
  assert.throws(() => validateConfig(raw, 'env'), (e) =>
    /player 2: steamid is listed twice/.test(e.message) && /player 2: matchAuthCode/.test(e.message)
    && !e.message.includes('bad-code-value'));
});

test('ONEFIX_PLAYERS that is not JSON fails without echoing it', () => {
  assert.throws(() => configFromEnv({ ONEFIX_PLAYERS: '[{secret' }), (e) => !e.message.includes('secret'));
});

test('invited players are added; a bad or repeated one is skipped, not fatal', () => {
  const ok = { name: 'Kim', steamid: '76561190000000002', matchAuthCode: 'ABCD-EFGHI-JKLM', firstShareCode: ENV.ONEFIX_FIRST_SHARE_CODE };
  const repeat = { ...ok, name: 'Owner again', steamid: ENV.ONEFIX_STEAMID };
  const bad = { ...ok, steamid: '76561190000000003', matchAuthCode: 'secret-bad-value' };
  const c = validateConfig({ ...configFromEnv(ENV), invitedPlayers: [ok, repeat, bad] }, 'env');
  assert.deepEqual(c.players.map((p) => p.name), ['Me', 'Kim']);
  assert.equal(c.skipped.length, 2);
  assert.match(c.skipped[0], /#2: steamid is listed twice/);
  assert.ok(!c.skipped.join().includes('secret-bad-value'));
});

test('once the owner is in the user database, the top-level player is ignored', () => {
  const owner = { name: 'Brandon', steamid: ENV.ONEFIX_STEAMID, matchAuthCode: 'WXYZ-EFGHI-JKLM', firstShareCode: ENV.ONEFIX_FIRST_SHARE_CODE };
  const c = validateConfig({ ...configFromEnv(ENV), ignoreTopLevelPlayer: true, invitedPlayers: [owner] }, 'env');
  assert.deepEqual(c.players.map((p) => [p.name, p.matchAuthCode]), [['Brandon', 'WXYZ-EFGHI-JKLM']]);
  assert.deepEqual(c.skipped, []);
  // The owner deleted their data and nobody else has joined: nothing to sync, not an error.
  assert.deepEqual(validateConfig({ ...configFromEnv(ENV), ignoreTopLevelPlayer: true, invitedPlayers: [] }, 'env').players, []);
  assert.throws(() => validateConfig({ webApiKey: ENV.STEAM_WEB_API_KEY, demoDir: '/d' }, 'env'), /no players/);
});
