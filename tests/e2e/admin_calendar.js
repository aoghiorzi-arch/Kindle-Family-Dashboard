// Browser end-to-end check of household settings: members, location, calendar import, Shortcuts tokens and roles.
// Run by tests/test_e2e.py with E2E_BASE, E2E_USER (an admin) and E2E_PASS set. Exit code 77 means Playwright is not installed.
let chromium;
try {
  ({chromium} = require('playwright'));
} catch (e) {
  console.log('playwright is not installed');
  process.exit(77);
}

const base = process.env.E2E_BASE;
const admin = process.env.E2E_USER;
const adminPass = process.env.E2E_PASS;
const memberName = 'ava';
const memberPass = 'a long pass 1';

function check(condition, message) {
  if (!condition) throw new Error(message);
}

// Today's date in the household time zone, as YYYYMMDD.
function londonDayStamp() {
  return new Date().toLocaleDateString('en-CA', {timeZone: 'Europe/London'}).replace(/-/g, '');
}

async function signIn(page, username, password) {
  await page.goto(base + '/');
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.click('#loginForm button');
}

async function shortcutStatus(page, token) {
  return page.evaluate(async t => (await fetch('/api/shortcut/shopping', {
    method: 'POST',
    headers: {'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json'},
    body: JSON.stringify({title: 'Oat milk'}),
  })).status, token);
}

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport: {width: 390, height: 844}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const frame = async () => (await page.context().request.get(base + '/frame.png')).body();

    await signIn(page, admin, adminPass);
    await page.waitForSelector('#admin:not([hidden])');

    // Members: add one, who should then appear in the list.
    await page.fill('#newUser', memberName);
    await page.fill('#newPass', memberPass);
    await page.click('#memberForm button');
    await page.waitForSelector(`#members li:has-text("${memberName}")`);

    // Location: save, which the calendar import needs.
    await page.fill('#lat', '51.5074');
    await page.fill('#lon', '-0.1278');
    await page.fill('#tz', 'Europe/London');
    await page.click('#locationForm button');
    await page.waitForSelector('#status:has-text("Location saved")');

    // Calendar: import one private event for today and one recurring event (which is skipped).
    const before = await frame();
    const day = londonDayStamp();
    const ics = [
      'BEGIN:VCALENDAR',
      'BEGIN:VEVENT', 'UID:browser-1', `DTSTART:${day}T120000Z`, 'SUMMARY:Doctor', 'CLASS:PRIVATE', 'END:VEVENT',
      'BEGIN:VEVENT', 'UID:browser-2', `DTSTART:${day}T090000Z`, 'RRULE:FREQ=DAILY', 'SUMMARY:Daily', 'END:VEVENT',
      'END:VCALENDAR',
    ].join('\n');
    await page.fill('#ics', ics);
    await page.click('#calendarForm button');
    await page.waitForSelector('#status:has-text("Calendar imported")');
    check((await page.textContent('#status')).includes('Calendar imported: 1 events. 1 recurring'),
      'calendar import summary was not shown');
    check(!before.equals(await frame()), 'importing today\'s calendar did not change the preview');

    // Shortcuts: create a token, use it, revoke it, and check it stops working.
    await page.fill('#tokenName', 'Test phone');
    await page.click('#tokenForm button');
    await page.waitForSelector('#newToken:not([hidden])');
    const token = await page.textContent('#tokenValue');
    check(token.startsWith('kfd_'), 'token was not shown');
    check(await shortcutStatus(page, token) === 201, 'new token could not add a shopping item');
    await page.locator('#tokens li', {hasText: 'Test phone'}).getByRole('button', {name: 'Revoke'}).click();
    await page.waitForSelector('#tokens li:has-text("revoked")');
    check(await shortcutStatus(page, token) === 401, 'revoked token still worked');

    // Clear the imported calendar.
    await page.click('#calendarClear button');
    await page.waitForSelector('#calendarStatus:has-text("No calendar imported")');

    // Calendar feed: add one (the test server answers without the network), check it, then remove it.
    await page.fill('#feedLabel', 'Family');
    await page.fill('#feedUrl', 'https://calendar.example.test/family.ics');
    await page.click('#feedForm button');
    await page.waitForSelector('#status:has-text("Feed added and synced")');
    check((await page.textContent('#feeds li')).includes('calendar.example.test'), 'feed host was not shown');
    check(!(await page.textContent('#feeds')).includes('family.ics'), 'feed address was shown in full');
    await page.locator('#feeds li', {hasText: 'Family'}).getByRole('button', {name: 'Remove'}).click();
    await page.waitForSelector('#feeds li:has-text("Family")', {state: 'detached'});

    // A member signs in: no admin panel is shown.
    await page.click('#logout');
    await page.waitForSelector('#loginForm');
    await signIn(page, memberName, memberPass);
    await page.waitForSelector('#app:not([hidden])');
    check(!(await page.isVisible('#admin')), 'a member can see the admin panel');

    check(errors.length === 0, `page errors: ${errors.join('; ')}`);
    console.log('admin path OK: members, location, calendar import and clear, tokens, and member view');
  } finally {
    await browser.close();
  }
})().catch(e => {
  console.error('FAILED:', e.message);
  process.exitCode = 1;
});
