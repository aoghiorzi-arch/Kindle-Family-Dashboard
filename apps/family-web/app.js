// Family Hub editor. Plain ES module, no build step. Every value from the server is set with textContent.

const state = {
  health: null,
  session: null,
  route: "home",
  items: [],
  itemsLoaded: false,
  snapshot: null,
  devices: [],
  editingId: null,
  newToken: null,
};

const $ = (selector) => document.querySelector(selector);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "text") node.textContent = value;
    else if (key === "on") for (const [event, handler] of Object.entries(value)) node.addEventListener(event, handler);
    else if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

class ApiError extends Error {
  constructor(status, code, message, current) {
    super(message);
    this.status = status;
    this.code = code;
    this.current = current;
  }
}

async function api(path, { method = "GET", body, csrf } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
    cache: "no-store",
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const error = data?.error ?? {};
    throw new ApiError(response.status, error.code ?? "error", error.message ?? "Something went wrong", error.current);
  }
  return data;
}

function setStatus(message, isError = false) {
  const status = $("#status");
  status.textContent = message;
  status.classList.toggle("error", isError);
}

function focusHeading() {
  const heading = document.querySelector("#view h2");
  if (heading) heading.focus();
}

// ---- Data -------------------------------------------------------------------

async function loadSession() {
  try {
    state.session = await api("/api/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) state.session = null;
    else throw error;
  }
}

async function loadItems() {
  const data = await api("/api/shopping");
  state.items = data.items;
  state.itemsLoaded = true;
}

async function loadSnapshot() {
  state.snapshot = await api("/api/snapshot/preview");
}

async function loadDevices() {
  if (state.session?.role !== "admin") return;
  state.devices = (await api("/api/admin/devices")).devices;
}

// ---- Views ------------------------------------------------------------------

function signInView() {
  if (state.health?.signIn !== "development") {
    return el("section", { class: "card" },
      el("h2", { tabindex: "-1" }, "Sign in"),
      el("p", {}, "Sign-in is not set up on this server yet. A household admin needs to finish setup before the family can use the Hub."),
    );
  }
  const input = el("input", { type: "text", id: "dev-member", autocomplete: "off", required: true, "aria-describedby": "dev-note" });
  return el("section", { class: "card" },
    el("h2", { tabindex: "-1" }, "Sign in"),
    el("p", { id: "dev-note", class: "muted" }, "Development sign-in. It works on this computer only."),
    el("form", {
      class: "stack",
      on: {
        submit: async (event) => {
          event.preventDefault();
          try {
            await api("/api/dev/login", { method: "POST", body: { memberId: input.value.trim() } });
            await start();
          } catch {
            setStatus("Sign-in failed. Check the member ID.", true);
          }
        },
      },
    },
    el("label", { for: "dev-member" }, "Member ID"),
    input,
    el("button", { type: "submit", class: "primary" }, "Sign in")),
  );
}

function homeView() {
  const snap = state.snapshot;
  const expired = snap && Date.now() > Date.parse(snap.expiresAt);
  const items = snap?.shopping.items ?? [];
  return el("section", {},
    el("h2", { tabindex: "-1" }, "Today on the Kindle"),
    el("p", { class: "muted" }, "This is the picture the display receives. It updates when the list changes."),
    el("div", { class: `card${expired ? " stale" : ""}` },
      el("p", {}, `Date: ${snap?.localDate ?? "unknown"} (${snap?.timezone ?? ""})`),
      el("p", {}, snap?.weather.summary ? `Weather: ${snap.weather.summary}` : "Weather is not connected yet."),
      el("p", {}, "Calendar is not connected yet."),
      el("p", {}, `Shopping: ${snap?.shopping.remainingCount ?? 0} to get`),
      items.length ? el("ul", { class: "muted" }, items.map((item) => el("li", {}, item.title))) : null,
      snap ? el("p", { class: "badge" }, `Generated ${formatTime(snap.generatedAt)}`) : null,
      expired
        ? el("p", { role: "note" }, "This picture is more than 20 minutes old. The Kindle may still show an earlier one.")
        : null,
    ),
    el("button", { type: "button", on: { click: refresh } }, "Refresh"),
  );
}

function shoppingView() {
  const addInput = el("input", { type: "text", id: "new-item", maxlength: "60", required: true, autocomplete: "off", "aria-label": "New item" });
  return el("section", {},
    el("h2", { tabindex: "-1" }, "Shopping"),
    el("form", {
      class: "stack",
      on: {
        submit: async (event) => {
          event.preventDefault();
          const title = addInput.value.trim();
          if (!title) return;
          await mutate(() => api("/api/shopping", { method: "POST", body: { title }, csrf: state.session.csrfToken }), "Added.");
          addInput.value = "";
          addInput.focus();
        },
      },
    },
    el("label", { for: "new-item" }, "Add an item"),
    el("div", { class: "row" }, el("div", { class: "grow" }, addInput),
      el("button", { type: "submit", class: "primary" }, "Add"))),
    el("div", { id: "list" }),
  );
}

function renderList() {
  const container = $("#list");
  if (!container) return;
  container.replaceChildren();
  const open = state.items.filter((i) => !i.done).length;
  container.append(el("p", { class: "muted", "aria-live": "polite" }, `${open} to get`));
  if (state.items.length === 0) {
    container.append(el("p", { class: "muted" }, "The list is empty."));
    return;
  }
  container.append(el("ul", { class: "list", "aria-label": "Shopping items" },
    state.items.map((item, index) => itemRow(item, index))));
}

function itemRow(item, index) {
  const isEditing = state.editingId === item.id;
  const checkbox = el("input", {
    type: "checkbox",
    checked: item.done,
    "aria-label": `Got: ${item.title}`,
    on: { change: (event) => mutate(() => api(`/api/shopping/${item.id}`, { method: "PATCH", body: { version: item.version, done: event.target.checked }, csrf: state.session.csrfToken })) },
  });
  const title = el("span", { class: `item-title${item.done ? " done" : ""}` }, item.title);
  const controls = isEditing ? editForm(item) : el("div", { class: "row" },
    el("button", { type: "button", on: { click: () => { state.editingId = item.id; renderList(); $(`#edit-${item.id}`)?.focus(); } } }, "Rename"),
    el("button", { type: "button", disabled: index === 0, on: { click: () => move(index, index - 1) }, "aria-label": `Move ${item.title} up` }, "Up"),
    el("button", { type: "button", disabled: index === state.items.length - 1, on: { click: () => move(index, index + 1) }, "aria-label": `Move ${item.title} down` }, "Down"),
    el("button", { type: "button", class: "danger", on: { click: () => remove(item) }, "aria-label": `Delete ${item.title}` }, "Delete"),
  );
  return el("li", {}, el("label", { class: "check" }, checkbox, title), controls);
}

function editForm(item) {
  const input = el("input", { type: "text", id: `edit-${item.id}`, maxlength: "60", value: item.title, "aria-label": "New name", autocomplete: "off" });
  return el("form", {
    class: "stack",
    on: {
      submit: async (event) => {
        event.preventDefault();
        const title = input.value.trim();
        if (!title) return;
        state.editingId = null;
        await mutate(() => api(`/api/shopping/${item.id}`, { method: "PATCH", body: { version: item.version, title }, csrf: state.session.csrfToken }), "Renamed.");
      },
      keydown: (event) => {
        if (event.key === "Escape") { state.editingId = null; renderList(); }
      },
    },
  },
  input,
  el("div", { class: "row" },
    el("button", { type: "submit", class: "primary" }, "Save"),
    el("button", { type: "button", on: { click: () => { state.editingId = null; renderList(); } } }, "Cancel")));
}

// Swap is sent as a full renumbering so positions stay unique. Each write is version-checked.
async function move(from, to) {
  const order = [...state.items];
  [order[from], order[to]] = [order[to], order[from]];
  const changes = order
    .map((item, index) => ({ item, index }))
    .filter(({ item, index }) => item.position !== index);
  await mutate(async () => {
    for (const { item, index } of changes) {
      const current = state.items.find((i) => i.id === item.id);
      await api(`/api/shopping/${item.id}`, { method: "PATCH", body: { version: current.version, position: index }, csrf: state.session.csrfToken });
    }
  }, "Order saved.");
}

async function remove(item) {
  if (!window.confirm(`Delete ${item.title}?`)) return;
  await mutate(() => api(`/api/shopping/${item.id}?version=${item.version}`, { method: "DELETE", csrf: state.session.csrfToken }), "Deleted.");
}

// Runs a write, then reloads. A conflict means another family member changed the list first.
async function mutate(write, success) {
  try {
    await write();
    setStatus(success);
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      setStatus("Someone else changed this list. It has been reloaded; please try again.", true);
    } else {
      setStatus(error.message || "Could not save. Please try again.", true);
    }
  }
  await loadItems();
  renderList();
}

