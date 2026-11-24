const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

/** Run the actual push event handler with a device snapshot. */
async function deliver(snapshot) {
  const listeners = {};
  let notification;
  vm.runInNewContext(fs.readFileSync('static/sw.js', 'utf8'), {
    self: {
      addEventListener: (event, handler) => { listeners[event] = handler; },
      registration: { showNotification: (title, options) => {
        notification = [title, options.body, options.data.url];
      } },
    },
    caches: { open: async () => ({ match: async () => snapshot && { json: async () => snapshot } }) },
  });
  let completed;
  listeners.push({
    data: { json: () => ({ title: 'Ignored', body: 'Reminder', dailyBody: 'Today' }) },
    waitUntil: promise => { completed = promise; },
  });
  await completed;
  return notification;
}

test('held text wins over daily text with no custom title', async () => {
  assert.deepEqual(await deliver({ mode: 'held', body: 'Held text' }), ['', 'Held text', '/']);
});
test('daily text and missing-snapshot fallback', async () => {
  assert.deepEqual(await deliver({ mode: 'daily' }), ['', 'Today', '/']);
  assert.deepEqual(await deliver(null), ['', 'Reminder', '/']);
});
