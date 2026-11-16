// Renders /api/data. All text goes in through textContent: nothing from the data is run as HTML.
'use strict';

const DETECTOR_TITLES = {
  untraded_death: 'Dying untraded',
  isolated_opening_death: 'Dying first and alone',
  missed_trade: 'Missed trades',
  repeek_death: 'Re-peeking after a kill',
};
const POLL_MS = 5000;

const MATCH_HISTORY_HELP = 'https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid=730&issueid=128';

let state = null;
let notice = '';
let lastView = null; // entrance animations play when this changes, not on every refresh

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

// A card: a banner with the map's picture, name and side, then the body the caller fills in.
// The picture comes from the class map-<name> in app.css; a map without one gets a plain banner.
function cardShell(card, extra = '') {
  const box = el('article', `card mapcard map-${mapName(card.map).toLowerCase().replace(/[^a-z0-9]/g, '')} ${extra}`.trim());
  const art = el('div', 'map-art');
  const name = el('div');
  name.append(el('b', '', mapName(card.map)), el('span', 'rounds', plural(card.side_rounds, 'round')));
  art.append(name, el('span', `side ${card.side}`, `${card.side} side`));
  const body = el('div', 'mapcard-body');
  box.append(art, body);
  return { box, body };
}

function fixCard(card) {
  const { box: shell, body: box } = cardShell(card, 'fix');
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
  return shell;
}

function thinCard(card) {
  const { box: shell, body: box } = cardShell(card);
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
  return shell;
}

function noFixCard(card) {
  const { box: shell, body: box } = cardShell(card);
  box.append(el('h3', '', 'No fix found'));
  box.append(el('p', 'reason', card.reason));
  return shell;
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
    // Each card's banner shows the map, so the heading is only for screen readers.
    const head = el('h2', 'visually-hidden', mapName(map));
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

// A modal window. `build(close)` returns its content. Esc, the backdrop and Cancel all close it.
function openModal(build, className = '') {
  const dialog = el('dialog', `modal ${className}`.trim());
  let closing = false;
  const close = () => {
    if (closing) return;
    closing = true;
    dialog.classList.add('closing');
    const done = () => { dialog.close(); dialog.remove(); };
    dialog.addEventListener('animationend', done, { once: true });
    setTimeout(done, 250); // in case animations are off
  };
  dialog.addEventListener('cancel', (event) => { event.preventDefault(); close(); });
  dialog.addEventListener('click', (event) => { if (event.target === dialog) close(); });
  dialog.append(build(close));
  document.body.append(dialog);
  dialog.showModal();
  return close;
}

function joinForm(me, close) {
  const updating = me.joined;
  const form = el('form', 'join');
  form.noValidate = true;
  const title = el('h2', '', updating ? 'Update your codes' : 'Connect your matches');
  form.append(title);
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

  if (!updating && !me.owner) field(form, 'invite', 'Invite code', 'From the person who invited you.', { type: 'password' });
  const name = field(form, 'name', 'Name to show', '', { maxLength: 40 });
  if (me.name) name.value = me.name;
  field(form, 'auth_code', 'Match history authentication code', 'Looks like XXXX-XXXXX-XXXX.');
  field(form, 'share_code', 'Share code of a recent match', 'Looks like CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx. Matches after this one are fetched.');

  const general = el('p', 'notice');
  general.hidden = true;
  general.setAttribute('role', 'alert');
  form.append(general);
  const actions = el('div', 'actions');
  if (close) {
    const cancel = el('button', '', 'Cancel');
    cancel.type = 'button';
    cancel.addEventListener('click', close);
    actions.append(cancel);
  }
  const submit = el('button', 'primary', updating ? 'Save' : 'Connect');
  submit.type = 'submit';
  actions.append(submit);
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
    if (close) close();
    notice = res.body.warning || (updating ? 'Saved.' : 'Connected. Your first sync has started; it takes a few minutes per match.');
    load().catch(showError);
  });
  return form;
}

function confirmModal(title, text, action) {
  openModal((close) => {
    const box = el('div', 'confirm');
    box.append(el('h2', '', title), el('p', '', text));
    const actions = el('div', 'actions');
    const cancel = el('button', '', 'Cancel');
    cancel.type = 'button';
    cancel.autofocus = true; // the safe choice gets the focus
    cancel.addEventListener('click', close);
    const yes = el('button', 'danger solid', 'Delete');
    yes.type = 'button';
    yes.addEventListener('click', async () => {
      yes.disabled = true;
      yes.textContent = 'Deleting…';
      await action();
      close();
    });
    actions.append(cancel, yes);
    box.append(actions);
    return box;
  }, 'narrow');
}

