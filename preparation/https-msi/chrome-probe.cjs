'use strict';
// Installed Windows Chrome, real local HTTPS, anonymous GET only; no Wavy service start.
const fs = require('node:fs'), path = require('node:path');
const dns = require('node:dns').promises;
const { chromium } = require(process.env.WAVY_PLAYWRIGHT_CORE);
const { diagnostics } = require('./chrome-diagnostics.cjs');
const origin = 'https://recettelocal.wavyservices.fr';
async function main() {
  const directory = process.argv[2];
  if (!directory || !fs.statSync(directory).isDirectory()) throw new Error('PRIVATE_OUTPUT_REQUIRED');
  const diag = diagnostics(directory);
  let browser, page, failure;
  try {
    diag.stage('Windows-DNS');
    diag.result.dns = await dns.lookup(new URL(origin).hostname, { all: true });
    if (!diag.result.dns.every(x => ['127.0.0.1', '::1'].includes(x.address))) throw new Error('NONLOCAL_DNS_REFUSED');
    diag.stage('launch-Chrome');
    browser = await chromium.launch({ channel: 'chrome', headless: false });
    diag.result.browser = browser.version();
    const context = await browser.newContext({ ignoreHTTPSErrors: false, serviceWorkers: 'block' });
    diag.attach(context);
    await context.route('**/*', route => {
      const r = route.request();
      const u = new URL(r.url());
      if (u.origin !== origin || !['GET', 'HEAD', 'OPTIONS'].includes(r.method()) ||
          (u.pathname.startsWith('/api/') && u.pathname !== '/api/auth/session') || u.pathname.startsWith('/modules/')) {
        diag.blocked(r); return route.abort('blockedbyclient');
      }
      return route.continue();
    });
    page = await context.newPage();
    diag.stage('HTTPS-navigation');
    await diag.navigation(await page.goto(origin, { waitUntil: 'domcontentloaded', timeout: 15000 }));
    if (process.argv.includes('--expect-login')) {
      diag.stage('locate-email-input');
      const permissions = () => page.evaluate(async () => {
        const values = {};
        for (const name of ['local-network', 'loopback-network']) {
          try { values[name] = (await navigator.permissions.query({ name })).state; }
          catch { values[name] = 'unsupported'; }
        }
        return values;
      });
      diag.result.localPermissionsBefore = await permissions();
      await page.getByLabel('Adresse email').waitFor({ state: 'visible', timeout: 15000 });
      diag.stage('locate-password-input');
      await page.getByLabel('Mot de passe').waitFor({ state: 'visible', timeout: 5000 });
    }
    diag.result.dom = await page.evaluate(() => ({ title: document.title,
      diagnostic: document.body.innerText.includes('Wavy RECETTE LOCALE - HTTPS OK'),
      appRoot: !!document.querySelector('app-root'), scripts: document.scripts.length,
      emailInputs: document.querySelectorAll('input[type=email]').length }));
    if (diag.result.navigation.status !== 200 || !['127.0.0.1', '::1'].includes(diag.result.navigation.server?.ipAddress)) throw new Error('LOCAL_HTTPS_FAILED');
    diag.stage('HTTPS-readonly-probe-complete');
  } catch (error) { failure = error; }
  finally { await diag.finish(page, failure); if (browser) await browser.close(); }
  if (failure) throw failure;
}
main().catch(() => { console.error('Read-only Chrome probe failed; see sanitized diagnostics.'); process.exitCode = 1; });
