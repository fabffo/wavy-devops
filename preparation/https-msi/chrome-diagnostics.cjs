'use strict';
const fs = require('node:fs');
const path = require('node:path');

function diagnostics(directory, secrets = []) {
  const redact = value => {
    let text = String(value ?? '');
    for (const secret of secrets.filter(Boolean)) text = text.split(secret).join('[REDACTED]');
    return text.replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '[EMAIL]')
      .replace(/(WAVY_SESSION\s*[=:]\s*|Bearer\s+)[^\s;,"']+/gi, '$1[REDACTED]')
      .replace(/(https?:\/\/[^\s?#"']+)[?#][^\s"']*/g, '$1?[REDACTED]')
      .slice(0, 2000);
  };
  const url = value => {
    try { const u = new URL(value); return ['http:', 'https:'].includes(u.protocol) ? u.origin + u.pathname : '[non-HTTP URL]'; }
    catch { return '[non-HTTP URL]'; }
  };
  const result = { stage: 'launch', finalUrl: null, navigation: null, browser: null,
    javascriptErrors: [], consoleErrors: [], failedRequests: [], responses: [], blockedRequests: [],
    tlsBypass: false, screenshot: null, failure: null };
  const pending = new Map();
  const cap = (list, entry) => { if (list.length < 200) list.push(entry); };
  return {
    result, redact,
    stage(name) { result.stage = name; },
    attach(context) {
      context.on('request', request => pending.set(request, { url: url(request.url()), method: request.method(), resource: request.resourceType() }));
      context.on('requestfinished', request => pending.delete(request));
      context.on('page', page => {
        page.on('pageerror', error => cap(result.javascriptErrors, redact(error.message)));
        page.on('console', message => { if (message.type() === 'error') cap(result.consoleErrors, redact(message.text())); });
      });
      context.on('requestfailed', request => { pending.delete(request); cap(result.failedRequests, {
        url: url(request.url()), method: request.method(), resource: request.resourceType(),
        error: redact(request.failure()?.errorText) }); });
      context.on('response', response => cap(result.responses, {
        url: url(response.url()), status: response.status(), resource: response.request().resourceType() }));
    },
    blocked(request) { cap(result.blockedRequests, { url: url(request.url()), method: request.method() }); },
    async navigation(response) {
      if (!response) return;
      result.navigation = { url: url(response.url()), status: response.status(),
        server: await response.serverAddr(), security: await response.securityDetails() };
    },
    async finish(page, error) {
      result.pendingRequests = [...pending.values()].slice(0, 200);
      if (page) result.finalUrl = url(page.url());
      if (error) result.failure = { type: error.name, message: redact(error.message) };
      if (page && !page.isClosed()) {
        try {
          const filename = 'chrome-diagnostic-redacted.png';
          await page.screenshot({ path: path.join(directory, filename),
            mask: [page.locator('input,textarea,[contenteditable],[data-sensitive]')] });
          result.screenshot = filename;
        } catch (captureError) { result.screenshotError = redact(captureError.message); }
      }
      fs.writeFileSync(path.join(directory, 'chrome-diagnostics.json'), JSON.stringify(result, null, 2));
    }
  };
}
module.exports = { diagnostics };
