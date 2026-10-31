import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const TEMPLATE = readFileSync(join(ROOT, 'Game_Logic', 'templates', 'index.html'), 'utf8');
const SAVE_PREFIX = 'dead-but-dreaming:save:';
const URLS = {
  api_random_name: '/api/random-name', api_new_game: '/api/new-game', api_play: '/api/play', api_account: '/api/account',
  api_register: '/api/register', api_login: '/api/login', api_logout: '/api/logout', api_sync: '/api/sync',
  api_reset_question: '/api/reset-question', api_reset_password: '/api/reset-password', sso_login: '/sso/login',
  api_portfolio_link: '/api/portfolio/link', api_portfolio_new: '/api/portfolio/new', api_stats: '/api/stats',
};
const STYLES = ['Cthulhu', 'Dagon'];
const DIFFICULTIES = [['quick', 'Quick and Easy'], ['recommended', 'Recommended'], ['eternal', 'Eternal']];
const MODES = [['idle', 'Idle Mode'], ['clicker', 'Clicker Mode']];
const GROUPS = [['all', 'All'], ['quick', 'Quick and Easy']];
// Ids ending in _clicker are Clicker Mode achievements, like the real ones
const ACHIEVEMENTS = { all: ['cult_leader', 'goo_manager'], quick: ['devour_quick', 'quick_fast_clicker'] };

