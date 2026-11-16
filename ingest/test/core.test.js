import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  decodeShareCode, demoFileName, demoUrlFromMatch, emptyState, idsFromFileName, isShareCode,
  newerShareCodes, pendingCodes,
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
  const state = emptyState();
  assert.deepEqual(pendingCodes(state, A, [B, C]), [A, B, C]);
  state.matches[A] = { status: 'downloaded' };
  state.matches[B] = { status: 'error' };
  state.matches[C] = { status: 'expired' };
  assert.deepEqual(pendingCodes(state, A, [B, C]), [B]);
});