function renderAccount() {
  const box = document.getElementById('account');
  box.replaceChildren();
  const { me, viewing, players } = state;
  if (!me.joined && viewing === me.steamid) return;
  if (viewing === me.steamid) {
    box.append(el('span', 'who', `Signed in as ${me.name}`));
    if (me.invited) {
      const edit = el('button', 'quiet', 'Update my codes');
      edit.type = 'button';
      edit.addEventListener('click', () => openModal((close) => joinForm(state.me, close)));
      const leave = el('button', 'quiet danger', 'Delete my data');
      leave.type = 'button';
      leave.addEventListener('click', () => confirmModal('Delete your data?',
        'This deletes your matches, cards and Steam codes from this site. It cannot be undone.', async () => {
          await post('/api/leave');
          notice = 'Your data is being deleted.';
          await load().catch(showError);
        }));
      box.append(edit, leave);
    }
    return;
  }
  const other = (players || []).find((p) => p.steamid === viewing);
  if (other && other.invited) {
    box.append(el('span', 'who', `Viewing ${other.name}`));
    const remove = el('button', 'quiet danger', 'Remove this person');
    remove.type = 'button';
    remove.addEventListener('click', () => confirmModal(`Remove ${other.name}?`,
      `This deletes ${other.name}'s matches, cards and Steam codes from this site. It cannot be undone.`, async () => {
        await post('/api/remove', { steamid: viewing });
        location.hash = '';
        await load().catch(showError);
      }));
    box.append(remove);
  }
}

function render() {
  const { me, sync, player, players, viewing } = state;
  const syncButton = document.getElementById('sync');
  syncButton.hidden = !sync.enabled || !(me.joined || me.owner);
  syncButton.disabled = sync.running;
  syncButton.classList.toggle('busy', sync.running);
  syncButton.textContent = sync.running ? 'Syncing…' : 'Sync now';
  const synced = document.getElementById('synced');
  synced.textContent = state.synced_at && me.joined ? syncedText(state.synced_at) : '';
  if (sync.last_ok === false && !sync.running && me.joined) synced.textContent += ' · last sync had problems';

  const nav = document.getElementById('players');
  nav.hidden = !players || players.length < 2;
  const tabs = (players || []).map((p) => `${p.steamid}:${p.name}`).join('|');
  if (nav.dataset.tabs !== tabs) { // rebuild only when the people change, so tabs do not flicker
    nav.dataset.tabs = tabs;
    nav.replaceChildren();
    for (const p of players || []) {
      const b = el('button', '', p.name);
      b.type = 'button';
      b.dataset.steamid = p.steamid;
      b.addEventListener('click', () => { location.hash = p.steamid; });
      nav.append(b);
    }
  }
  for (const b of nav.children) b.setAttribute('aria-pressed', String(b.dataset.steamid === viewing));

  const main = document.getElementById('main');
  const mine = viewing === me.steamid;
  const kind = !me.joined && mine ? 'join' : player ? 'cards' : 'empty';
  // Do not rebuild the first-time form while someone is typing in it.
  if (kind === 'join' && lastView === `${viewing}|join` && main.querySelector('form.join')) {
    renderAccount();
    return;
  }
  const view = `${viewing}|${kind}`;
  main.classList.remove('enter');
  if (view !== lastView) {
    void main.offsetWidth; // restart the animation
    main.classList.add('enter');
    lastView = view;
  }
  main.replaceChildren();
  if (notice) main.append(el('p', 'notice good', notice));
  if (kind === 'join') {
    if (me.owner || state.joining_open) {
      main.append(joinForm(me, null));
    } else {
      const closed = el('div', 'empty');
      closed.append(el('p', '', 'This site is invite only and is not taking new people right now.'),
        el('p', 'muted', 'Ask the person who sent you the link.'));
      main.append(closed);
    }
  } else if (kind === 'cards') {
    renderPlayer(player, main);
  } else {
    const empty = el('div', 'empty');
    empty.append(el('p', '', sync.running ? 'Sync is running…' : 'No matches yet.'),
      el('p', 'muted', 'Downloading and reading demos takes a few minutes per match. This page updates by itself.'));
    main.append(empty);
  }
  main.querySelectorAll('.card').forEach((card, i) => card.style.setProperty('--i', String(i)));
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
window.addEventListener('hashchange', () => { notice = ''; load().catch(showError); });
load().catch(showError);