/* The page the way Flask renders it. Any Jinja left over means the template changed under these tests. */
function page({ portfolio = false } = {}) {
  const loop = (html, header, items, fill) => html.replace(
    new RegExp(`{% for ${header} %}([\\s\\S]*?){% endfor %}`), (_, item) => items.map((entry) => fill(item, entry)).join(''));
  let html = TEMPLATE.slice(TEMPLATE.indexOf('<body'), TEMPLATE.indexOf('</body>') + 7)
    .replace(/{{ url_for\('(\w+)'\) }}/g, (_, endpoint) => URLS[endpoint])
    .replace(/{%- if portfolio %}([\s\S]*?){% endif %}/, (_, attributes) =>
      (portfolio ? attributes.replace('{{ portfolio_url }}', 'http://portfolio.test') : ''))
    .replace('{{ max_name_length }}', '20');
  html = loop(html, 'name in great_old_ones', STYLES,
    (item, name) => item.replace('{{ name|lower }}', name.toLowerCase()).replace('{{ name }}', name));
  html = loop(html, 'question in questions', ['Pet?'], (item, question) => item.replace('{{ question }}', question));
  html = loop(html, 'key, difficulty in difficulties.items\\(\\)', DIFFICULTIES, (item, [key, name]) => item
    .replace('{{ key }}', key).replace('{% if key == default_difficulty %} selected{% endif %}',
      key === 'recommended' ? ' selected' : '').replace('{{ difficulty.name }} ({{ difficulty.estimate }})', name));
  // The groups loop holds the achievements loop, so that one is marked first and filled per group. The groups
  // loop appears twice: the filter buttons and the groups themselves.
  html = html.replace(/{% for id, achievement in members\.items\(\) %}([\s\S]*?){% endfor %}/, '__ITEMS__$1__END__');
  const group = (item, [key, title]) => item
    .replace(/__ITEMS__([\s\S]*?)__END__/, (_, entry) => ACHIEVEMENTS[key].map((id) => entry
      .replace('{{ id }}', id).replace('{{ achievement.name }}', id).replace('{{ achievement.description }}', '')
      .replace("{{ achievement.mode or '' }}", id.endsWith('_clicker') ? 'clicker' : '')).join(''))
    .replaceAll('{{ key }}', key).replaceAll('{{ title }}', title);
  // The modes loop appears twice too: the achievements mode filter and the New Game cards.
  const mode = (item, [key, name]) => item
    .replace('{{ key }}', key).replace('{% if key == default_mode %} checked{% endif %}', key === 'idle' ? ' checked' : '')
    .replace('{{ mode.name }}', name).replace('{{ mode.reason }}', `${name} reason`);
  html = loop(html, 'key, mode in modes.items\\(\\)', MODES, mode);
  html = loop(html, 'key, mode in modes.items\\(\\)', MODES, mode);
  html = loop(html, 'key, \\(title, members\\) in groups.items\\(\\)', GROUPS, group);
  html = loop(html, 'key, \\(title, members\\) in groups.items\\(\\)', GROUPS, group);
  if (/{{|{%/.test(html)) throw new Error(`Template tags the tests don't fill: ${html.match(/{[{%][^}]*[}%]}/)[0]}`);
  const body = new DOMParser().parseFromString(`<html>${html}</html>`, 'text/html').body;
  document.documentElement.replaceChild(document.importNode(body, true), document.body);
}

function reply(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function resource(key, overrides = {}) {
  return { key, name: key, manager_name: `${key} keeper`, unlocked: false, rate: 1, processing: false, progress: 0,
    cycle_seconds: 2, solid_bar: false, unlock_cost: 30, can_unlock: false, manager_cost: 10, has_manager: false,
    can_hire: false, ...overrides };
}

function upgrade(id, type, resourceKey, cost, affordable = false) {
  return { id, name: id, description: `${type} for ${resourceKey}`, type, resource: resourceKey, resource_name: resourceKey,
    cost, affordable };
}

function view(overrides = {}) {
  return {
    player_name: 'Dagon', sanity: 1234, difficulty_name: 'Quick and Easy', difficulty: 'Quick and Easy (15 min)',
    mode: 'Idle Mode', clicker: false,
    dream_time: '0m 05s', ending: false, endless: false, worlds_devoured: 0, devoured_time: null,
    resources: [resource('cultists', { unlocked: true }), resource('tomes')],
    upgrades: [upgrade('cultists_speed_2x', 'speed', 'cultists', 50), upgrade('cultists_prod_2x', 'production', 'cultists', 15, true)],
    ...overrides,
  };
}

const save = (name = 'Dagon', world = 'a') => ({ player_name: name, world_id: world.repeat(16), signature: 'signed' });
// Signed by the server over its contents, so two records with the same contents share a signature
const record = (achievements = []) => ({ achievements, devours: [], names: [], signature: `signed ${achievements.join()}` });

function played(overrides = {}, extra = {}) {
  return { save: save(), view: view(overrides), new_achievements: [], record: record(), ...extra };
}

const listeners = [];
let server;

beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
  for (const target of [window, document]) {
    const listen = target.addEventListener;
    vi.spyOn(target, 'addEventListener').mockImplementation(function track(type, listener, options) {
      listeners.push([target, type, listener, options]);
      return listen.call(this, type, listener, options);
    });
  }
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  for (const [target, type, listener, options] of listeners.splice(0)) target.removeEventListener(type, listener, options);
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function fakeServer(routes) {
  const calls = [];
  const fetch = vi.fn(async (url, options = {}) => {
    const method = options.method || 'GET';
    const body = options.body === undefined ? undefined : JSON.parse(options.body);
    calls.push({ method, url, body });
    const handler = routes[`${method} ${url}`];
    if (!handler) return reply(404, { error: `${url} is not faked` });
    const result = typeof handler === 'function' ? await handler(body) : handler;
    return typeof result?.json === 'function' ? result : reply(200, result);
  });
  vi.stubGlobal('fetch', fetch);
  return { fetch, calls, routes };
}

const flush = () => vi.advanceTimersByTimeAsync(0);

async function boot({ routes = {}, portfolio = false, stored = {} } = {}) {
  page({ portfolio });
  for (const [key, value] of Object.entries(stored)) {
    localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
  }
  server = fakeServer({ 'GET /api/account': { username: null, portfolio_pending: null }, ...routes });
  vi.resetModules();
  await import('../../Game_Logic/static/js/play.js');
  await flush();
}

const $ = (id) => document.getElementById(id);
const shown = () => [...document.querySelectorAll('.screen')].filter((s) => !s.hidden).map((s) => s.id);
const posted = (url) => server.calls.filter((call) => call.method === 'POST' && call.url === url);
const stored = (key) => JSON.parse(localStorage.getItem(key));

async function click(element) {
  element.click();
  await flush();
}

async function submit(form) {
  form.requestSubmit();
  await flush();
}

async function startNewGame(name = 'Dagon') {
  await click($('new-game'));
  $('name-input').value = name;
  await submit($('name-form'));
}

describe('menus', () => {
  it('starts a new game under a name and difficulty', async () => {
    await boot({ routes: { 'POST /api/new-game': { save: save() }, 'POST /api/play': played() } });
    expect(shown()).toEqual(['main-menu']);
    await startNewGame();
    expect(posted('/api/new-game')[0].body).toEqual({ name: 'Dagon', difficulty: 'recommended', mode: 'idle' });
    expect(shown()).toEqual(['game']);
    expect(document.title).toBe('Dead But Dreaming - Dagon');
    expect(document.documentElement.dataset.style).toBe('dagon');
    expect($('sanity').textContent).toBe('1,234');
    expect($('difficulty-label').textContent).toBe('Difficulty: Quick and Easy (15 min) in Idle Mode');
    expect(stored(`${SAVE_PREFIX}Dagon`)).toEqual(save());
  });

  it('offers a way back to the main menu from every other screen', async () => {
    await boot({ routes: { 'POST /api/new-game': { save: save() }, 'POST /api/play': played() } });
    expect($('main-menu-button').hidden).toBe(true);
    await click($('show-achievements'));
    expect($('main-menu-button').hidden).toBe(false);
    await click($('main-menu-button'));
    expect(shown()).toEqual(['main-menu']);
    await startNewGame();
    expect(document.title).toBe('Dead But Dreaming - Dagon');
    await click($('main-menu-button'));
    expect(shown()).toEqual(['main-menu']);
    expect($('main-menu-button').hidden).toBe(true);
    expect(document.title).toBe('Dead But Dreaming');
    const ticks = posted('/api/play').length;
    await vi.advanceTimersByTimeAsync(1000);
    expect(posted('/api/play')).toHaveLength(ticks);
  });

  it('starts a Clicker Mode world when that card is picked', async () => {
    await boot({ routes: { 'POST /api/new-game': { save: save() }, 'POST /api/play': played() } });
    await click($('new-game'));
    expect(document.querySelector('input[name="mode"]:checked').value).toBe('idle');
    document.querySelector('input[name="mode"][value="clicker"]').checked = true;
    $('name-input').value = 'Dagon';
    await submit($('name-form'));
    expect(posted('/api/new-game')[0].body.mode).toBe('clicker');
  });

  it('asks for a name, and asks before overwriting a save', async () => {
    await boot({ stored: { [`${SAVE_PREFIX}Dagon`]: save() },
      routes: { 'POST /api/new-game': { save: save('Dagon', 'b') }, 'POST /api/play': played() } });
    await click($('new-game'));
    $('name-input').value = '   ';
    await submit($('name-form'));
    expect($('name-error').textContent).toBe('Please enter a name');
    $('name-input').value = 'Dagon';
    await submit($('name-form'));
    expect($('confirm').hidden).toBe(false);
    expect($('confirm-message').textContent).toBe('Save game already exists. Overwrite?');
    await click($('confirm-no'));
    expect(posted('/api/new-game')).toHaveLength(0);
    await submit($('name-form'));
    await click($('confirm-yes'));
    expect($('confirm').hidden).toBe(true);
    expect(shown()).toEqual(['game']);
  });

  it('shows why a new game was refused, and suggests names', async () => {
    let names = 0;
    await boot({ routes: { 'POST /api/new-game': reply(400, {}), 'GET /api/random-name': () => {
      names += 1;
      return names === 1 ? { name: 'Hastur' } : reply(500, { error: 'No names left' });
    } } });
    await click($('new-game'));
    await click($('random-name'));
    expect($('name-input').value).toBe('Hastur');
    await click($('random-name'));
    expect($('name-error').textContent).toBe('No names left');
    await submit($('name-form'));
    expect($('name-error').textContent).toBe('/api/new-game returned 400');
    expect(shown()).toEqual(['name-entry']);
    await click(document.querySelector('#name-entry .back'));
    expect(shown()).toEqual(['main-menu']);
  });

  it('lists, loads and deletes saves', async () => {
    await boot({ stored: { [`${SAVE_PREFIX}Dagon`]: save(), [`${SAVE_PREFIX}Broken`]: '{not json' },
      routes: { 'POST /api/play': played() } });
    await click($('load-game'));
    expect($('no-saves').hidden).toBe(true);
    const rows = () => [...document.querySelectorAll('.save-row .menu-button')].map((b) => b.textContent);
    expect(rows()).toEqual(['Broken', 'Dagon']);
    await click(document.querySelector('.save-row .menu-button'));
    expect($('menu-error').textContent).toBe("Broken can't be read. Delete it from Load Game.");
    await click($('load-game'));
    await click(document.querySelectorAll('.delete-button')[1]);
    await click($('confirm-yes'));
    expect(rows()).toEqual(['Broken']);
    expect(stored('dead-but-dreaming:pending-deletes')).toEqual(['a'.repeat(16)]);
    await click(document.querySelector('.delete-button'));
    await click($('confirm-yes'));
    expect($('no-saves').hidden).toBe(false);
    expect(stored('dead-but-dreaming:pending-deletes')).toEqual(['a'.repeat(16)]);
  });

  it('keeps and restores the chosen style', async () => {
    await boot({ stored: { 'dead-but-dreaming:style': 'dagon' } });
    expect($('style-picker').value).toBe('dagon');
    $('style-picker').value = 'cthulhu';
    $('style-picker').dispatchEvent(new Event('change'));
    expect(localStorage.getItem('dead-but-dreaming:style')).toBe('cthulhu');
    await boot({ stored: { 'dead-but-dreaming:style': 'not-a-style' } });
    expect(document.documentElement.dataset.style).not.toBe('not-a-style');
  });

  it('marks earned achievements and goes back to the menu', async () => {
    await boot({ stored: { 'dead-but-dreaming:record': record(['goo_manager']) } });
    await click($('show-achievements'));
    const earned = [...document.querySelectorAll('[data-achievement].earned')].map((item) => item.dataset.achievement);
    expect(earned).toEqual(['goo_manager']);
    expect($('achievements-back').textContent).toBe('Back to Menu');
    await click($('achievements-back'));
    expect(shown()).toEqual(['main-menu']);
  });

  it('filters achievements by difficulty and by whether they are earned', async () => {
    await boot({ stored: { 'dead-but-dreaming:record': record(['goo_manager']) } });
    await click($('show-achievements'));
    const visible = () => [...document.querySelectorAll('.achievement')].filter((item) => !item.hidden)
      .map((item) => item.dataset.achievement);
    const groups = () => [...document.querySelectorAll('.achievement-group')].filter((group) => !group.hidden)
      .map((group) => group.dataset.group);
    const count = (key) => document.querySelector(`.achievement-group[data-group="${key}"] .group-count`).textContent;
    const choose = (id, value) => {
      $(id).value = value;
      $(id).dispatchEvent(new Event('change'));
    };
    expect(visible()).toEqual(['cult_leader', 'goo_manager', 'devour_quick', 'quick_fast_clicker']);
    expect([count('all'), count('quick')]).toEqual(['1 / 2', '0 / 2']);
    const quick = document.querySelector('.filter-button[data-group="quick"]');
    await click(quick);
    expect(quick.getAttribute('aria-pressed')).toBe('true');
    expect(groups()).toEqual(['quick']);
    choose('state-filter', 'earned');
    expect(visible()).toEqual([]);
    expect($('no-achievements').hidden).toBe(false);
    await click(quick);
    expect(quick.getAttribute('aria-pressed')).toBe('false');
    expect(visible()).toEqual(['goo_manager']);
    expect(groups()).toEqual(['all']);
    choose('state-filter', 'locked');
    expect(visible()).toEqual(['cult_leader', 'devour_quick', 'quick_fast_clicker']);
    expect($('no-achievements').hidden).toBe(true);
    choose('mode-filter', 'idle');
    expect(visible()).toEqual(['cult_leader', 'devour_quick']);
    choose('mode-filter', 'clicker');
    expect(visible()).toEqual(['cult_leader', 'devour_quick', 'quick_fast_clicker']);
    choose('state-filter', '');
    choose('mode-filter', '');
    expect(visible()).toEqual(['cult_leader', 'goo_manager', 'devour_quick', 'quick_fast_clicker']);
  });

  it('runs without storage when the browser blocks it', async () => {
    for (const method of ['getItem', 'setItem', 'removeItem']) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => { throw new Error('blocked'); });
    }
    vi.spyOn(Object, 'keys').mockImplementation(function keys(value) {
      if (value === localStorage) throw new Error('blocked');
      return Reflect.apply(Object.getOwnPropertyNames, null, [value]).filter((key) =>
        Object.getOwnPropertyDescriptor(value, key).enumerable);
    });
    await boot({ routes: { 'POST /api/new-game': { save: save() }, 'POST /api/play': played() } });
    await click($('load-game'));
    expect($('no-saves').hidden).toBe(false);
    await click(document.querySelector('#load-list .back'));
    await startNewGame();
    expect(shown()).toEqual(['game']);
  });
});

describe('accounts', () => {
  const login = { 'POST /api/login': { username: 'pilot' },
    'POST /api/sync': { saves: {}, deleted: [], record: record() } };

  it('logs in, syncs and returns to where the player was', async () => {
    await boot({ routes: login });
    expect($('login-warning').hidden).toBe(false);
    await click($('login-button'));
    expect(shown()).toEqual(['login']);
    $('login-username').value = 'pilot';
    $('login-password').value = 'longpassword';
    await submit($('login-form'));
    expect(posted('/api/login')[0].body).toEqual({ username: 'pilot', password: 'longpassword' });
    expect($('login-password').value).toBe('');
    expect($('account-name').textContent).toBe('pilot');
    expect([$('login-button').hidden, $('logout-button').hidden, $('portfolio-button').hidden]).toEqual([true, false, true]);
    expect(posted('/api/sync')).toHaveLength(1);
    expect(shown()).toEqual(['main-menu']);
  });

  it('shows why a login failed', async () => {
    await boot({ routes: { 'POST /api/login': reply(401, { error: 'Wrong username or password' }) } });
    await click($('login-button'));
    await submit($('login-form'));
    expect($('login-error').textContent).toBe('Wrong username or password');
    await click($('login-back'));
    expect(shown()).toEqual(['main-menu']);
  });

  it('explains a refusal whose answer is not JSON', async () => {
    await boot({ routes: { 'POST /api/login': { ok: false, status: 502, json: async () => { throw new SyntaxError('html'); } } } });
    await click($('login-button'));
    await submit($('login-form'));
    expect($('login-error').textContent).toBe('/api/login returned 502');
  });

  it('registers with a security question', async () => {
    await boot({ routes: { 'POST /api/register': { username: 'pilot' },
      'POST /api/sync': { saves: {}, deleted: [], record: record() } } });
    await click($('login-button'));
    $('login-username').value = 'pilot';
    $('login-password').value = 'longpassword';
    $('login-question').value = 'Pet?';
    $('login-answer').value = 'Rex';
    await click($('register'));
    expect(posted('/api/register')[0].body).toEqual({ username: 'pilot', password: 'longpassword', question: 'Pet?',
      answer: 'Rex' });
    expect($('login-answer').value).toBe('');
  });

  it('logs out', async () => {
    await boot({ routes: { 'GET /api/account': { username: 'pilot' }, 'POST /api/logout': { username: null },
      'POST /api/sync': { saves: {}, deleted: [], record: record() } } });
    expect($('account-name').textContent).toBe('pilot');
    await click($('logout-button'));
    expect($('account-name').hidden).toBe(true);
    expect($('login-button').hidden).toBe(false);
  });

  it('merges saves with the account, keeping other accounts out', async () => {
    const remote = save('Hastur', 'c');
    await boot({
      stored: {
        [`${SAVE_PREFIX}Mine`]: save('Mine', 'b'), [`${SAVE_PREFIX}Theirs`]: save('Theirs', 'd'),
        [`${SAVE_PREFIX}Gone`]: save('Gone', 'e'), [`${SAVE_PREFIX}Unreadable`]: '{',
        'dead-but-dreaming:save-owners': { Theirs: 'someone-else', Mine: 'pilot' },
        'dead-but-dreaming:record': record(['cult_leader']), 'dead-but-dreaming:record-owner': 'someone-else',
        'dead-but-dreaming:pending-deletes': ['f'.repeat(16)],
      },
      routes: { 'GET /api/account': { username: 'pilot' },
        'POST /api/sync': { saves: { Hastur: remote }, deleted: ['e'.repeat(16)], record: record(['goo_manager']) } },
    });
    const [sent] = posted('/api/sync');
    expect(Object.keys(sent.body.saves).sort()).toEqual(['Gone', 'Mine']);
    expect(sent.body.record).toBeNull();
    expect(sent.body.deleted).toEqual(['f'.repeat(16)]);
    expect(localStorage.getItem(`${SAVE_PREFIX}Theirs`)).toBeNull();
    expect(localStorage.getItem(`${SAVE_PREFIX}Gone`)).toBeNull();
    expect(stored(`${SAVE_PREFIX}Hastur`)).toEqual(remote);
    expect(stored('dead-but-dreaming:save-owners')).toEqual({ Mine: 'pilot', Hastur: 'pilot' });
    expect(stored('dead-but-dreaming:record')).toEqual(record(['goo_manager']));
    expect(stored('dead-but-dreaming:pending-deletes')).toEqual([]);
  });

  it('deleting a save while logged in tells the account', async () => {
    await boot({ stored: { [`${SAVE_PREFIX}Dagon`]: save() },
      routes: { 'GET /api/account': { username: 'pilot' },
        'POST /api/sync': (body) => ({ saves: {}, deleted: body.deleted, record: record() }) } });
    await click($('load-game'));
    await click(document.querySelector('.delete-button'));
    await click($('confirm-yes'));
    expect(posted('/api/sync').at(-1).body.deleted).toEqual(['a'.repeat(16)]);
  });

  it('resets a password in two steps', async () => {
    await boot({ routes: { 'POST /api/reset-question': { question: 'Pet?' }, 'POST /api/reset-password': { reset: true } } });
    await click($('login-button'));
    $('login-username').value = 'pilot';
    await click($('forgot-password'));
    expect($('reset-username').value).toBe('pilot');
    expect($('reset-answer').hidden).toBe(true);
    await submit($('reset-form'));
    expect($('reset-question').textContent).toBe('Pet?');
    expect([$('reset-answer').hidden, $('reset-username').readOnly, $('reset-submit').textContent]).toEqual(
      [false, true, 'Reset Password']);
    $('reset-answer').value = 'Rex';
    $('reset-password').value = 'newpassword';
    await submit($('reset-form'));
    expect(posted('/api/reset-password')[0].body).toEqual({ username: 'pilot', answer: 'Rex', password: 'newpassword' });
    expect(shown()).toEqual(['login']);
    expect($('login-error').textContent).toBe('Password changed. Log in with your new password.');
  });

  it('says when a reset cannot go ahead, and goes back', async () => {
    await boot({ routes: { 'POST /api/reset-question': reply(400, { error: 'There is no account with that username' }) } });
    await click($('forgot-password'));
    await submit($('reset-form'));
    expect($('reset-error').textContent).toBe('There is no account with that username');
    await click($('reset-back'));
    expect(shown()).toEqual(['login']);
  });

  it('offers the portfolio login under the name the portfolio knows', async () => {
    await boot({ portfolio: true, routes: { 'GET http://portfolio.test/sso/me': { username: 'Gambler' } } });
    expect($('portfolio-button').hidden).toBe(false);
    expect($('portfolio-button').textContent).toBe('Log In as Gambler');
    const browser = { href: '' };
    vi.stubGlobal('location', browser);
    await click($('portfolio-button'));
    expect(browser.href).toBe('/sso/login');
  });

  it.each([
    ['logged out of the portfolio', () => reply(401, {})],
    ['without a name', () => ({ username: null })],
    ['unreachable', () => { throw new TypeError('offline'); }],
  ])('keeps the plain portfolio button when the portfolio is %s', async (_, answer) => {
    await boot({ portfolio: true, routes: { 'GET http://portfolio.test/sso/me': answer } });
    expect($('portfolio-button').textContent).toBe('Log In with Portfolio Account');
  });

  it('links a first portfolio login to an account, or makes one, or cancels', async () => {
    let tries = 0;
    const pending = { 'GET /api/account': { username: null, portfolio_pending: 'Gambler' },
      'POST /api/sync': { saves: {}, deleted: [], record: record() } };
    await boot({ portfolio: true, routes: { ...pending, 'POST /api/portfolio/link': () => {
      tries += 1;
      return tries === 1 ? reply(400, { error: 'Wrong username or password' }) : { username: 'pilot' };
    } } });
    expect(shown()).toEqual(['account-link']);
    expect($('account-link-name').textContent).toBe('Gambler');
    expect($('account-link-username').value).toBe('Gambler');
    $('account-link-password').value = 'wrong';
    await submit($('account-link-form'));
    expect($('account-link-error').textContent).toBe('Wrong username or password');
    await submit($('account-link-form'));
    expect($('account-name').textContent).toBe('pilot');

    await boot({ portfolio: true, routes: { ...pending, 'POST /api/portfolio/new': { username: 'Gambler' } } });
    await click($('account-link-new'));
    expect($('account-name').textContent).toBe('Gambler');

    await boot({ portfolio: true, routes: { ...pending, 'POST /api/logout': reply(500, {}) } });
    await click($('account-link-cancel'));
    expect(shown()).toEqual(['main-menu']);
  });

  it('notes when the account check fails', async () => {
    await boot({ routes: { 'GET /api/account': reply(500, {}) } });
    expect(console.error).toHaveBeenCalled();
    expect($('account-name').hidden).toBe(true);
  });
});

describe('the game', () => {
  async function play(routes = {}, stored = {}) {
    await boot({ routes: { 'POST /api/new-game': { save: save() }, 'POST /api/play': played(), ...routes }, stored });
    await startNewGame();
  }

  it('sends clicks with the save and draws the resources', async () => {
    await play({ 'POST /api/play': played({ resources: [
      resource('cultists', { unlocked: true, rate: 1500, has_manager: true, processing: true }),
      resource('tomes', { unlocked: true, can_hire: true, manager_cost: 60 }),
      resource('relics', { unlocked: true, manager_cost: 900 }),
      resource('rites', { can_unlock: true, unlock_cost: 2000 }),
      resource('stars', { unlock_cost: 5000 }),
    ] }) });
    const row = (key) => document.querySelector(`[data-action="resource"][data-target="${key}"]`).closest('.resource-row');
    expect(row('cultists').querySelector('.resource').className).toBe('resource unlocked');
    expect(row('cultists').querySelector('.resource-detail').textContent).toBe('1,500 Sanity');
    expect(row('cultists').querySelector('.manager').className).toBe('manager hired');
    expect(row('cultists').querySelector('.manager-cost').textContent).toBe('Hired');
    expect(row('tomes').querySelector('.manager').className).toBe('manager affordable');
    expect(row('relics').querySelector('.manager').className).toBe('manager unaffordable');
    expect(row('rites').querySelector('.resource').className).toBe('resource locked affordable');
    expect(row('stars').querySelector('.resource-detail').textContent).toBe('Unlock: 5,000');
    expect(row('stars').querySelector('.manager').hidden).toBe(true);

    const button = row('tomes').querySelector('.manager');
    button.click();
    expect(button.dataset.pressed).toBe('');
    await flush();
    expect(posted('/api/play').at(-1).body.actions).toEqual([{ type: 'manager', target: 'tomes' }]);
    expect(button.dataset.pressed).toBeUndefined();
  });

  it('keeps sending updates four times a second, but not while the page is hidden', async () => {
    await play();
    const before = posted('/api/play').length;
    await vi.advanceTimersByTimeAsync(1000);
    expect(posted('/api/play').length).toBe(before + 4);
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    await vi.advanceTimersByTimeAsync(1000);
    expect(posted('/api/play').length).toBe(before + 4);
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
    document.dispatchEvent(new Event('visibilitychange'));
    await flush();
    expect(posted('/api/play').length).toBe(before + 5);
  });

  it('asks the account to back up every 30 seconds while logged in', async () => {
    await play({ 'GET /api/account': { username: 'pilot' },
      'POST /api/sync': { saves: {}, deleted: [], record: record() } });
    expect(posted('/api/play').at(-1).body.backup).toBe(false);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(posted('/api/play').some((call) => call.body.backup)).toBe(true);
  });

  it('animates the progress bars only when a cycle changes', async () => {
    const bars = [
      resource('cultists', { unlocked: true, processing: true, progress: 0.5, cycle_seconds: 2 }),
      resource('tomes', { unlocked: true, processing: true, has_manager: true, solid_bar: true }),
      resource('relics', { unlocked: true }),
    ];
    let current = played({ resources: bars });
    await play({ 'POST /api/play': () => current });
    const fill = (key) => document.querySelector(`[data-target="${key}"] .progress-fill`);
    expect(fill('cultists').style.animation).toBe('fill-bar 2s linear -1s 1 forwards');
    expect(fill('tomes').style.transform).toBe('scaleX(1)');
    expect(fill('relics').style.transform).toBe('scaleX(0)');

    fill('cultists').style.animation = 'kept';
    current = played({ resources: [{ ...bars[0], progress: 0.7 }, bars[1], bars[2]] });
    await vi.advanceTimersByTimeAsync(250);
    expect(fill('cultists').style.animation).toBe('kept');
    current = played({ resources: [{ ...bars[0], progress: 0.1 }, bars[1], bars[2]] });
    await vi.advanceTimersByTimeAsync(250);
    expect(fill('cultists').style.animation).toBe('fill-bar 2s linear -0.2s 1 forwards');
    current = played({ resources: [{ ...bars[0], has_manager: true, progress: 0 }, bars[1], bars[2]] });
    await vi.advanceTimersByTimeAsync(250);
    expect(fill('cultists').style.animation).toBe('fill-bar 2s linear 0s infinite forwards');
  });

  it('filters the upgrades by type and resource', async () => {
    let current = played({ upgrades: [upgrade('cultists_speed_2x', 'speed', 'cultists', 50, true),
      upgrade('tomes_prod_2x', 'production', 'tomes', 180)],
    resources: [resource('cultists', { unlocked: true }), resource('tomes', { unlocked: true })] });
    await play({ 'POST /api/play': () => current });
    const names = () => [...document.querySelectorAll('.upgrade-button .upgrade-name')].map((n) => n.textContent);
    expect(names()).toEqual(['cultists_speed_2x', 'tomes_prod_2x']);
    expect(document.querySelector('.upgrade-button').className).toBe('upgrade-button affordable');
    expect([...$('resource-filter').options].map((o) => o.value)).toEqual(['', 'cultists', 'tomes']);

    const filter = (id, value) => {
      $(id).value = value;
      $(id).dispatchEvent(new Event('change'));
    };
    filter('type-filter', 'production');
    expect(names()).toEqual(['tomes_prod_2x']);
    expect($('speed-upgrades').hidden).toBe(true);
    filter('resource-filter', 'cultists');
    expect(names()).toEqual([]);
    expect($('no-upgrades').hidden).toBe(false);
    filter('type-filter', '');
    const kept = document.querySelector('.upgrade-button');
    current = played({ upgrades: current.view.upgrades, resources: [resource('cultists', { unlocked: true })] });
    await vi.advanceTimersByTimeAsync(250);
    expect($('resource-filter').value).toBe('cultists');
    expect(document.querySelector('.upgrade-button')).toBe(kept);
    filter('resource-filter', 'tomes');
    current = played({ upgrades: current.view.upgrades, resources: [resource('cultists', { unlocked: true }),
      resource('stars', { unlocked: true })] });
    await vi.advanceTimersByTimeAsync(250);
    expect($('resource-filter').value).toBe('');
  });

  it('shows the ending, and the time once the world has been devoured', async () => {
    let current = played({ ending: true, worlds_devoured: 1200, devoured_time: '2h 00m 00s', upgrades: [] });
    await play({ 'POST /api/play': (body) => {
      if (body.actions.some((action) => action.type === 'endless')) {
        current = played({ endless: true, devoured_time: '2h 00m 00s', upgrades: [] });
      }
      return current;
    } });
    expect(shown()).toEqual(['ending']);
    expect([$('ending-time').textContent, $('ending-difficulty').textContent, $('ending-mode').textContent,
      $('ending-worlds').textContent]).toEqual(['2h 00m 00s', 'Quick and Easy', 'Idle Mode', '1,200']);
    await click($('endless'));
    expect(shown()).toEqual(['game']);
    expect($('devoured-label').textContent).toBe('World devoured in 2h 00m 00s');
    expect($('devoured-label').hidden).toBe(false);
  });

  it('begins a new world or deletes the devoured one', async () => {
    await play({ 'POST /api/play': played({ ending: true, upgrades: [] }) });
    await click($('new-world'));
    expect(posted('/api/play').at(-1).body.actions).toEqual([{ type: 'reset', target: '' }]);
    await click($('delete-world'));
    await click($('confirm-yes'));
    expect(shown()).toEqual(['main-menu']);
    expect(document.title).toBe('Dead But Dreaming');
    expect(localStorage.getItem(`${SAVE_PREFIX}Dagon`)).toBeNull();
  });

  it('pops up new achievements and marks them on the open list', async () => {
    let current = played();
    await play({ 'POST /api/play': () => current });
    await click($('footer-achievements'));
    expect($('achievements-back').textContent).toBe('Back to Game');
    current = played({}, { new_achievements: [{ id: 'cult_leader', name: 'The First Disciple' }], record: record(['cult_leader']) });
    await vi.advanceTimersByTimeAsync(250);
    current = played({}, { record: record(['cult_leader']) });
    expect(document.querySelector('[data-achievement="cult_leader"]').className).toContain('earned');
    expect(document.querySelector('.toast-name').textContent).toBe('The First Disciple');
    await click($('achievements-back'));
    expect(shown()).toEqual(['game']);
    current = played({}, { new_achievements: [{ id: 'goo_manager', name: 'Whispers' }] });
    await vi.advanceTimersByTimeAsync(250);
    current = played();
    expect(document.querySelectorAll('.toast')).toHaveLength(2);
    await click(document.querySelector('.toast-close'));
    expect(document.querySelectorAll('.toast')).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(5000);
    expect(document.querySelectorAll('.toast')).toHaveLength(0);
  });

  it('throttles taps and jumps the bar when a tap lands in Clicker Mode', async () => {
    let progress = 0.3;
    const working = () => played({ clicker: true, resources: [
      resource('cultists', { unlocked: true, processing: true, progress, cycle_seconds: 2 }), resource('tomes')] });
    await play({ 'POST /api/play': working });
    const button = document.querySelector('[data-action="resource"][data-target="cultists"]');
    const fill = button.querySelector('.progress-fill');
    expect(fill.style.animation).toContain('-0.6s');
    progress = 0.35;
    await vi.advanceTimersByTimeAsync(250);
    expect(fill.style.animation).toContain('-0.6s');
    button.click();
    button.click();
    await flush();
    expect(posted('/api/play').at(-1).body.actions).toEqual([{ type: 'resource', target: 'cultists' }]);
    expect(fill.style.animation).toContain('-0.7s');
    await vi.advanceTimersByTimeAsync(80);
    button.click();
    await flush();
    expect(posted('/api/play').at(-1).body.actions).toEqual([{ type: 'resource', target: 'cultists' }]);
  });

  it("leaves another tab's newer record alone unless this tick changed it", async () => {
    const newer = { ...record(['goo_manager']), signature: 'newer' };
    let answer = (body) => body.record;
    await play({ 'POST /api/play': (body) => {
      localStorage.setItem('dead-but-dreaming:record', JSON.stringify(newer));
      return played({}, { record: answer(body) });
    } }, { 'dead-but-dreaming:record': { ...record(), signature: 'older' } });
    expect(posted('/api/play').at(-1).body.record.signature).toBe('older');
    expect(stored('dead-but-dreaming:record')).toEqual(newer);
    answer = () => ({ ...record(['cult_leader']), signature: 'changed' });
    await vi.advanceTimersByTimeAsync(250);
    expect(stored('dead-but-dreaming:record').signature).toBe('changed');
  });

  it('resends clicks after a dropped or stalled connection', async () => {
    let failure = null;
    await play({ 'POST /api/play': () => {
      if (failure) {
        const error = failure;
        failure = null;
        throw error;
      }
      return played();
    } });
    const button = document.querySelector('[data-action="resource"]');
    failure = new TypeError('offline');
    button.click();
    await flush();
    expect(button.dataset.pressed).toBe('');
    await vi.advanceTimersByTimeAsync(250);
    expect(posted('/api/play').at(-1).body.actions).toEqual([{ type: 'resource', target: 'cultists' }]);
    expect(button.dataset.pressed).toBeUndefined();

    failure = Object.assign(new Error('slow'), { name: 'TimeoutError' });
    button.click();
    await flush();
    const [stalled, resent] = posted('/api/play').slice(-2);
    expect(stalled.body.actions).toEqual(resent.body.actions);
  });

  it.each([502, 503, 504])('resends clicks while a restarting server answers %i', async (status) => {
    let failing = false;
    await play({ 'POST /api/play': () => {
      if (!failing) return played();
      failing = false;
      return { ok: false, status, json: async () => { throw new SyntaxError('html'); } };
    } });
    const button = document.querySelector('[data-action="resource"]');
    failing = true;
    button.click();
    await flush();
    expect(shown()).toEqual(['game']);
    expect($('menu-error').textContent).toBe('');
    expect(button.dataset.pressed).toBe('');
    await vi.advanceTimersByTimeAsync(250);
    expect(posted('/api/play').at(-1).body.actions).toEqual([{ type: 'resource', target: 'cultists' }]);
    expect(button.dataset.pressed).toBeUndefined();
  });

  it('stops the game when the server refuses the save', async () => {
    await play({ 'POST /api/play': reply(400, { error: "This save was changed outside the game, so it can't be loaded." }) });
    expect(shown()).toEqual(['main-menu']);
    expect($('menu-error').textContent).toBe("This save was changed outside the game, so it can't be loaded.");
  });

  it('ignores an update that comes back after the game was stopped', async () => {
    let answer;
    await play({ 'POST /api/play': () => new Promise((resolve) => { answer = resolve; }) });
    await click($('footer-achievements'));
    answer(played({ ending: true, upgrades: [] }));
    await flush();
    $('delete-world').click();
    let late;
    server.routes['POST /api/play'] = () => new Promise((resolve) => { late = resolve; });
    await vi.advanceTimersByTimeAsync(250);
    await click($('confirm-yes'));
    late(played({ sanity: 999 }));
    await flush();
    expect(shown()).toEqual(['main-menu']);
    expect(localStorage.getItem(`${SAVE_PREFIX}Dagon`)).toBeNull();
  });

  it('ignores an error that comes back after the game was stopped', async () => {
    await play({ 'POST /api/play': played({ ending: true, upgrades: [] }) });
    let late;
    server.routes['POST /api/play'] = () => new Promise((resolve) => { late = resolve; });
    await vi.advanceTimersByTimeAsync(250);
    $('delete-world').click();
    await click($('confirm-yes'));
    late(reply(500, { error: 'Something broke' }));
    await flush();
    expect($('menu-error').textContent).toBe('');
  });

  it('does nothing when the upgrade filters change before a game is drawn', async () => {
    await boot();
    $('type-filter').value = 'speed';
    $('type-filter').dispatchEvent(new Event('change'));
    expect(document.querySelectorAll('.upgrade-button')).toHaveLength(0);
  });

  it('hands the final save to the account as the page closes', async () => {
    const beacon = vi.fn();
    Object.defineProperty(navigator, 'sendBeacon', { value: beacon, configurable: true });
    await play();
    window.dispatchEvent(new Event('pagehide'));
    expect(beacon).not.toHaveBeenCalled();
    localStorage.clear();
    await boot({ routes: { 'GET /api/account': { username: 'pilot' }, 'POST /api/new-game': { save: save() },
      'POST /api/play': played(), 'POST /api/sync': { saves: {}, deleted: [], record: record() } } });
    window.dispatchEvent(new Event('pagehide'));
    expect(beacon).not.toHaveBeenCalled();
    await startNewGame();
    window.dispatchEvent(new Event('pagehide'));
    expect(beacon).toHaveBeenCalledOnce();
    expect(beacon.mock.calls[0][0]).toBe('/api/sync');
    delete navigator.sendBeacon;
  });

  it('shows account statistics while logged in', async () => {
    await boot();
    expect($('show-stats').hidden).toBe(true);
    let stats = { rows: [], total: { sanity: 0, worlds: 0 } };
    await boot({ routes: { 'GET /api/account': { username: 'pilot' }, 'GET /api/stats': () => stats,
      'POST /api/sync': { saves: {}, deleted: [], record: record() } } });
    expect($('show-stats').hidden).toBe(false);
    await click($('show-stats'));
    expect(shown()).toEqual(['stats']);
    expect($('no-stats').hidden).toBe(false);
    expect($('stats-table').hidden).toBe(true);
    await click(document.querySelector('#stats .back'));
    stats = { rows: [{ difficulty: 'Quick and Easy', sanity: 151189823, worlds: 2 }], total: { sanity: 151189823, worlds: 2 } };
    await click($('show-stats'));
    expect($('no-stats').hidden).toBe(true);
    expect([...$('stats-rows').querySelectorAll('th, td')].map((cell) => cell.textContent))
      .toEqual(['Quick and Easy', '151,189,823', '2']);
    expect([$('stats-sanity').textContent, $('stats-worlds').textContent]).toEqual(['151,189,823', '2']);
    await click(document.querySelector('#stats .back'));
    stats = reply(500, { error: 'Something broke' });
    await click($('show-stats'));
    expect(shown()).toEqual(['main-menu']);
    expect($('menu-error').textContent).toBe('Something broke');
  });

  it("shows the new world's upgrade costs after a stopped game", async () => {
    let current = played({ resources: [resource('cultists', { unlocked: true }), resource('tomes', { unlocked: true })],
      upgrades: [upgrade('tomes_speed_2x', 'speed', 'tomes', 370)] });
    await play({ 'POST /api/play': () => current }, { [`${SAVE_PREFIX}Hastur`]: save('Hastur', 'b') });
    current = reply(500, { error: 'Something broke' });
    await vi.advanceTimersByTimeAsync(250);
    expect(shown()).toEqual(['main-menu']);
    current = played({ player_name: 'Hastur', resources: [resource('cultists', { unlocked: true }),
      resource('tomes', { unlocked: true })], upgrades: [upgrade('tomes_speed_2x', 'speed', 'tomes', 870)] });
    await click($('load-game'));
    await click([...document.querySelectorAll('.save-row .menu-button')].find((b) => b.textContent === 'Hastur'));
    expect(document.querySelector('.upgrade-button .number').textContent).toBe('870');
  });
});
