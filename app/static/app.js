const $ = id => document.getElementById(id);
let csrf = '';

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

async function refresh() {
  const s = await call('/api/state');
  csrf = s.csrf;
  $('who').textContent = s.user;
  $('items').replaceChildren(...s.shopping.map(shoppingRow));
  $('events').replaceChildren(...s.events.map(eventRow));
  $('screen').src = '/frame.png?t=' + Date.now();
  $('login').hidden = true;
  $('app').hidden = false;
  $('account').hidden = false;
}

async function act(path, body = {}) {
  try {
    await call(path, {method: 'POST', body});
    message('Saved. Preview updated.');
    await refresh();
  } catch (e) { handleError(e); }
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
  showLogin('Signed out.');
});

$('shopping').addEventListener('submit', async e => {
  e.preventDefault();
  const title = $('item').value;
  try {
    await call('/api/shopping', {method: 'POST', body: {title}});
    $('item').value = '';
    message('Saved. Preview updated.');
    await refresh();
    $('item').focus();
  } catch (err) { handleError(err); }
});

$('event').addEventListener('submit', async e => {
  e.preventDefault();
  const body = {title: $('eventTitle').value, time: $('eventTime').value, private: $('eventPrivate').checked};
  try {
    await call('/api/events', {method: 'POST', body});
    $('eventTitle').value = '';
    $('eventTime').value = '';
    $('eventPrivate').checked = false;
    message('Saved. Preview updated.');
    await refresh();
  } catch (err) { handleError(err); }
});

refresh().catch(e => showLogin(e.status === 401 ? '' : e.message));
