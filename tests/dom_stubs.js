'use strict';
// One shared home for the DOM test double that two page suites need.
// tests/test_ops.js and tests/test_app_timeline.js both require this file.
// One change here reaches both suites, so the two harnesses cannot disagree.
// This file starts no test when a suite loads it.
// It requires no test runner module.
//
// Round 43 recorded why the other two doubles stay where they are. Four element doubles exist, and
// each one answers the surface of the module its own suite loads. They are measured, not accidental:
//
//   tests/dom_stubs.js:11 domNode(selector)        35 names, this file
//   tests/test_ops.js:40 richDocument(handlers)    one region per selector, loads annotator/ops.js
//   tests/test_app_timeline.js:46 element()        36 names, loads annotator/app.js
//   tests/test_board.js:209 fakePage({...})        a whole page, loads annotator/board.js
//
// The two big ones disagree on 13 names each way, because they serve different readers. The engine
// double answers the media surface of the review root (`checked`, `disabled`, `files`, `hasAttribute`,
// `load`, `play`, `pause`, `blur`, `getBoundingClientRect`). This file answers the composition surface
// of the console shell (`title`, `attributes`, `insertAdjacentHTML`, `contains`, `toggles`, `appended`,
// `inserted`). No source module reads both surfaces, so a merge would give one suite the needs of
// another suite, and it would hide the disagreement that matters: a name that a loaded module reads
// and the double does not answer. Keep a new name in the double of the suite that reads it, and put it
// here only when both page suites read it.

// Round 34, console candidate 1: render() is the console's whole composition path, and the suite
// never ran it (42 tests replaced it instead). A page-shaped stub lets one test execute it, so the
// nav, the tabbar, the mounted screen, the vision host move and the poll schedule are observable.
function domNode(selector = '') {
  const node = {
    selector, innerHTML: '', textContent: '', hidden: false, value: '', title: '', children: [],
    dataset: {tab: '', lang: '', theme: '', action: ''}, style: {setProperty() {}, getPropertyValue: () => ''},
    classList: {add() {}, remove() {}, toggle(name, on) { node.toggles.push({name, on}) }}, toggles: [], appended: [], inserted: [], attributes: {},
    setAttribute(key, value) { node.attributes[key] = String(value); },
    getAttribute(key) { return Object.prototype.hasOwnProperty.call(node.attributes, key) ? node.attributes[key] : null; },
    removeAttribute() {}, appendChild(child) { node.appended.push(child); node.children.push(child); return child; },
    insertAdjacentHTML(_where, html) { node.inserted.push(html); node.innerHTML += html; },
    addEventListener() {}, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [],
    closest: () => null, contains: () => false, focus() {}, remove() {}
  };
  return node;
}

// A small node for a caller that writes an attribute or a fragment and reads nothing back.
function elementStub() {
  return {setAttribute() {}, insertAdjacentHTML() {}, addEventListener() {}, classList: {add() {}, remove() {}, toggle() {}}};
}

module.exports = {domNode, elementStub};
