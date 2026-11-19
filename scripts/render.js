/* 逐帧渲染：Chrome headless 截图 → PNG 序列
 *
 * 用法：
 *   node render.js <engine.html> <timeline.json> <framesDir> [选项]
 *
 * 选项：
 *   --fps 30            帧率（默认 30）
 *   --scale 1           画面缩放（草稿用 0.5，出 960×540）
 *   --style rough       切 Rough.js 手绘档
 *   --preview 1.5,10    只出这几个时间点的预览图（不写帧序列）
 *   --from 0 --to 30    只渲某一段（秒）
 *   --force             已存在的帧也重渲
 *   --jpeg 95           截图存 JPEG（默认 PNG）。实测 q95 PSNR 49dB / SSIM 0.995，
 *                       视觉无损，但截图快 1.6–2 倍，文件小 2/3
 *
 * 为什么要 headless:'shell' + --no-sandbox：
 *   macOS 上完整 headless 会在 setViewport 时抛 TargetCloseError，
 *   shell 模式 + 独立 user-data-dir 才稳定。
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const [enginePath, tlPath, framesDir] = args;
function arg(flag, def) {
  const i = args.indexOf(flag);
  return i > -1 ? args[i + 1] : def;
}
const has = f => args.includes(f);

const FPS = parseFloat(arg('--fps', '30'));
const SCALE = parseFloat(arg('--scale', '1'));
const CW = parseInt(arg('--w', '1920'), 10);
const CH = parseInt(arg('--h', '1080'), 10);
const ROUGH = has('--style') && arg('--style') === 'rough';
const PREVIEW = arg('--preview', null);
const FORCE = has('--force');
// 每集自带场景脚本（epXX/scenery.js）：在引擎就绪后、setTimeline 之前注入，
// 里面用 SCENE_KIT.scene(name, fn) 现场画这一集话题需要的场景。
const SCENERY = arg('--scenery', null);
// PNG 的编码开销在逐帧截图里占大头；矢量卡通转 JPEG 视觉上无损，速度快一倍
const JPEGQ = arg('--jpeg', null);
const EXT = JPEGQ ? 'jpg' : 'png';
const SHOT_OPTS = JPEGQ
  ? { type: 'jpeg', quality: Math.min(100, Math.max(1, parseInt(JPEGQ, 10) || 95)) }
  : { type: 'png' };

const chrome = process.env.CHROME_PATH ||
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

// 每个进程独立 profile；带时间戳，避免 PID 重用撞上上次残留的 SingletonLock
const PROFILE = `/tmp/kids-chrome-${process.pid}-${Date.now()}`;

// headless:'shell' 收尾时 browser.close() 偶尔永不返回，node 就不退出，
// 父进程（build.py 并行分片）的 wait() 会一直挂到超时。这里等不到就强退。
async function shutdown(browser) {
  await Promise.race([
    browser.close().catch(() => {}),
    new Promise(r => setTimeout(r, 4000)),
  ]);
  /* close() 不返回时，Chrome 的 Helper 进程会一直挂着（用户实测后台堆了十几个）。
     这里按 user-data-dir 精确清掉本进程拉起来的那一组，别误杀用户自己的浏览器。 */
  try {
    const proc = browser.process && browser.process();
    if (proc && !proc.killed) { try { proc.kill('SIGKILL'); } catch (e) { /* */ } }
  } catch (e) { /* */ }
  try {
    require('child_process').execSync(
      `pkill -9 -f "user-data-dir=${PROFILE}" || true`, { stdio: 'ignore' });
  } catch (e) { /* */ }
  try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) { /* */ }
  process.exit(0);
}

let BROWSER = null;
const bail = async (code) => {
  if (BROWSER) { try { await shutdown(BROWSER); } catch (e) { /* */ } }
  process.exit(code);
};
process.on('SIGINT', () => { bail(130); });
process.on('SIGTERM', () => { bail(143); });
process.on('uncaughtException', (e) => {
  console.error('渲染异常：', String(e).slice(0, 200));
  bail(1);
});

