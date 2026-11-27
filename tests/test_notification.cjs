const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

/** Run the actual push event handler with a device snapshot. */
async function deliver(snapshot, { trace, stages = [], displayError } = {}) {
  const listeners = {};
  let notification;
  vm.runInNewContext(fs.readFileSync('static/sw.js', 'utf8'), {
    self: {
      addEventListener: (event, handler) => { listeners[event] = handler; },
      registration: { showNotification: (title, options) => {
        if (displayError) throw displayError;
        notification = [title, options.body, options.data.url];
      } },
    },
    AbortController, setTimeout, clearTimeout,
    fetch: async (url, options) => {
      assert.equal(url, '/api/push-receipt');
      stages.push(JSON.parse(options.body).stage);
    },
    caches: { open: async () => ({ match: async () => snapshot && { json: async () => snapshot } }) },
  });
  let completed;
  listeners.push({
    data: { json: () => ({ title: 'Ignored', body: 'Reminder', dailyBody: 'Today', trace }) },
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


test('worker reports receipt and display request for traced pushes', async () => {
  const stages = [];
  await deliver({ mode: 'held', body: 'Held text' }, { trace: 'a'.repeat(48), stages });
  assert.deepEqual(stages, ['received', 'display_requested']);
});

test('display failure reports a separate stage', async () => {
  const stages = [];
  await assert.rejects(deliver(null, { trace: 'b'.repeat(48), stages, displayError: new Error('blocked') }), /blocked/);
  assert.deepEqual(stages, ['received', 'display_failed']);
});
