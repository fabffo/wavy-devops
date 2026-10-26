'use strict';
// Deterministic synthetic receipts rendered offline by installed Windows Chrome.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require(process.env.WAVY_PLAYWRIGHT_CORE);
async function main() {
  const directory = process.argv[2];
  if (!directory || !fs.statSync(directory).isDirectory() || fs.readdirSync(directory).length) {
    throw new Error('NEW_EMPTY_DIRECTORY_REQUIRED');
  }
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const fixtures = [];
  try {
    const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
    await page.route('**/*', route => route.abort());
    for (const [format, ht, tva, ttc] of [['jpeg', '10.00', '2.00', '12.00'], ['png', '20.00', '4.00', '24.00'], ['pdf', '30.00', '6.00', '36.00']]) {
      const reference = 'QA-WAVY-' + format.toUpperCase();
      await page.setContent(`<html><body style="font:28px Arial;padding:40px;color:#111;background:white">
        <h1>DOCUMENT TEST SYNTHETIQUE</h1><p>Sans valeur comptable</p>
        <h2>FOURNISSEUR FICTIF WAVY</h2><p>Justificatif ${reference}</p>
        <p>Date : 25/10/2026</p><p>Prestation de test</p>
        <p>Montant HT : ${ht} EUR</p><p>TVA 20% : ${tva} EUR</p>
        <h2>Total TTC : ${ttc} EUR</h2></body></html>`);
      const file = 'receipt.' + (format === 'jpeg' ? 'jpg' : format);
      const target = path.join(directory, file);
      if (format === 'pdf') await page.pdf({ path: target, format: 'A4', printBackground: true });
      else await page.screenshot({ path: target, type: format, fullPage: true });
      const data = fs.readFileSync(target);
      fixtures.push({ file, mime: format === 'pdf' ? 'application/pdf' : 'image/' + format,
        bytes: data.length, sha256: crypto.createHash('sha256').update(data).digest('hex'),
        expected: { reference, fournisseur: 'FOURNISSEUR FICTIF WAVY', date: '2026-10-25', ht, tva, ttc, devise: 'EUR' } });
    }
    fs.writeFileSync(path.join(directory, 'expected.json'), JSON.stringify({ syntheticOnly: true, fixtures }, null, 2));
  } finally { await browser.close(); }
}
main().catch(() => { console.error('Offline fixture preparation failed.'); process.exitCode = 1; });
