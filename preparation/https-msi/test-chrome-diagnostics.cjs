'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { diagnostics } = require('./chrome-diagnostics.cjs');
test('saved failures omit credentials, cookies, bearer values and URL query tokens', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'wavy-diag-test-'));
  try {
    const diag = diagnostics(directory, ['private-password']);
    diag.stage('locate-password-input');
    await diag.finish(null, new Error('private-password qa@example.invalid WAVY_SESSION=secret-cookie Bearer token https://local/path?code=private-token'));
    const saved = fs.readFileSync(path.join(directory, 'chrome-diagnostics.json'), 'utf8');
    for (const secret of ['private-password', 'qa@example.invalid', 'secret-cookie', 'Bearer token', 'private-token']) assert.ok(!saved.includes(secret));
    assert.equal(JSON.parse(saved).stage, 'locate-password-input');
  } finally { fs.rmSync(directory, { recursive: true }); }
});
test('capture masks form fields and removes tokens from final URL', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'wavy-diag-test-'));
  try {
    const diag = diagnostics(directory); let mask;
    const page = { url: () => 'https://local/connexion?token=hidden#secret', isClosed: () => false,
      locator: selector => selector, screenshot: async options => { mask = options.mask; } };
    await diag.finish(page);
    const saved = JSON.parse(fs.readFileSync(path.join(directory, 'chrome-diagnostics.json')));
    assert.equal(saved.finalUrl, 'https://local/connexion');
    assert.deepEqual(mask, ['input,textarea,[contenteditable],[data-sensitive]']);
    assert.equal(saved.tlsBypass, false);
  } finally { fs.rmSync(directory, { recursive: true }); }
});
test('failed requests preserve method/resource/error but never headers or body', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'wavy-diag-test-'));
  try {
    const diag = diagnostics(directory), listeners = {};
    diag.attach({ on: (name, fn) => { listeners[name] = fn; } });
    listeners.requestfailed({ url: () => 'https://local/api/auth/session?secret=hidden',
      method: () => 'GET', resourceType: () => 'xhr', failure: () => ({ errorText: 'net::ERR_CERT_AUTHORITY_INVALID' }) });
    await diag.finish(null);
    const saved = JSON.parse(fs.readFileSync(path.join(directory, 'chrome-diagnostics.json')));
    assert.deepEqual(saved.failedRequests, [{ url: 'https://local/api/auth/session', method: 'GET', resource: 'xhr', error: 'net::ERR_CERT_AUTHORITY_INVALID' }]);
  } finally { fs.rmSync(directory, { recursive: true }); }
});
test('a pending session XHR is retained even without response or network error', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'wavy-diag-test-'));
  try {
    const diag = diagnostics(directory), listeners = {};
    diag.attach({ on: (name, fn) => { listeners[name] = fn; } });
    listeners.request({ url: () => 'https://local/api/auth/session', method: () => 'GET', resourceType: () => 'xhr' });
    await diag.finish(null);
    const saved = JSON.parse(fs.readFileSync(path.join(directory, 'chrome-diagnostics.json')));
    assert.deepEqual(saved.pendingRequests, [{ url: 'https://local/api/auth/session', method: 'GET', resource: 'xhr' }]);
  } finally { fs.rmSync(directory, { recursive: true }); }
});