function calendarView() {
  return el("section", {},
    el("h2", { tabindex: "-1" }, "Calendar"),
    el("div", { class: "card" },
      el("p", {}, "The calendar is not connected yet."),
      el("p", { class: "muted" }, "When it is connected, upcoming family events will show here. Events are read-only in the Hub: change them in the calendar app they come from."),
    ),
  );
}

function settingsView() {
  const s = state.session;
  const children = [
    el("h2", { tabindex: "-1" }, "Settings"),
    el("div", { class: "card" },
      el("p", {}, `Signed in as ${s.displayName}`),
      el("p", { class: "muted" }, s.role === "admin" ? "Household admin" : "Household member"),
      el("button", { type: "button", on: { click: signOut } }, "Sign out"),
    ),
  ];
  if (s.role === "admin") children.push(devicesSection());
  children.push(el("div", { class: "card" },
    el("h3", {}, "Shopping Shortcut"),
    el("p", { class: "muted" }, "Follow shortcuts/README.md in the repository to add items from Siri or the Shortcuts app. Never share a Shortcut that contains a token."),
  ));
  return el("section", {}, children);
}

function devicesSection() {
  const nameInput = el("input", { type: "text", id: "device-name", maxlength: "60", required: true, autocomplete: "off" });
  const kind = el("select", { id: "device-kind" },
    el("option", { value: "display" }, "Kindle display (picture only)"),
    el("option", { value: "shortcut" }, "Shortcut (add items only)"));
  const list = state.devices.length
    ? el("ul", { class: "list", "aria-label": "Devices" }, state.devices.map((device) => deviceRow(device)))
    : el("p", { class: "muted" }, "No devices yet.");
  return el("section", {},
    el("h2", { tabindex: "-1" }, "Devices"),
    state.newToken ? tokenCard(state.newToken) : null,
    list,
    el("div", { class: "card" },
      el("h3", {}, "Add a device"),
      el("form", {
        class: "stack",
        on: {
          submit: async (event) => {
            event.preventDefault();
            const name = nameInput.value.trim();
            if (!name) return;
            try {
              const created = await api("/api/admin/devices", { method: "POST", body: { name, kind: kind.value }, csrf: state.session.csrfToken });
              state.newToken = { name, token: created.token };
              setStatus("Device created. Copy its token now.");
              await loadDevices();
              renderView();
            } catch {
              setStatus("Could not create the device.", true);
            }
          },
        },
      },
      el("label", { for: "device-name" }, "Name"), nameInput,
      el("label", { for: "device-kind" }, "Type"), kind,
      el("button", { type: "submit", class: "primary" }, "Create device"))),
    );
}

