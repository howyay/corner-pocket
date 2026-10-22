import assert from 'node:assert/strict';
import { test } from '@e2e-dev/web';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// The review workbench gives its pixels to the picture, and the strip's controls never overlap.
test('the video player fills its column and keeps its controls apart', async ({ app, browser }) => {
  await app.open('/#/records/review/2903032282');
  let ready = false;
  for (let i = 0; i < 240 && !ready; i += 1) {
    ready = await browser.evaluate(() => {
      const img = document.querySelector('#t-img') as HTMLImageElement | null;
      return !!(img && img.naturalWidth > 0 && !document.querySelector('.stage-empty:not([hidden])'));
    });
    if (!ready) await wait(250);
  }
  assert.ok(ready, 'the stage painted a decoded frame');
  // The strip is taller while its overlays load; measure the settled workbench.
  for (let i = 0; i < 240; i += 1) {
    const loading = await browser.evaluate(() => !!document.querySelector('.vs-strip[data-loading="1"]'));
    if (!loading) break;
    await wait(250);
  }
  const m = await browser.evaluate(() => {
    const rect = (el: Element | null) => (el ? el.getBoundingClientRect() : null);
    const img = document.querySelector('#t-img') as HTMLImageElement;
    const frame = rect(img)!;
    const stage = rect(document.querySelector('.vs-stage'))!;
    const strip = rect(document.querySelector('.vs-strip'))!;
    const kids = [...document.querySelectorAll('.vs-transport > *')]
      .map((el) => el.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
    let overlaps = 0;
    for (let i = 0; i < kids.length; i += 1) for (let j = i + 1; j < kids.length; j += 1) {
      const a = kids[i], b = kids[j];
      if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) overlaps += 1;
    }
    const play = document.querySelector('.vs-transport > *:not([hidden])');
    return {
      vw: innerWidth, vh: innerHeight,
      frameW: Math.round(frame.width), frameH: Math.round(frame.height),
      stageW: Math.round(stage.width), stageH: Math.round(stage.height),
      naturalW: img.naturalWidth,
      stripBottom: Math.round(strip.bottom), overlaps,
      firstControl: (play as HTMLElement | null)?.id ?? '',
      pageScroll: document.documentElement.scrollHeight - innerHeight,
    };
  });
  // The picture fills its stage in one direction (it is limited by width or by height), or it
  // already shows at its native size. Before the fix it left dead bands on both axes.
  const fills = m.frameW >= m.stageW - 2 || m.frameH >= m.stageH - 2 || m.frameW >= m.naturalW;
  assert.ok(fills, `the frame fills the stage (${m.frameW}x${m.frameH} in ${m.stageW}x${m.stageH})`);
  assert.ok(m.stripBottom <= m.vh + 1, 'the control strip stays on the screen');
  assert.equal(m.overlaps, 0, 'no transport control paints over another');
  assert.equal(m.pageScroll, 0, 'the workbench fits the screen; the page does not scroll');
});
