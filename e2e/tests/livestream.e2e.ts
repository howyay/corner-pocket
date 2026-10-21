import assert from 'node:assert/strict';
import { test } from '@e2e-dev/web';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

test('the Livestream tab shows its status line and source chips', async ({ app, browser }) => {
  await app.open('/#/vision');
  let panel = { status: '', chips: 0 };
  for (let i = 0; i < 80 && (panel.status === '' || panel.chips === 0); i += 1) {
    panel = await browser.evaluate(() => ({
      status: ((document.querySelector('#live-panel-status') as HTMLElement | null)?.textContent ?? '').trim(),
      chips: document.querySelectorAll('.vs-chip').length,
    }));
    if (panel.status === '' || panel.chips === 0) await wait(250);
  }
  assert.ok(panel.status.length > 0, 'the panel writes its status');
  assert.match(panel.status, /idle|live|starting|stopped|error|重放|直播/i);
  assert.ok(panel.chips >= 1, 'at least one source chip is offered');
});
