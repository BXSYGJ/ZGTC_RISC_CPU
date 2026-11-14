import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createRequire } from 'node:module';
import { createServer } from 'node:net';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';

const require = createRequire(import.meta.url);
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const projectRoot = path.resolve(appRoot, '..', '..');
const options = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index];
  if (!['--url', '--out', '--python', '--playwright-module'].includes(key) || !process.argv[index + 1]) {
    throw new Error('Usage: node tests/browser_smoke.mjs [--url URL] [--out DIRECTORY] [--python EXECUTABLE] [--playwright-module PATH]');
  }
  options.set(key, process.argv[index + 1]);
}

const outputRoot = path.resolve(options.get('--out') || path.join(projectRoot, 'build', 'symphony', 'browser-smoke'));
const started = new Date();
const report = { passed: false, started_utc: started.toISOString(), command: [process.execPath, ...process.argv.slice(1)], cwd: process.cwd(), tests: [], browser_errors: [], request_failures: [], screenshots: [], input_sha256: {} };
let browser;
let server;
let page;
let serverOutput = '';
let serverError = '';

async function sha256(filename) {
  return createHash('sha256').update(await readFile(filename)).digest('hex');
}

async function bindInputs(directory = appRoot) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === '__pycache__' || entry.name === '.DS_Store') continue;
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) await bindInputs(filename);
    else report.input_sha256[path.relative(appRoot, filename).split(path.sep).join('/')] = await sha256(filename);
  }
}

