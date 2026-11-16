// Renders /api/data. All text goes in through textContent: nothing from the data is run as HTML.
'use strict';

const DETECTOR_TITLES = {
  untraded_death: 'Untraded deaths',
  isolated_opening_death: 'Isolated opening deaths',
};
const POLL_MS = 5000;

const MATCH_HISTORY_HELP = 'https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid=730&issueid=128';

let state = null;
let editing = false; // the signed-in person is changing their codes
let confirming = null; // which delete button is showing "Are you sure?"

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

function renderPlayer(player, main) {
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

async function post(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'X-Onefix': '1', 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (res.status === 401) { location.href = '/login'; return null; }
  return { status: res.status, body: await res.json().catch(() => ({})) };
}

function field(form, name, label, hint, attrs = {}) {
  const id = `f-${name}`;
  const lab = el('label', '', label);
  lab.htmlFor = id;
  const input = el('input');
  Object.assign(input, { id, name, required: true, autocomplete: 'off', spellcheck: false }, attrs);
  form.append(lab, input);
  if (hint) form.append(el('p', 'hint', hint));
  const error = el('p', 'field-error');
  error.id = `${id}-error`;
  error.hidden = true;
  form.append(error);
  return input;
}

function joinForm(me) {
  const updating = me.joined;
  const form = el('form', 'join');
  form.noValidate = true;
  form.append(el('h2', '', updating ? 'Update your codes' : 'Connect your matches'));
  form.append(el('p', 'muted', updating
    ? 'Use this if you made a new authentication code on Steam, or want a different name.'
    : 'You are signed in. To find your matches, this site needs two codes from Steam.'));
  const steps = el('ol');
  const first = el('li');
  const link = el('a', '', "Open Steam's match history page");
  link.href = MATCH_HISTORY_HELP;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  first.append(link, ' and sign in.');
  steps.append(first,
    el('li', '', 'Create an authentication code and copy it.'),
    el('li', '', 'Copy the share code of your most recent match from the same page.'));
  form.append(steps);

  if (!updating) field(form, 'invite', 'Invite code', 'From the person who invited you.', { type: 'password' });
  const name = field(form, 'name', 'Name to show', '', { maxLength: 40 });
  if (me.name) name.value = me.name;
  field(form, 'auth_code', 'Match history authentication code', 'Looks like XXXX-XXXXX-XXXX.');
  field(form, 'share_code', 'Share code of a recent match', 'Looks like CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx. Matches after this one are fetched.');

  const general = el('p', 'notice');
  general.hidden = true;
  general.setAttribute('role', 'alert');
  form.append(general);
  const actions = el('div', 'actions');
  const submit = el('button', 'primary', updating ? 'Save' : 'Connect');
  submit.type = 'submit';
  actions.append(submit);
  if (updating) {
    const cancel = el('button', '', 'Cancel');
    cancel.type = 'button';
    cancel.addEventListener('click', () => { editing = false; render(); });
    actions.append(cancel);
  }
  form.append(actions);
  form.append(el('p', 'promise',
    'Never type your Steam password here: this site does not ask for it. The codes only let it read your '
    + 'match list. You see only your own results; the site owner can see them too. You can delete your data '
    + 'at any time, and making a new authentication code on Steam cuts off access.'));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    submit.textContent = 'Checking with Steam…';
    general.hidden = true;
    const values = Object.fromEntries(new FormData(form).entries());
    const res = await post('/api/join', values).catch(() => ({ status: 0, body: {} }));
    if (!res) return;
    submit.disabled = false;
    submit.textContent = updating ? 'Save' : 'Connect';
    const problems = res.body.fields || {};
    let firstBad = null;
    for (const input of form.querySelectorAll('input')) {
      const error = document.getElementById(`${input.id}-error`);
      const text = problems[input.name];
      error.hidden = !text;
      error.textContent = text || '';
      input.setAttribute('aria-invalid', String(Boolean(text)));
      if (text) input.setAttribute('aria-describedby', error.id); else input.removeAttribute('aria-describedby');
      if (text && !firstBad) firstBad = input;
    }
    if (firstBad) { firstBad.focus(); return; }
    if (res.status !== 200) {
      general.textContent = res.body.error || 'That did not work. Try again in a minute.';
      general.hidden = false;
      return;
    }
    editing = false;
    notice = res.body.warning || (updating ? 'Saved.' : 'Connected. Your first sync has started; it takes a few minutes per match.');
    load().catch(showError);
  });
  return form;
}