(async () => {
  const tl = JSON.parse(fs.readFileSync(tlPath, 'utf8'));
  const total = tl.segments.reduce((a, s) => a + s.dur, 0);

  /* 光栅化占单帧 99%（截图 49ms，JS+DOM 只有 0.8ms），所以唯一有效的单帧优化是让 GPU 参与。
     实测 macOS：留着 GPU 41.7ms / 关掉 49.1ms，快 15%，内存不涨。
     在无 GPU 的容器里反而可能更慢或起不来，用 CHROME_NO_GPU=1 关回去。 */
  const gpuArgs = process.env.CHROME_NO_GPU === '1' ? ['--disable-gpu'] : [];
  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: 'shell',
    args: ['--no-sandbox', '--hide-scrollbars',
           `--user-data-dir=${PROFILE}`, '--disable-dev-shm-usage',
           '--force-color-profile=srgb', '--font-render-hinting=none', '--disable-lcd-text',
           ...gpuArgs],
  });
  BROWSER = browser;
  const page = await browser.newPage();
  await page.setViewport({ width: CW, height: CH, deviceScaleFactor: SCALE });

  const q = ROUGH ? '?style=rough' : '';
  await page.goto('file://' + path.resolve(enginePath) + q, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  // 先定语言：每集 scenery.js 里的标签用 K.L(中文, 西语) 选词
  await page.evaluate(l => { window.__LANG = l; },
                      (tl.segments && tl.segments[0] && tl.segments[0].lang) || 'es');
  // 非 16:9 画布（如 4:3 封面）必须在注册场景前改好，场景挂载时才拿得到正确的 W/H
  if (CW !== 1920 || CH !== 1080) {
    await page.evaluate((w, h) => window.setCanvas(w, h), CW, CH);
  }
  // 每集专属场景：必须在 setTimeline 之前注册，否则挂载时找不到 BG[name]
  if (SCENERY) {
    const abs = path.resolve(SCENERY);
    if (!fs.existsSync(abs)) throw new Error('找不到场景脚本：' + abs);
    await page.addScriptTag({ content: fs.readFileSync(abs, 'utf8') });
  }
  await page.evaluate(t => window.setTimeline(t), tl);

  const shot = async (t, file) => {
    await page.evaluate(tt => window.renderFrame(tt), t);
    await page.screenshot({ path: file, ...SHOT_OPTS });
  };

  if (PREVIEW) {
    fs.mkdirSync(framesDir, { recursive: true });
    for (const t of PREVIEW.split(',').map(Number)) {
      const f = path.join(framesDir, `preview_${t.toFixed(2)}.${EXT}`);
      await shot(t, f);
      console.log('预览', f);
    }
    await shutdown(browser);
    return;
  }

  fs.mkdirSync(framesDir, { recursive: true });
  const t0 = parseFloat(arg('--from', '0'));
  const t1 = parseFloat(arg('--to', String(total)));
  const first = Math.round(t0 * FPS), last = Math.round(Math.min(t1, total) * FPS);
  const started = Date.now();
  let done = 0;

  for (let i = first; i < last; i++) {
    const f = path.join(framesDir, `f${String(i + 1).padStart(5, '0')}.${EXT}`);
    if (!FORCE && fs.existsSync(f) && fs.statSync(f).size > 1000) { done++; continue; }
    await shot(i / FPS, f);
    done++;
    if (done % 100 === 0) {
      const el = (Date.now() - started) / 1000;
      const eta = el / done * (last - first - done);
      console.log(`  ${done}/${last - first}  已用 ${el.toFixed(0)}s  预计还需 ${eta.toFixed(0)}s`);
    }
  }
  console.log(`帧渲染完成：${done} 帧 → ${framesDir}（${((Date.now() - started) / 1000).toFixed(0)}s）`);
  await shutdown(browser);
})();