function deviceRow(device) {
  return el("li", {},
    el("span", { class: "item-title" }, device.name),
    el("span", { class: "badge" }, `${device.kind === "display" ? "Kindle display" : "Shortcut"} · ${device.active ? "active" : "revoked"}`),
    device.active ? el("div", { class: "row" },
      el("button", { type: "button", on: { click: () => rotate(device) }, "aria-label": `Rotate token for ${device.name}` }, "Rotate token"),
      el("button", { type: "button", class: "danger", on: { click: () => revoke(device) }, "aria-label": `Revoke ${device.name}` }, "Revoke")) : null,
  );
}

function tokenCard(newToken) {
  return el("div", { class: "card", role: "region", "aria-label": "New token" },
    el("h3", {}, `Token for ${newToken.name}`),
    el("p", {}, "Copy this now. It will not be shown again."),
    el("p", { class: "code", id: "token-value" }, newToken.token),
    el("div", { class: "row" },
      el("button", { type: "button", on: { click: async () => {
        try { await navigator.clipboard.writeText(newToken.token); setStatus("Token copied."); }
        catch { setStatus("Copy failed. Select the token and copy it by hand.", true); }
      } } }, "Copy token"),
      el("button", { type: "button", on: { click: () => { state.newToken = null; renderView(); } } }, "Done")),
  );
}