let notice = '';

function confirmButton(key, label, question, action) {
  const wrap = el('span');
  if (confirming !== key) {
    const b = el('button', 'quiet danger', label);
    b.type = 'button';
    b.addEventListener('click', () => { confirming = key; render(); });
    wrap.append(b);
    return wrap;
  }
  const yes = el('button', 'danger', 'Yes, delete');
  yes.type = 'button';
  yes.addEventListener('click', async () => { confirming = null; yes.disabled = true; await action(); });
  const no = el('button', '', 'Cancel');
  no.type = 'button';
  no.addEventListener('click', () => { confirming = null; render(); });
  wrap.append(el('span', 'muted', `${question} `), yes, ' ', no);
  return wrap;
}

function renderAccount() {
  const box = document.getElementById('account');
  box.replaceChildren();
  const { me, viewing, players } = state;
  if (!me.joined || editing) return;
  if (viewing === me.steamid) {
    box.append(el('span', 'who', `Signed in as ${me.name}`));
    if (me.invited) {
      const edit = el('button', 'quiet', 'Update my codes');
      edit.type = 'button';
      edit.addEventListener('click', () => { editing = true; render(); });
      box.append(edit, confirmButton('leave', 'Delete my data', 'Delete your matches, cards and codes?', async () => {
        await post('/api/leave');
        notice = 'Your data is being deleted.';
        load().catch(showError);
      }));
    }
    return;
  }
  const other = (players || []).find((p) => p.steamid === viewing);
  if (other && other.invited) {
    box.append(el('span', 'who', `Viewing ${other.name}`));
    box.append(confirmButton('remove', 'Remove this person', `Delete ${other.name}'s matches, cards and codes?`, async () => {
      await post('/api/remove', { steamid: viewing });
      location.hash = '';
      load().catch(showError);
    }));
  }
}

function render() {
  const { me, sync, player, players, viewing } = state;
  const syncButton = document.getElementById('sync');
  syncButton.hidden = !sync.enabled || !me.joined;
  syncButton.disabled = sync.running;
  syncButton.textContent = sync.running ? 'Syncing…' : 'Sync now';
  const synced = document.getElementById('synced');
  synced.textContent = state.synced_at && me.joined ? syncedText(state.synced_at) : '';
  if (sync.last_ok === false && !sync.running && me.joined) synced.textContent += ' · last sync had problems';

  const nav = document.getElementById('players');
  nav.replaceChildren();
  nav.hidden = !players || players.length < 2 || editing;
  for (const p of players || []) {
    const b = el('button', '', p.name);
    b.type = 'button';
    b.setAttribute('aria-pressed', String(p.steamid === viewing));
    b.addEventListener('click', () => { location.hash = p.steamid; });
    nav.append(b);
  }

  const main = document.getElementById('main');
  main.replaceChildren();
  if (notice) main.append(el('p', 'notice', notice));
  if (!me.joined || editing) {
    if (me.joined || state.joining_open) {
      main.append(joinForm(me));
    } else {
      const closed = el('div', 'empty');
      closed.append(el('p', '', 'This site is invite only and is not taking new people right now.'),
        el('p', 'muted', 'Ask the person who sent you the link.'));
      main.append(closed);
    }
  } else if (player) {
    renderPlayer(player, main);
  } else {
    const empty = el('div', 'empty');
    empty.append(el('p', '', sync.running ? 'Sync is running…' : 'No matches yet.'),
      el('p', 'muted', 'Downloading and reading demos takes a few minutes per match. This page updates by itself.'));
    main.append(empty);
  }
  renderAccount();
}

let pollTimer = null;
async function load() {
  const wanted = decodeURIComponent(location.hash.slice(1));
  const query = /^\d{17}$/.test(wanted) ? `?player=${wanted}` : '';
  const res = await fetch(`/api/data${query}`, { headers: { Accept: 'application/json' } });
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
  await post('/api/sync');
  load().catch(showError);
});
window.addEventListener('hashchange', () => { notice = ''; confirming = null; load().catch(showError); });
load().catch(showError);
