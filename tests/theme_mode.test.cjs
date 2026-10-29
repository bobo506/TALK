'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '..', 'web', 'theme.js'), 'utf8');

function harness({ hour = 12, stored = null } = {}) {
  const storage = new Map(stored ? [['talk-theme-mode', stored]] : []);
  const buttons = ['auto', 'light', 'dark'].map(mode => {
    const listeners = [];
    return {
      dataset: { themeMode: mode }, className: '', attributes: {},
      classList: { toggle(name, on) { this.owner.className = on ? 'is-active' : ''; } },
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(type, fn) { listeners.push(fn); },
      closest(selector) { return selector === '[data-theme-mode]' ? this : null; },
      fire() { for (const fn of listeners) fn({ target: this }); },
      get textContent() { return mode; },
    };
  });
  const root = { dataset: {} };
  const groupListeners = [];
  const group = {
    contains: () => true,
    addEventListener(type, fn) { groupListeners.push(fn); },
  };
  for (const button of buttons) button.classList.owner = button;
  const document = {
    readyState: 'complete',
    documentElement: root,
    hidden: false,
    getElementById: id => (id === 'theme-switch' ? group : null),
    querySelectorAll: () => buttons,
    addEventListener() {},
  };
  const context = {
    document,
    console,
    Promise,
    JSON,
    Date: class extends Date { constructor(...args) { super(...(args.length ? args : [2026, 9, 29, hour, 0, 0])); } },
    setTimeout: () => 1,
    clearTimeout: () => {},
    localStorage: {
      getItem: key => (storage.has(key) ? storage.get(key) : null),
      setItem: (key, value) => storage.set(key, value),
    },
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(source, context);
  const click = mode => {
    const button = buttons.find(item => item.dataset.themeMode === mode);
    for (const fn of groupListeners) fn({ target: button });
  };
  return { context, root, buttons, storage, click };
}

test('自动模式：08:00–18:00 为白天，其余为夜间', () => {
  const cases = [[7, 'dark'], [8, 'light'], [12, 'light'], [17, 'light'], [18, 'dark'], [23, 'dark']];
  for (const [hour, theme] of cases) {
    const h = harness({ hour, stored: 'auto' });
    assert.equal(h.root.dataset.theme, theme, `hour=${hour}`);
    assert.equal(h.root.dataset.themeMode, 'auto');
  }
});

test('固定白天/夜间不受时间影响', () => {
  const day = harness({ hour: 23, stored: 'light' });
  assert.equal(day.root.dataset.theme, 'light');
  const night = harness({ hour: 12, stored: 'dark' });
  assert.equal(night.root.dataset.theme, 'dark');
});

test('未知存储值回落到自动', () => {
  const h = harness({ hour: 23, stored: 'rainbow' });
  assert.equal(h.root.dataset.themeMode, 'auto');
  assert.equal(h.root.dataset.theme, 'dark');
});

test('点击切换：写入本地存储、更新 data-theme 与选中态', () => {
  const h = harness({ hour: 23, stored: 'auto' });
  h.click('light');
  assert.equal(h.storage.get('talk-theme-mode'), 'light');
  assert.equal(h.root.dataset.theme, 'light');
  assert.equal(h.root.dataset.themeMode, 'light');
  const active = h.buttons.filter(button => button.className === 'is-active').map(button => button.dataset.themeMode);
  assert.deepEqual(active, ['light']);
  assert.equal(h.buttons.find(button => button.dataset.themeMode === 'light').attributes['aria-pressed'], 'true');
  assert.equal(h.buttons.find(button => button.dataset.themeMode === 'auto').attributes['aria-pressed'], 'false');
});

test('顶部控件固定三段，顺序为 自动/白天/夜间', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
  const group = html.match(/<div id="theme-switch"[\s\S]*?<\/div>/);
  assert.ok(group, '存在 theme-switch');
  const modes = [...group[0].matchAll(/data-theme-mode="([a-z]+)"/g)].map(match => match[1]);
  assert.deepEqual(modes, ['auto', 'light', 'dark']);
  assert.match(html, /<script src="\/theme\.js\?v=/);
  assert.match(html, /dataset\.theme/, '首屏前置脚本存在');
});