async function rotate(device) {
  if (!window.confirm(`Rotate the token for ${device.name}? The old token stops working at once.`)) return;
  try {
    const rotated = await api(`/api/admin/devices/${device.id}/rotate`, { method: "POST", csrf: state.session.csrfToken });
    state.newToken = { name: device.name, token: rotated.token };
    setStatus("Token rotated. Copy the new token now.");
    renderView();
  } catch {
    setStatus("Could not rotate the token.", true);
  }
}

async function revoke(device) {
  if (!window.confirm(`Revoke ${device.name}? It will stop working at once.`)) return;
  try {
    await api(`/api/admin/devices/${device.id}`, { method: "DELETE", csrf: state.session.csrfToken });
    setStatus("Device revoked.");
    await loadDevices();
    renderView();
  } catch {
    setStatus("Could not revoke the device.", true);
  }
}

async function signOut() {
  try {
    await api("/api/logout", { method: "POST", csrf: state.session.csrfToken });
  } catch {
    // Signing out locally is still the right result if the session already expired.
  }
  state.session = null;
  state.newToken = null;
  render();
}

// ---- Shell ------------------------------------------------------------------

function formatTime(iso) {
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: state.snapshot?.timezone ?? "Europe/London" })
    .format(new Date(iso));
}

function currentRoute() {
  const match = /^#\/(home|shopping|calendar|settings)$/.exec(location.hash);
  return match ? match[1] : "home";
}

function renderView() {
  const view = $("#view");
  const tabs = $("#tabs");
  if (!state.session) {
    tabs.hidden = true;
    $("#who").textContent = "";
    view.replaceChildren(signInView());
    focusHeading();
    return;
  }
  tabs.hidden = false;
  $("#who").textContent = `${state.session.displayName} · ${state.session.role === "admin" ? "Admin" : "Member"}`;
  for (const link of tabs.querySelectorAll("a")) {
    if (link.dataset.tab === state.route) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  const views = { home: homeView, shopping: shoppingView, calendar: calendarView, settings: settingsView };
  view.replaceChildren(views[state.route]());
  if (state.route === "shopping") renderList();
  focusHeading();
}

function render() {
  state.route = currentRoute();
  renderView();
}

async function refresh() {
  try {
    if (state.session) {
      await Promise.all([loadSnapshot(), loadItems(), loadDevices()]);
    }
    setStatus("");
  } catch (error) {
    setStatus(error.status === 401 ? "Your session has ended. Please sign in again." : "Could not load. Check the connection and try again.", true);
    if (error.status === 401) { state.session = null; }
  }
  render();
}

async function start() {
  state.health = await api("/api/health").catch(() => ({ signIn: "unavailable" }));
  await loadSession();
  if (state.session) {
    await Promise.all([loadSnapshot(), loadItems(), loadDevices()]).catch(() => setStatus("Could not load the list.", true));
  }
  render();
}

// Each tab loads its own data when opened, so changes made on another phone show up without a full reload.
async function showRoute() {
  state.route = currentRoute();
  if (state.session) {
    try {
      if (state.route === "home") await loadSnapshot();
      if (state.route === "shopping") await loadItems();
      if (state.route === "settings") await loadDevices();
    } catch (error) {
      setStatus(error.status === 401 ? "Your session has ended. Please sign in again." : "Could not load. Check the connection and try again.", true);
    }
  }
  renderView();
}

window.addEventListener("hashchange", showRoute);

// Pick up other family members' changes when this phone's tab comes back into view.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && state.session && state.route === "shopping" && !state.editingId) {
    loadItems().then(renderList).catch(() => {});
  }
});

start();
