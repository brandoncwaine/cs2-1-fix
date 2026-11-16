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
