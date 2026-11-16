// Renders /api/data. All text goes in through textContent: nothing from the data is run as HTML.
'use strict';

const DETECTOR_TITLES = {
  untraded_death: 'Untraded deaths',
  isolated_opening_death: 'Isolated opening deaths',
};
const POLL_MS = 5000;

let state = { data: null, sync: { enabled: false, running: false, last_ok: null } };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const mapName = (map) => {
  const name = map.replace(/^[a-z]{2}_/, '');
  return name.charAt(0).toUpperCase() + name.slice(1);
};
const placeName = (place) => place.replace(/([a-z])([A-Z])/g, '$1 $2');
const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
// "match730_003853899879407419425_0218692445_271" -> the reservation id's last 6 digits
const shortMatch = (id) => {
  const m = /^match730_(\d+)_/.exec(id);
  return m ? `match …${m[1].slice(-6)}` : id;
};

function syncedText(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `Updated ${d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}`;
}

function cardHead(card) {
  const head = el('div', 'card-head');
  head.append(el('span', `side ${card.side}`, `${card.side} side`), el('span', 'rounds', plural(card.side_rounds, 'round')));
  return head;
}

function fixCard(card) {
  const box = el('article', 'card fix');
  box.append(cardHead(card));
  box.append(el('h3', '', `${DETECTOR_TITLES[card.detector] || card.detector} at ${placeName(card.place)}`));
  box.append(el('p', 'lead', card.fix_text));

  box.append(el('p', 'label', 'Drill'), el('p', '', card.drill));

  const m = card.metric;
  box.append(el('p', 'label', 'Target'));
  const metric = el('div', 'metric');
  const goal = el('b', 'goal', String(m.target));
  metric.append(el('b', '', String(m.baseline)), el('span', 'arrow', '→'), goal,
    el('span', 'muted', `per 100 ${card.side} rounds, over your next ${plural(m.window_matches, 'match', 'matches')}`));
  box.append(metric);

  box.append(el('p', 'label', 'Rounds to watch'));
  const list = el('ul', 'evidence');
  for (const e of card.evidence) {
    const li = el('li');
    const match = el('span', 'match', shortMatch(e.match_id));
    match.title = e.match_id;
    li.append(el('span', '', `Round ${e.round}, ${clock(e.t)} in`), match);
    list.append(li);
  }
  box.append(list);

  const s = card.stats;
  const details = el('details');
  details.append(el('summary', '', 'The numbers'));
  const dl = el('dl');
  const rows = [
    ['Rounds it happened in', `${s.fired_rounds} (in ${plural(s.matches_with_pattern, 'match', 'matches')})`],
    ['Won when it happened', `${s.win_rate_fired_pct}%`],
    [`Won in ${plural(s.comparison_rounds, 'comparison round')}`, `${s.win_rate_other_pct}%`],
    ['Rounds it may have cost', String(s.rounds_cost)],
    ['Chance this is luck (p)', `${s.p_value} (limit ${s.p_threshold})`],
    ['Patterns checked', String(s.patterns_tested)],
  ];
  for (const [k, v] of rows) dl.append(el('dt', '', k), el('dd', '', v));
  details.append(dl, el('p', 'note', s.note));
  box.append(details);
  return box;
}

function thinCard(card) {
  const box = el('article', 'card');
  box.append(cardHead(card));
  box.append(el('h3', '', 'Not enough rounds yet'));
  const need = card.side_rounds + card.rounds_needed;
  box.append(el('p', 'reason', `${plural(card.rounds_needed, 'more round')} needed before this side is analysed (${card.side_rounds} of ${need}).`));
  const bar = el('div', 'progress');
  bar.setAttribute('role', 'progressbar');
  bar.setAttribute('aria-valuemin', '0');
  bar.setAttribute('aria-valuemax', String(need));
  bar.setAttribute('aria-valuenow', String(card.side_rounds));
  const fill = el('div');
  fill.style.width = `${Math.round((100 * card.side_rounds) / need)}%`;
  bar.append(fill);
  box.append(bar);
  return box;
}

function noFixCard(card) {
  const box = el('article', 'card');
  box.append(cardHead(card));
  box.append(el('h3', '', 'No fix found'));
  box.append(el('p', 'reason', card.reason));
  return box;
}

function renderCard(card) {
  if (card.status === 'fix') return fixCard(card);
  if (card.status === 'insufficient_data') return thinCard(card);
  return noFixCard(card);
}

