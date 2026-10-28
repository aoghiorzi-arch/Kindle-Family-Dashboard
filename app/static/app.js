const $ = id => document.getElementById(id);
let csrf = '';
let isAdmin = false;

async function call(path, {method = 'GET', body} = {}) {
  const headers = {'Content-Type': 'application/json'};
  if (method === 'POST') headers['X-CSRF-Token'] = csrf;
  const r = await fetch(path, {method, headers, body: body ? JSON.stringify(body) : undefined, credentials: 'same-origin'});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(j.error || 'Something went wrong'); e.status = r.status; throw e; }
  return j;
}

function text(tag, value, className) {
  const n = document.createElement(tag);
  n.textContent = value;
  if (className) n.className = className;
  return n;
}

function message(value, isError = false) {
  $('status').textContent = value;
  $('status').className = isError ? 'status error' : 'status';
}

function showLogin(note = '') {
  $('app').hidden = true;
  $('account').hidden = true;
  $('login').hidden = false;
  $('loginStatus').textContent = note;
  $('password').value = '';
}

function handleError(e) {
  if (e.status === 401) showLogin('Please sign in again.');
  else message(e.message, true);
}

function shoppingRow(item) {
  const li = document.createElement('li');
  if (item.done) li.className = 'done';
  const toggle = text('button', item.done ? 'Undo' : 'Got it', 'link');
  toggle.onclick = () => act(`/api/shopping/${item.id}/toggle`);
  const remove = text('button', 'Remove', 'link danger');
  remove.onclick = () => act(`/api/shopping/${item.id}/delete`);
  li.append(text('span', item.title), toggle, remove);
  return li;
}

function eventRow(event) {
  const li = document.createElement('li');
  const label = event.time ? `${event.title} · ${event.time}` : event.title;
  const suffix = event.private ? ' (private)' : '';
  const remove = text('button', 'Remove', 'link danger');
  remove.onclick = () => act(`/api/events/${event.id}/delete`);
  li.append(text('span', label + suffix), remove);
  return li;
}

function memberRow(member) {
  return text('li', `${member.username} · ${member.role}`);
}

function feedRow(feed) {
  const li = document.createElement('li');
  let status = 'not synced yet';
  if (feed.last_error) status = `failed: ${feed.last_error}`;
  else if (feed.last_success) status = `synced ${new Date(feed.last_success * 1000).toLocaleString()}`;
  li.append(text('span', `${feed.label} · ${feed.host} · ${status}`));
  const refreshButton = text('button', 'Refresh', 'link');
  refreshButton.onclick = async () => {
    try {
      const j = await call(`/api/feeds/${feed.id}/refresh`, {method: 'POST', body: {}});
      message(j.ok ? 'Feed refreshed.' : `Feed failed: ${j.error}`, !j.ok);
      await refresh();
    } catch (e) { handleError(e); }
  };
  const remove = text('button', 'Remove', 'link danger');
  remove.onclick = () => act(`/api/feeds/${feed.id}/delete`, {}, 'Feed removed.');
  li.append(refreshButton, remove);
  return li;
}

function tokenRow(token) {
  const li = document.createElement('li');
  const used = token.last_used_at ? new Date(token.last_used_at * 1000).toLocaleDateString() : 'never used';
  const state = token.revoked ? 'revoked' : `last used ${used}`;
  li.append(text('span', `${token.name} · ${state}`));
  if (!token.revoked) {
    const revoke = text('button', 'Revoke', 'link danger');
    revoke.onclick = () => act(`/api/tokens/${token.id}/revoke`);
    li.append(revoke);
  }
  return li;
}

async function refresh() {
  const s = await call('/api/state');
  csrf = s.csrf;
  isAdmin = s.role === 'admin';
  $('who').textContent = `${s.user}${isAdmin ? ' (admin)' : ''}`;
  $('items').replaceChildren(...s.shopping.map(shoppingRow));
  $('events').replaceChildren(...s.events.map(eventRow));
  $('admin').hidden = !isAdmin;
  if (isAdmin) {
    $('members').replaceChildren(...s.members.map(memberRow));
    $('tokens').replaceChildren(...s.tokens.map(tokenRow));
    $('feeds').replaceChildren(...s.feeds.map(feedRow));
    $('calendarStatus').textContent = s.calendar.events ? `${s.calendar.events} imported events in the calendar.` : 'No calendar imported.';
    if (s.location) {
      $('lat').value = s.location.lat;
      $('lon').value = s.location.lon;
      $('tz').value = s.location.tz;
    }
  }
  $('screen').src = '/frame.png?t=' + Date.now();
  $('login').hidden = true;
  $('app').hidden = false;
  $('account').hidden = false;
}

async function act(path, body = {}, done = 'Saved. Preview updated.') {
  try {
    await call(path, {method: 'POST', body});
    message(done);
    await refresh();
    return true;
  } catch (e) { handleError(e); return false; }
}

$('loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const j = await call('/api/login', {method: 'POST', body: {username: $('username').value, password: $('password').value}});
    csrf = j.csrf;
    await refresh();
  } catch (err) {
    $('loginStatus').textContent = err.message;
  }
});

$('logout').addEventListener('click', async () => {
  await call('/api/logout', {method: 'POST'}).catch(() => {});
  csrf = '';
  $('newToken').hidden = true;
  showLogin('Signed out.');
});

$('shopping').addEventListener('submit', async e => {
  e.preventDefault();
  const title = $('item').value;
  if (await act('/api/shopping', {title})) { $('item').value = ''; $('item').focus(); }
});

$('event').addEventListener('submit', async e => {
  e.preventDefault();
  const body = {title: $('eventTitle').value, time: $('eventTime').value, private: $('eventPrivate').checked};
  if (await act('/api/events', body)) {
    $('eventTitle').value = '';
    $('eventTime').value = '';
    $('eventPrivate').checked = false;
  }
});

$('memberForm').addEventListener('submit', async e => {
  e.preventDefault();
  const body = {username: $('newUser').value, password: $('newPass').value, role: $('newRole').value};
  if (await act('/api/members', body, 'Member added.')) {
    $('newUser').value = '';
    $('newPass').value = '';
  }
});

$('locationForm').addEventListener('submit', async e => {
  e.preventDefault();
  await act('/api/location', {lat: $('lat').value, lon: $('lon').value, tz: $('tz').value}, 'Location saved. Sunset updates on the next preview.');
});

$('tokenForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const j = await call('/api/tokens', {method: 'POST', body: {name: $('tokenName').value}});
    $('tokenValue').textContent = j.token;
    $('newToken').hidden = false;
    $('tokenName').value = '';
    message('Token created. Copy it now.');
    await refresh();
  } catch (err) { handleError(err); }
});

$('calendarForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const j = await call('/api/calendar', {method: 'POST', body: {ics: $('ics').value}});
    $('ics').value = '';
    message(`Calendar imported: ${j.imported} events. ${j.skipped} recurring or unreadable entries skipped.`);
    await refresh();
  } catch (err) { handleError(err); }
});

$('calendarClear').addEventListener('submit', async e => {
  e.preventDefault();
  await act('/api/calendar/clear', {}, 'Imported calendar removed.');
});

$('feedForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const j = await call('/api/feeds', {method: 'POST', body: {label: $('feedLabel').value, url: $('feedUrl').value}});
    $('feedLabel').value = '';
    $('feedUrl').value = '';
    message(j.ok ? 'Feed added and synced.' : `Feed added, but it failed: ${j.error}`, !j.ok);
    await refresh();
  } catch (err) { handleError(err); }
});

refresh().catch(e => showLogin(e.status === 401 ? '' : e.message));
