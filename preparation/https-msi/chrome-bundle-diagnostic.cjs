'use strict';
// UI-only reproduction of the pinned ERP bundle with a synthetic anonymous 401.
// No backend, credentials, real authentication, service start or business writes.
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require(process.env.WAVY_PLAYWRIGHT_CORE);
const { diagnostics } = require('./chrome-diagnostics.cjs');
const origin = 'https://recettelocal.wavyservices.fr';
async function main() {
  const [bundle, directory] = process.argv.slice(2), diag = diagnostics(directory);
  diag.result.scope = 'PINNED_STATIC_BUNDLE_SYNTHETIC_ANONYMOUS_401_NOT_BACKEND_QUALIFICATION';
  diag.result.mockedResponses = true;
  let browser, page, failure;
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: false });
    diag.result.browser = browser.version();
    const context = await browser.newContext({ ignoreHTTPSErrors: false, serviceWorkers: 'block' });
    diag.attach(context);
    await context.route('**/*', route => {
      const request = route.request(), u = new URL(request.url());
      if (u.origin !== origin || request.method() !== 'GET') {
        diag.blocked(request); return route.abort('blockedbyclient');
      }
      if (u.pathname === '/api/auth/session') return route.fulfill({ status: 401, contentType: 'application/json', body: '{}' });
      if (u.pathname.startsWith('/api/')) return route.abort('blockedbyclient');
      const relative = decodeURIComponent(u.pathname).replace(/^\/+/, '') || 'index.html';
      const file = path.resolve(bundle, relative);
      if (!file.startsWith(path.resolve(bundle) + path.sep)) return route.abort('blockedbyclient');
      const actual = fs.existsSync(file) && fs.statSync(file).isFile() ? file : path.join(bundle, 'index.html');
      const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2' };
      return route.fulfill({ status: 200, contentType: types[path.extname(actual)] || 'application/octet-stream', body: fs.readFileSync(actual) });
    });
    page = await context.newPage();
    diag.stage('render-pinned-ERP-bundle');
    await diag.navigation(await page.goto(origin, { waitUntil: 'domcontentloaded' }));
    diag.stage('locate-email-input');
    await page.getByLabel('Adresse email').waitFor({ state: 'visible', timeout: 10000 });
    await page.getByLabel('Adresse email').fill('qa.pwa.0123456789ab.a-owner@example.invalid');
    diag.stage('locate-password-input');
    await page.getByLabel('Mot de passe').waitFor({ state: 'visible', timeout: 5000 });
    await page.getByLabel('Mot de passe').fill('SYNTHETIC_OFFLINE_ONLY');
    diag.result.selectors = { email: await page.getByLabel('Adresse email').count(),
      password: await page.getByLabel('Mot de passe').count(), login: await page.getByRole('button', { name: 'Se connecter', exact: true }).count(),
      formValid: await page.locator('form').evaluate(form => form.checkValidity()) };
    diag.stage('login-selectors-ready-no-submission');
  } catch (error) { failure = error; }
  finally { await diag.finish(page, failure); if (browser) await browser.close(); }
  if (failure) throw failure;
}
main().catch(() => { console.error('Static bundle UI reproduction failed; see sanitized diagnostics.'); process.exitCode = 1; });
