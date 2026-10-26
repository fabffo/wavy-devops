/* Run with Windows Node + installed Chrome, after authorization and fixture setup.
 * Input: private JSON {email,password,companyIds:[A1,A2]} outside the repository.
 * No request mocking, TLS bypass, saved cookies, traces or raw HAR.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.WAVY_PLAYWRIGHT_CORE);
const { diagnostics } = require('./chrome-diagnostics.cjs');
const origin = 'https://recettelocal.wavyservices.fr';

async function main() {
  const [input, directory] = process.argv.slice(2);
  if (!input || !directory || !fs.statSync(directory).isDirectory()) throw new Error('PRIVATE_INPUT_REQUIRED');
  const fixture = JSON.parse(fs.readFileSync(input, 'utf8'));
  if (!fixture.email?.endsWith('@example.invalid') || !fixture.password ||
      fixture.companyIds?.length !== 2 || !fixture.companyIds.every(Number.isSafeInteger)) {
    throw new Error('DEDICATED_FIXTURE_REQUIRED');
  }
  const result = { origin, checks: [], blockedRequests: 0, pageErrors: 0,
    apiErrors: [], requestCount: 0, loginCount: 0, browser: null, passed: false, tlsVerified: true, mockedResponses: false };
  const output = path.join(directory, 'chrome-navigation-results.json');
  const diag = diagnostics(directory, [fixture.password, fixture.email]);
  const stage = name => { result.stage = name; diag.stage(name); };
  const record = (control, passed) => {
    result.checks.push({ control, passed: !!passed });
    fs.writeFileSync(output, JSON.stringify(result, null, 2));
    if (!passed) throw new Error('BROWSER_ASSERTION_FAILED');
  };
  let browser, page;
  try {
    stage('launch-Chrome');
    browser = await chromium.launch({ channel: 'chrome', headless: false });
    result.browser = browser.version(); diag.result.browser = result.browser;
    const context = await browser.newContext({ ignoreHTTPSErrors: false, serviceWorkers: 'block' });
    diag.attach(context);
    const allowed = new Set(['POST /api/auth/session', 'POST /api/auth/session/societe',
      'DELETE /api/auth/session']);
    // Fail closed for every nonlocal request and every unrelated API mutation.
    await context.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      result.requestCount++;
      if (request.method() === 'POST' && url.pathname === '/api/auth/session') result.loginCount++;
      if (result.requestCount > 200 || url.origin !== origin ||
          (!['GET', 'HEAD', 'OPTIONS'].includes(request.method()) &&
           !allowed.has(request.method() + ' ' + url.pathname))) {
        result.blockedRequests++;
        diag.blocked(request);
        return route.abort('blockedbyclient');
      }
      return route.continue();
    });
    const successes = new Set();
    context.on('response', response => {
      const url = new URL(response.url());
      if (url.origin === origin && url.pathname.startsWith('/api/')) {
        if (response.ok()) successes.add(url.pathname);
        else if (response.status() >= 400 && url.pathname !== '/api/auth/session') {
          result.apiErrors.push({ path: url.pathname, status: response.status() });
        }
      }
    });
    page = await context.newPage();
    page.on('pageerror', () => result.pageErrors++);
    stage('open-ERP');
    await diag.navigation(await page.goto(origin, { waitUntil: 'domcontentloaded' }));
    stage('locate-email-input');
    await page.getByLabel('Adresse email').fill(fixture.email);
    stage('locate-password-input');
    await page.getByLabel('Mot de passe').fill(fixture.password);
    stage('login');
    const loginResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/auth/session' && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Se connecter', exact: true }).click();
    record('login-real-POST-200', (await loginResponse).status() === 200);
    await page.getByRole('heading', { name: /Bonjour/ }).waitFor();
    await page.locator('.kpis').waitFor();
    record('dashboard-rendered-with-indicators', true);
    await page.screenshot({ path: path.join(directory, 'dashboard.png') });
    for (const [module, label, apiPrefix] of [
      ['socle', 'Sociétés', '/api/contexte'],
      ['tiers', 'Tous les tiers', '/api/tiers'],
      ['contrats', 'Tous les contrats', '/api/contrats'],
      ['factures', 'Factures de vente', '/api/factures'],
      ['tresorerie', 'Opérations bancaires', '/api/tresorerie']
    ]) {
      stage('module-' + module);
      successes.clear();
      await page.getByRole('button', { name: label, exact: true }).click();
      const iframe = page.locator('iframe[title="Module Wavy"]');
      await iframe.waitFor();
      const src = new URL(await iframe.getAttribute('src'), origin);
      record(module + '-same-origin-iframe', src.origin === origin && src.pathname.startsWith('/modules/' + module + '/'));
      const frame = page.frameLocator('iframe[title="Module Wavy"]');
      await frame.locator('h1,h2').first().waitFor();
      await page.waitForFunction(() => !document.querySelector('.splash'));
      // Poll only already-observed browser responses, never generate another API call.
      for (let attempt = 0; attempt < 50 && ![...successes].some(p => p.startsWith(apiPrefix)); attempt++) {
        await page.waitForTimeout(200);
      }
      record(module + '-backend-data-loaded', [...successes].some(p => p.startsWith(apiPrefix)));
      record(module + '-no-secondary-login', await frame.getByRole('button', { name: 'Se connecter', exact: true }).count() === 0);
      await page.screenshot({ path: path.join(directory, module + '.png') });
    }
    for (const companyId of [fixture.companyIds[1], fixture.companyIds[0]]) {
      stage('company-switch');
      const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/auth/session/societe' && r.request().method() === 'POST');
      await page.getByLabel('Société courante').selectOption(String(companyId));
      const changed = await response;
      record('company-switch-POST-200', changed.status() === 200);
      record('company-switch-server-context', (await changed.json()).societeCouranteId === companyId);
      record('company-selector-updated', await page.getByLabel('Société courante').inputValue() === String(companyId));
    }
    stage('logout');
    await page.locator('button.profile').click();
    const logoutResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/auth/session' && r.request().method() === 'DELETE');
    await page.getByRole('button', { name: 'Se déconnecter', exact: true }).click();
    record('logout-real-DELETE', [200, 204].includes((await logoutResponse).status()));
    await page.getByRole('button', { name: 'Se connecter', exact: true }).waitFor();
    record('logout-login-form-returned', true);
    record('logout-server-session-invalidated', (await context.request.get(origin + '/api/auth/session')).status() === 401);
    record('no-unexpected-mutations-or-external-requests', result.blockedRequests === 0);
    record('no-JavaScript-errors', result.pageErrors === 0);
    record('no-module-API-errors', result.apiErrors.length === 0);
    result.passed = true;
    stage('completed');
    await diag.finish(page);
    await context.close();
  } catch (error) {
    await diag.finish(page, error);
    throw error;
  } finally {
    fs.writeFileSync(output, JSON.stringify(result, null, 2));
    if (browser) await browser.close();
  }
}
main().catch(() => { console.error('Chrome qualification failed; inspect private sanitized results.'); process.exitCode = 1; });
