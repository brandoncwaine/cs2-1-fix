import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  decodeShareCode, demoFileName, buildManifest, demoUrlFromMatch, emptyPlayerState, emptyState, idsFromFileName, isShareCode,
  migrateState, newerShareCodes, pendingCodes,
} from '../lib/core.js';

// Example from the csgo-sharecode README (not a real user's match).
const CODE = 'CSGO-GADqf-jjyJ8-cSP2r-smZRo-TO2xK';

test('decodes a share code into match, reservation and tv port', () => {
  assert.deepEqual(decodeShareCode(CODE), {
    matchId: '3230642215713767580', reservationId: '3230647599455273103', tvPort: 55788,
  });
});

test('rejects things that are not share codes', () => {
  assert.equal(isShareCode('CSGO-abc'), false);
  assert.equal(isShareCode('n/a'), false);
  assert.throws(() => decodeShareCode('nope'));
});

test('demo file name matches the CS2 client naming', () => {
  const url = 'http://replay390.valve.net/730/003848141567361548483_1426637720.dem.bz2';
  assert.equal(demoFileName(url), 'match730_003848141567361548483_1426637720_390.dem');
  assert.deepEqual(idsFromFileName(demoFileName(url)),
    { reservationId: '3848141567361548483', tvPort: 1426637720 });
  assert.throws(() => demoFileName('http://evil.example.com/x.dem.bz2'));
});

test('demo URL is the last round stats entry with a map', () => {
  const match = { roundstatsall: [{ map: '' }, { map: 'http://replay1.valve.net/730/1_2.dem.bz2' }, {}] };
  assert.equal(demoUrlFromMatch(match), 'http://replay1.valve.net/730/1_2.dem.bz2');
  assert.equal(demoUrlFromMatch({ roundstatsall: [] }), null);
});

function fakeFetch(chain, calls = []) {
  return async (url) => {
    const known = new URL(url).searchParams.get('knowncode');
    calls.push(url);
    const next = chain[known];
    if (next === undefined) return { status: 202, json: async () => ({ result: { nextcode: 'n/a' } }) };
    if (typeof next === 'number') return { status: next, json: async () => ({}) };
    return { status: 200, json: async () => ({ result: { nextcode: next } }) };
  };
}

const A = 'CSGO-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA';
const B = 'CSGO-BBBBB-BBBBB-BBBBB-BBBBB-BBBBB';
const C = 'CSGO-CCCCC-CCCCC-CCCCC-CCCCC-CCCCC';
const args = { key: 'k', steamid: '1', authCode: 'x' };

test('walks share codes forward until Steam says n/a', async () => {
  const codes = await newerShareCodes({ ...args, knownCode: A, fetchImpl: fakeFetch({ [A]: B, [B]: C }) });
  assert.deepEqual(codes, [B, C]);
});

test('passes key, steamid, auth code and known code to Steam', async () => {
  const calls = [];
  await newerShareCodes({ ...args, knownCode: A, fetchImpl: fakeFetch({}, calls) });
  const p = new URL(calls[0]).searchParams;
  assert.deepEqual([p.get('key'), p.get('steamid'), p.get('steamidkey'), p.get('knowncode')], ['k', '1', 'x', A]);
});

test('clear errors for bad credentials and unknown codes', async () => {
  await assert.rejects(newerShareCodes({ ...args, knownCode: A, fetchImpl: fakeFetch({ [A]: 403 }) }), /403/);
  await assert.rejects(newerShareCodes({ ...args, knownCode: A, fetchImpl: fakeFetch({ [A]: 412 }) }), /412/);
});

test('pending codes include the starting code once, and retry errors only', () => {
  const state = emptyPlayerState();
  assert.deepEqual(pendingCodes(state, A, [B, C]), [A, B, C]);
  state.matches[A] = { status: 'downloaded' };
  state.matches[B] = { status: 'error' };
  state.matches[C] = { status: 'expired' };
  assert.deepEqual(pendingCodes(state, A, [B, C]), [B]);
});

test('an old single-player state file becomes the first player\'s state', () => {
  const old = { lastCode: B, matches: { [A]: { status: 'downloaded', file: '/d/a.dem' } } };
  assert.deepEqual(migrateState(old, '1'), { players: { 1: old } });
  const current = { players: { 2: emptyPlayerState() } };
  assert.equal(migrateState(current, '1'), current);
  assert.deepEqual(migrateState(null, '1'), emptyState());
});

test('manifest lists existing demos and problems per player, without codes or secrets', () => {
  const config = { webApiKey: 'SECRETKEY', players: [
    { name: 'Ann', steamid: '1', matchAuthCode: 'AUTH-SECRET', firstShareCode: A },
    { name: 'Bob', steamid: '2', matchAuthCode: 'AUTH-OTHER', firstShareCode: B },
  ] };
  const state = { players: { 1: { lastCode: C, error: { message: `unknown code ${A} (412)` }, matches: {
    [A]: { status: 'downloaded', file: '/d/b.dem' },
    [B]: { status: 'downloaded', file: '/d/gone.dem' },
    [C]: { status: 'expired' },
  } } } };
  const m = buildManifest(config, state, (f) => f !== '/d/gone.dem');
  assert.deepEqual(m.players[0], {
    steamid: '1', name: 'Ann', demos: ['/d/b.dem'], expired: 1, failed: 0, history_error: 'unknown code CSGO-… (412)',
  });
  assert.deepEqual(m.players[1], { steamid: '2', name: 'Bob', demos: [], expired: 0, failed: 0, history_error: null });
  assert.doesNotMatch(JSON.stringify(m), /SECRET|AUTH-|CSGO-[A-Za-z0-9]{5}/);
});
