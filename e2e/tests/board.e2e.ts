import assert from 'node:assert/strict';
import { test } from '@e2e-dev/web';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

test('the public board renders the night', async ({ app, browser }) => {
  await app.open('http://127.0.0.1:8132/board');
  let text = '';
  for (let i = 0; i < 80 && !/Corner Pocket/.test(text); i += 1) {
    text = await browser.evaluate(() => (document.body.textContent ?? '').replace(/\s+/g, ' ').trim());
    if (!/Corner Pocket/.test(text)) await wait(250);
  }
  assert.match(text, /Corner Pocket/, 'the board carries its title');
  assert.match(text, /On the tables|The board is off tonight/, 'the board shows its table state');
});