function playwright() {
  const candidates = [options.get('--playwright-module'), process.env.PLAYWRIGHT_MODULE, 'playwright', path.join(homedir(), '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'node', 'node_modules', 'playwright')].filter(Boolean);
  const errors = [];
  for (const candidate of candidates) {
    try {
      const module = require(candidate);
      report.playwright_module = candidate;
      report.playwright_version = require(`${candidate}/package.json`).version;
      return module;
    } catch (error) { errors.push(`${candidate}: ${error.message}`); }
  }
  throw new Error(`Playwright was not found. Set PLAYWRIGHT_MODULE to an installed package.\n${errors.join('\n')}`);
}

async function availablePort() {
  const socket = createServer();
  socket.listen(0, '127.0.0.1');
  await once(socket, 'listening');
  const port = socket.address().port;
  await new Promise((resolve, reject) => socket.close(error => error ? reject(error) : resolve()));
  return port;
}

async function appUrl() {
  if (options.has('--url')) return options.get('--url');
  const port = await availablePort();
  const args = ['-X', 'utf8', path.join(appRoot, 'server.py'), '--port', String(port)];
  const executable = options.get('--python') || process.env.SYMPHONY_PYTHON || 'python';
  report.server_command = [executable, ...args];
  server = spawn(executable, args, { cwd: appRoot, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  server.stdout.on('data', data => { serverOutput += data.toString('utf8'); });
  server.stderr.on('data', data => { serverError += data.toString('utf8'); });
  let launchError;
  server.on('error', error => { launchError = error; });
  const url = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (launchError) throw launchError;
    if (server.exitCode !== null) throw new Error(`App server exited ${server.exitCode}: ${serverError}`);
    try { if ((await fetch(url)).ok) return url; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`App server did not become ready: ${serverError}`);
}

async function check(name, action) {
  const start = Date.now();
  try {
    const details = await action();
    report.tests.push({ name, passed: true, elapsed_ms: Date.now() - start, ...(details || {}) });
    console.log(`PASS ${name}`);
  } catch (error) {
    report.tests.push({ name, passed: false, elapsed_ms: Date.now() - start, error: error.stack || String(error) });
    throw error;
  }
}

function observe(target, label) {
  target.on('pageerror', error => report.browser_errors.push({ page: label, kind: 'pageerror', message: error.message }));
  target.on('console', message => { if (message.type() === 'error') report.browser_errors.push({ page: label, kind: 'console', message: message.text() }); });
  target.on('requestfailed', request => report.request_failures.push({ page: label, url: request.url(), error: request.failure()?.errorText }));
}

async function screenshot(target, name) {
  const filename = path.join(outputRoot, name);
  await target.screenshot({ path: filename });
  report.screenshots.push({ file: filename, sha256: await sha256(filename), viewport: target.viewportSize(), full_page: false });
  const fullFilename = path.join(outputRoot, name.replace(/\.png$/, '-full.png'));
  await target.screenshot({ path: fullFilename, fullPage: true });
  report.screenshots.push({ file: fullFilename, sha256: await sha256(fullFilename), viewport: target.viewportSize(), full_page: true });
}

async function noOverflow(target) {
  const dimensions = await target.evaluate(() => ({ width: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
  assert.ok(dimensions.document <= dimensions.width + 1, `Horizontal overflow: ${JSON.stringify(dimensions)}`);
  return dimensions;
}

async function exportFile(target, selector, filename) {
  if (!(await target.locator(selector).isVisible())) await target.locator('#nav-library').click();
  const downloading = target.waitForEvent('download');
  await target.locator(selector).click();
  const download = await downloading;
  assert.equal(await download.failure(), null);
  const destination = path.join(outputRoot, filename);
  await download.saveAs(destination);
  return { filename: destination, text: await readFile(destination, 'utf8'), suggested: download.suggestedFilename() };
}

async function selectOrFill(locator, value) {
  if (await locator.evaluate(element => element.tagName) === 'SELECT') {
    await locator.selectOption({ label: value });
  } else await locator.fill(value);
}

function wav(seconds = 2, rate = 48000) {
  const samples = rate * seconds;
  const bytes = Buffer.alloc(44 + samples * 2);
  bytes.write('RIFF'); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write('WAVEfmt ', 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(rate, 24); bytes.writeUInt32LE(rate * 2, 28); bytes.writeUInt16LE(2, 32);
  bytes.writeUInt16LE(16, 34); bytes.write('data', 36); bytes.writeUInt32LE(samples * 2, 40);
  for (let index = 0; index < samples; index++) bytes.writeInt16LE(Math.round(2000 * Math.sin(2 * Math.PI * 440 * index / rate)), 44 + index * 2);
  return bytes;
}

try {
  await mkdir(outputRoot, { recursive: true });
  await bindInputs();
  const url = await appUrl();
  report.url = url;
  const { chromium } = playwright();
  const launch = { headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) };
  browser = await chromium.launch(launch);
  report.browser_version = browser.version();
  report.browser_launch = launch;
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true, locale: 'zh-CN' });
  page = await context.newPage();
  observe(page, 'desktop');
  await page.goto(url, { waitUntil: 'networkidle' });
  await check('demo_source_and_guide', async () => {
    await page.locator('#source-label').filter({ hasText: '交互演示' }).waitFor();
    assert.ok(await page.locator('#guide-view').isVisible());
    assert.equal(await page.locator('#library-view').isVisible(), false);
    const text = await page.locator('body').innerText();
    assert.equal(text.includes('\uFFFD') || text.includes('\0'), false, 'Rendered Chinese contains invalid text');
    await screenshot(page, 'desktop-guide.png');
    return { source: await page.locator('#source-label').innerText(), dimensions: await noOverflow(page) };
  });

  await check('reference_backend', async () => {
    const response = await context.request.get(`${url}/api/reference`);
    assert.equal(response.status(), 200);
    const value = await response.json();
    assert.ok(value && typeof value === 'object' && Object.keys(value).length > 0);
    return { status: response.status(), keys: Object.keys(value) };
  });

  await check('demo_transport', async () => {
    const initialPosition = Number(await page.locator('#seek').inputValue());
    await page.locator('#play-toggle').click();
    await page.waitForTimeout(250);
    await page.locator('#play-toggle').click();
    const position = Number(await page.locator('#seek').inputValue());
    assert.ok(position > initialPosition && position < initialPosition + 5, `Demo transport did not advance: ${initialPosition} -> ${position}`);
    await page.locator('#seek').evaluate(element => { element.value = '32'; element.dispatchEvent(new Event('input', { bubbles: true })); });
    assert.ok((await page.locator('#dominant-name').innerText()).includes('铜管'));
    return { initial_position: initialPosition, playback_position: position, seek: 32, dominant: await page.locator('#dominant-name').innerText() };
  });

  await check('library_search_and_group_intersection', async () => {
    await page.locator('#nav-library').click();
    assert.ok(await page.locator('#library-view').isVisible());
    const all = await page.locator('#result-list .result-row').count();
    assert.ok(all > 0, 'Demo has no searchable segments');
    await page.locator('#search-query').fill('木管');
    await page.waitForTimeout(150);
    const termMatches = await page.locator('#result-list .result-row').count();
    assert.ok(termMatches > 0 && termMatches < all);
    await page.locator('#search-query').fill('短暂停顿');
    await page.waitForTimeout(150);
    assert.equal(await page.locator('#result-list .result-row').count(), 1, 'Ungrouped manual annotation is not searchable');
    await page.locator('#search-query').fill('不存在的片段-qa-20261115');
    await page.waitForTimeout(150);
    assert.equal(await page.locator('#result-list .result-row').count(), 0);
    await page.locator('#search-query').fill('');
    await page.locator('[data-filter-group="strings"]').click();
    await page.locator('[data-filter-group="woodwinds"]').click();
    await page.locator('#search-mode').selectOption('any');
    const any = await page.locator('#result-list .result-row').count();
    await page.locator('#search-mode').selectOption('all');
    const intersection = await page.locator('#result-list .result-row').count();
    const intervals = await page.locator('#result-list .result-row').evaluateAll(rows => rows.map(row => [Number(row.dataset.start), Number(row.dataset.end)]));
    assert.ok(any > 0 && any <= all);
    assert.ok(intersection > 0 && intersection < any, `Intersection ${intersection} should be a proper subset of union ${any}`);
    assert.deepEqual(intervals, [[16, 42], [57, 86]]);
    await screenshot(page, 'desktop-library.png');
    await page.locator('[data-filter-group="strings"]').click();
    await page.locator('[data-filter-group="woodwinds"]').click();
    return { all, term_matches: termMatches, ungrouped_annotation_matches: 1, any, intersection, intervals };
  });

  const marker = '浏览器标注往返验证';
  const importedMarker = '浏览器导入修改已生效';
  let exported;
  await check('annotation_save_persist_export', async () => {
    await page.locator('#library-add-annotation').click();
    await page.locator('#annotation-dialog').waitFor({ state: 'visible' });
    await selectOrFill(page.locator('#annotation-label'), marker);
    await page.locator('#annotation-start').fill('12');
    await page.locator('#annotation-end').fill('10');
    await page.locator('#annotation-notes').fill('中文注释：弦乐进入，木管交接。');
    await page.locator('#annotation-groups button').filter({ hasText: '弦乐' }).click();
    await page.locator('#save-annotation').click();
    assert.ok(await page.locator('#annotation-dialog').isVisible(), 'Reversed annotation bounds were accepted');
    assert.ok((await page.locator('#annotation-error').innerText()).trim().length > 0);
    await page.locator('#annotation-end').fill('16');
    await page.locator('#save-annotation').click();
    await page.locator('#annotation-dialog').waitFor({ state: 'hidden' });
    exported = await exportFile(page, '#export-json', 'annotation-export.json');
    JSON.parse(exported.text);
    assert.ok(exported.text.includes(marker));
    assert.ok(exported.text.includes('中文注释'));
    const csv = await exportFile(page, '#export-csv', 'annotation-export.csv');
    assert.ok(csv.text.includes(marker));
    assert.equal(csv.text.includes('\uFFFD'), false);
    await page.reload({ waitUntil: 'networkidle' });
    const persisted = await exportFile(page, '#export-json', 'annotation-persisted.json');
    assert.ok(persisted.text.includes(marker), 'Annotation was lost after reload');
    return { json: exported.filename, csv: csv.filename, persisted: true };
  });

  await check('json_import_changes_data', async () => {
    const replacement = exported.text.replaceAll(marker, importedMarker);
    assert.notEqual(replacement, exported.text);
    await page.locator('#file-session').setInputFiles({ name: 'roundtrip-session.json', mimeType: 'application/json', buffer: Buffer.from(replacement, 'utf8') });
    await page.waitForTimeout(150);
    const imported = await exportFile(page, '#export-json', 'annotation-imported.json');
    assert.ok(imported.text.includes(importedMarker), 'Import did not replace the annotation');
    assert.equal(imported.text.includes(marker), false);
    return { file: imported.filename, modified_annotation_imported: true };
  });

  await check('invalid_json_preserves_current_session', async () => {
    const before = await exportFile(page, '#export-json', 'before-invalid-json.json');
    await page.locator('#file-session').setInputFiles({ name: 'invalid-session.json', mimeType: 'application/json', buffer: Buffer.from('{"schema_version":999,"frames":[]}', 'utf8') });
    await page.waitForTimeout(150);
    const after = await exportFile(page, '#export-json', 'after-invalid-json.json');
    assert.equal(after.text, before.text, 'Rejected JSON changed the active session');
    return { active_session_preserved: true };
  });

  await check('local_audio_validation_and_metadata', async () => {
    await page.locator('#file-audio').setInputFiles({ name: 'invalid.txt', mimeType: 'text/plain', buffer: Buffer.from('not an audio file', 'utf8') });
    await page.waitForTimeout(150);
    const before = await exportFile(page, '#export-json', 'after-invalid-audio.json');
    assert.ok(before.text.includes(importedMarker), 'Invalid audio unexpectedly replaced annotations');
    await page.locator('#file-audio').setInputFiles({ name: 'browser-fixture.wav', mimeType: 'audio/wav', buffer: wav() });
    await page.waitForFunction(() => Number.isFinite(document.querySelector('#audio').duration) && document.querySelector('#audio').duration > 0);
    const duration = await page.locator('#audio').evaluate(audio => audio.duration);
    assert.ok(Math.abs(duration - 2) < 0.01);
    const localAudio = JSON.parse((await exportFile(page, '#export-json', 'local-audio-session.json')).text);
    assert.equal(localAudio.source.kind, 'manual');
    assert.deepEqual(localAudio.frames, []);
    assert.equal(localAudio.track.duration, duration);
    return { valid_file: 'browser-fixture.wav', mime: 'audio/wav', samples: 96000, sample_rate: 48000, duration, source_kind: localAudio.source.kind, generated_inference_frames: localAudio.frames.length, invalid_file_rejected_without_data_loss: true };
  });

  let referenceExport;
  await check('reference_picker_uses_actual_model_values', async () => {
    const reference = await (await context.request.get(`${url}/api/reference`)).json();
    await page.locator('#open-sources').click();
    await page.locator('#reference-source').click();
    await page.locator('#reference-picker').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#reference-select option').count(), reference.samples.length);
    await page.locator('#reference-select').selectOption('2');
    await page.locator('#load-reference').click();
    await page.locator('#sources-dialog').waitFor({ state: 'hidden' });
    assert.equal(await page.locator('#source-label').innerText(), '模型参考');
    referenceExport = await exportFile(page, '#export-json', 'reference-session.json');
    const session = JSON.parse(referenceExport.text);
    assert.equal(session.source.kind, 'inference');
    assert.equal(session.frames.length, 1);
    assert.equal(session.track.duration, reference.samples[2].duration_seconds);
    assert.deepEqual(session.frames[0].activity, reference.samples[2].activities);
    assert.deepEqual(session.frames[0].dominance, reference.samples[2].dominance);
    return { sample_id: reference.samples[2].id, samples: reference.samples.length, activity: session.frames[0].activity, dominance: session.frames[0].dominance, independent_window: true };
  });

  await check('uart_eight_class_observation_keeps_group_session', async () => {
    const log = 'RTOS BOOT hz=125000000 tick=1000\nRTOS HEARTBEAT tick=200 results=0\nRTOS NPU top1=0 last_class=7 last_p=0 c=31152090 seq=1 tick=250\nRTOS NPU TIMEOUT seq=2 tick=400\n';
    await page.locator('#file-log').setInputFiles({ name: 'rtos-observation.log', mimeType: 'text/plain', buffer: Buffer.from(log, 'utf8') });
    await page.locator('#sources-dialog').waitFor({ state: 'visible' });
    const summary = await page.locator('#telemetry-summary').innerText();
    assert.ok(summary.includes('八类推理 1 次') && summary.includes('心跳 1 次') && summary.includes('超时 1 次'));
    assert.ok(summary.includes('最近分类：单簧管'));
    assert.ok(summary.includes('末概率通道：7，值 0%'));
    assert.equal(await page.locator('#source-label').innerText(), '模型参考');
    await screenshot(page, 'desktop-uart-observation.png');
    await page.locator('#sources-dialog [data-close-dialog]').click();
    const after = await exportFile(page, '#export-json', 'after-uart-session.json');
    assert.equal(after.text, referenceExport.text, 'UART log changed five-group scores');
    return { summary, group_session_unchanged: true };
  });

  await check('mobile_layout_and_tabs', async () => {
    const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 1, hasTouch: true, locale: 'zh-CN' });
    const mobile = await mobileContext.newPage();
    observe(mobile, 'mobile');
    await mobile.goto(url, { waitUntil: 'networkidle' });
    assert.ok(await mobile.locator('#guide-view').isVisible());
    const guide = await noOverflow(mobile);
    await screenshot(mobile, 'mobile-guide.png');
    await mobile.locator('#source-label').click();
    await mobile.locator('#sources-dialog').waitFor({ state: 'visible' });
    assert.ok(await mobile.locator('#reference-source').isVisible());
    assert.ok(await mobile.locator('#import-log').isVisible());
    await screenshot(mobile, 'mobile-sources.png');
    await mobile.locator('#sources-dialog [data-close-dialog]').click();
    await mobile.locator('#nav-library').click();
    assert.ok(await mobile.locator('#library-view').isVisible());
    const library = await noOverflow(mobile);
    await screenshot(mobile, 'mobile-library.png');
    await mobileContext.close();
    return { guide, library, source_picker_accessible: true, reference_and_uart_controls_accessible: true };
  });

  await check('browser_clean', async () => {
    assert.deepEqual(report.browser_errors, []);
    assert.deepEqual(report.request_failures, []);
    return { page_errors: 0, console_errors: 0, request_failures: 0 };
  });
  report.passed = true;
} catch (error) {
  report.error = error.stack || String(error);
  console.error(report.error);
  if (page && !page.isClosed()) {
    try { await screenshot(page, 'failure.png'); } catch {}
  }
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(error => { report.browser_close_error = error.message; });
  if (server) {
    server.kill();
    if (server.exitCode === null) await Promise.race([once(server, 'exit'), new Promise(resolve => setTimeout(resolve, 3000))]);
    report.server_exit = { code: server.exitCode, signal: server.signalCode };
  }
  report.finished_utc = new Date().toISOString();
  report.elapsed_ms = Date.now() - started.getTime();
  report.changed_inputs = [];
  for (const [relative, original] of Object.entries(report.input_sha256)) {
    try {
      if (await sha256(path.join(appRoot, relative)) !== original) report.changed_inputs.push(relative);
    } catch { report.changed_inputs.push(relative); }
  }
  report.inputs_unchanged = report.changed_inputs.length === 0;
  if (!report.inputs_unchanged) { report.passed = false; process.exitCode = 1; }
  report.exit_status = report.passed ? 0 : 1;
  await mkdir(outputRoot, { recursive: true });
  await writeFile(path.join(outputRoot, 'server.stdout.log'), serverOutput, 'utf8');
  await writeFile(path.join(outputRoot, 'server.stderr.log'), serverError, 'utf8');
  await writeFile(path.join(outputRoot, 'BROWSER_REPORT.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  const reopened = JSON.parse(await readFile(path.join(outputRoot, 'BROWSER_REPORT.json'), 'utf8'));
  assert.equal(reopened.passed, report.passed);
  console.log(`BROWSER_SMOKE_${report.passed ? 'PASS' : 'FAIL'} tests=${report.tests.length} report=${path.join(outputRoot, 'BROWSER_REPORT.json')}`);
}