function problemText(p) {
  const out = [];
  if (p.history_error) out.push(`Steam match history could not be read: ${p.history_error}`);
  if (p.fetch_failed) out.push(`${plural(p.fetch_failed, 'demo')} could not be downloaded yet; they are retried on the next sync.`);
  if (p.parse_failed) out.push(`${plural(p.parse_failed, 'demo')} could not be read.`);
  if (p.expired) out.push(`${plural(p.expired, 'match', 'matches')} had no demo left on Valve's servers.`);
  return out;
}

function renderPlayer(player) {
  const main = document.getElementById('main');
  main.replaceChildren();
  const fixes = player.cards.filter((c) => c.status === 'fix').length;
  main.append(el('p', 'summary muted',
    `${plural(player.matches, 'match', 'matches')} · ${plural(player.rounds, 'round')} · ${plural(fixes, 'fix', 'fixes')}`));
  for (const text of problemText(player.problems || {})) main.append(el('p', 'notice', text));

  if (!player.cards.length) {
    const empty = el('div', 'empty');
    empty.append(el('p', '', 'No matches yet.'), el('p', 'muted', 'New matches are picked up on the next sync.'));
    main.append(empty);
    return;
  }

  const maps = new Map();
  for (const card of player.cards) {
    if (!maps.has(card.map)) maps.set(card.map, []);
    maps.get(card.map).push(card);
  }
  // Maps with a fix first, then the most-played.
  const weight = (cards) => [cards.some((c) => c.status === 'fix') ? 1 : 0, cards.reduce((n, c) => n + c.side_rounds, 0)];
  const ordered = [...maps.entries()].sort((a, b) => {
    const [fa, ra] = weight(a[1]);
    const [fb, rb] = weight(b[1]);
    return fb - fa || rb - ra || a[0].localeCompare(b[0]);
  });
  for (const [map, cards] of ordered) {
    const section = el('section', 'map');
    const head = el('div', 'map-head');
    head.append(el('h2', '', mapName(map)), el('span', 'muted', plural(cards.reduce((n, c) => n + c.side_rounds, 0), 'round')));
    const cells = el('div', 'cells');
    for (const side of ['T', 'CT']) {
      const card = cards.find((c) => c.side === side);
      if (card) cells.append(renderCard(card));
    }
    section.append(head, cells);
    main.append(section);
  }
}

function selectedPlayer(players) {
  const wanted = decodeURIComponent(location.hash.slice(1));
  return players.find((p) => p.steamid === wanted) || players[0];
}

function render() {
  const { data, sync } = state;
  const syncButton = document.getElementById('sync');
  syncButton.hidden = !sync.enabled;
  syncButton.disabled = sync.running;
  syncButton.textContent = sync.running ? 'Syncing…' : 'Sync now';
  const synced = document.getElementById('synced');
  synced.textContent = data ? syncedText(data.synced_at) : '';
  if (sync.last_ok === false && !sync.running) synced.textContent += ' · last sync had problems';

  const nav = document.getElementById('players');
  nav.replaceChildren();
  const main = document.getElementById('main');
  if (!data || !data.players.length) {
    main.replaceChildren();
    const empty = el('div', 'empty');
    empty.append(el('p', '', sync.running ? 'First sync is running…' : 'No data yet.'),
      el('p', 'muted', 'Downloading and reading demos takes a few minutes per match.'));
    main.append(empty);
    return;
  }
  const current = selectedPlayer(data.players);
  nav.hidden = data.players.length < 2;
  for (const p of data.players) {
    const b = el('button', '', p.name);
    b.type = 'button';
    b.setAttribute('aria-pressed', String(p === current));
    b.addEventListener('click', () => { location.hash = p.steamid; });
    nav.append(b);
  }
  renderPlayer(current);
}

let pollTimer = null;
async function load() {
  const res = await fetch('/api/data', { headers: { Accept: 'application/json' } });
  if (res.status === 401) { location.href = '/login'; return; }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  state = await res.json();
  render();
  clearTimeout(pollTimer);
  if (state.sync.running) pollTimer = setTimeout(() => load().catch(showError), POLL_MS);
}

function showError() {
  const main = document.getElementById('main');
  main.replaceChildren(el('p', 'notice', 'Could not load the data. Reload the page to try again.'));
}

document.getElementById('sync').addEventListener('click', async () => {
  const res = await fetch('/api/sync', { method: 'POST', headers: { 'X-Onefix': '1' } });
  if (res.status === 401) { location.href = '/login'; return; }
  load().catch(showError);
});
window.addEventListener('hashchange', render);
load().catch(showError);
