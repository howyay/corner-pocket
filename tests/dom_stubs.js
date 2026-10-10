'use strict';
// One shared home for the DOM test double that two page suites need.
// tests/test_ops.js and tests/test_app_timeline.js both require this file.
// One change here reaches both suites, so the two harnesses cannot disagree.
// This file starts no test when a suite loads it.
// It requires no test runner module.

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
