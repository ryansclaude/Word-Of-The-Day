/**
 * Headless render script for Motion Canvas.
 * Starts the Vite dev server, opens the editor with ?render param via Puppeteer,
 * waits for rendering to complete, then outputs frames to ./output/.
 */
import {createServer} from 'vite';
import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';

const TIMEOUT_MS = 120_000; // 2 minutes max

async function main() {
  console.log('[RENDER] Starting Vite dev server...');
  const server = await createServer({
    configFile: path.resolve('vite.config.ts'),
    server: {port: 9000},
  });
  await server.listen();
  const address = server.resolvedUrls.local[0];
  console.log(`[RENDER] Server running at ${address}`);

  console.log('[RENDER] Launching headless browser...');
  const browser = await puppeteer.launch({headless: true});
  const page = await browser.newPage();

  // Navigate to editor with ?render to auto-start rendering
  const renderUrl = `${address}?render`;
  console.log(`[RENDER] Navigating to ${renderUrl}`);
  await page.goto(renderUrl, {waitUntil: 'networkidle0', timeout: 30000});

  // Wait for rendering to complete by polling for the output directory
  const outputDir = path.resolve('output');
  console.log('[RENDER] Waiting for render to complete...');

  const start = Date.now();
  let frameCount = 0;
  while (Date.now() - start < TIMEOUT_MS) {
    await new Promise(r => setTimeout(r, 2000));

    // Check if output directory has frames
    if (fs.existsSync(outputDir)) {
      const subdirs = fs.readdirSync(outputDir);
      for (const sub of subdirs) {
        const subPath = path.join(outputDir, sub);
        if (fs.statSync(subPath).isDirectory()) {
          const files = fs.readdirSync(subPath).filter(f => f.endsWith('.png'));
          if (files.length > frameCount) {
            frameCount = files.length;
            console.log(`[RENDER] ${frameCount} frames rendered...`);
          }
          // If we have frames and count hasn't changed, rendering might be done
          if (files.length > 0 && files.length === frameCount) {
            // Wait one more cycle to confirm
            await new Promise(r => setTimeout(r, 3000));
            const recheck = fs.readdirSync(subPath).filter(f => f.endsWith('.png'));
            if (recheck.length === frameCount) {
              console.log(`[RENDER] Rendering complete: ${frameCount} frames in ${subPath}`);
              await browser.close();
              await server.close();
              process.exit(0);
            }
          }
        }
      }
    }

    // Also check if puppeteer page shows render complete
    try {
      const status = await page.evaluate(() => {
        const el = document.querySelector('[class*="render"]');
        return el ? el.textContent : '';
      });
      if (status && status.toLowerCase().includes('done')) {
        console.log('[RENDER] Browser reports render done');
        break;
      }
    } catch {
      // Page might have navigated, ignore
    }
  }

  await browser.close();
  await server.close();

  if (frameCount > 0) {
    console.log(`[RENDER] Done. Total frames: ${frameCount}`);
  } else {
    console.error('[RENDER] ERROR: No frames were rendered within timeout.');
    process.exit(1);
  }
}

main().catch(err => {
  console.error('[RENDER] Fatal error:', err);
  process.exit(1);
});
