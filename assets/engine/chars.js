/* ==============================================================
   角色模块 · 考考 & 小熹
   全部为参数化 SVG 图元，零图片素材。

   配色原则（2026/11 改版）：
     小熹是橙狐（色相约 15°），考考就完全避开橙红区，主色改湖蓝（205°），
     副色只用一小块芥末黄（45°，不参与"谁是谁"的识别）。
     两人放在任何背景上都是「冷 / 暖」对立，剪影一眼分得开。

   动画句柄（挂在返回的 <g> 上，拿不到也不影响静态渲染）：
     g.__mouth  嘴 <g> —— 说话时逐帧改 transform 做开合
     g.__eyes   眼 <g> —— 眨眼
     g.__tail   尾 <g> —— 摇摆 / 亮起
   ============================================================== */

const NSV = "http://www.w3.org/2000/svg";

/* ---------------- 调色板 ---------------- */
const K = {
  ink: "#33261C", sw: 9,
  skin: "#F8C9A0", skinSh: "#E7A97B", blush: "#F2795C",
  hair: "#332319", hairHi: "#5A3E2A",
  // 主色：湖蓝。回避橙红，和狐狸形成冷/暖对立
  hoodie: "#3E7CB8", hoodieDk: "#2A5A8C", hoodieLt: "#67A6DC",
  accent: "#F2B33D",          // 芥末黄，只用在徽记字/帽里/抽绳扣，面积 < 5%
  cream: "#FFF6E2", pants: "#D9CBAF", sock: "#F3E6CE", shoe: "#4A3B2C", mouth: "#7A2B22",
};

/* ---------------------------------------------------------------
   角色明暗：把平涂色块换成「左上亮 → 右下暗」的同色系渐变。
   SVG 没有材质系统，这一层渐变就是体积感的全部来源；
   纯色块在深色背景上会像剪纸，加了渐变才像有厚度的实体。

   用 objectBoundingBox 坐标（默认），所以每个元素各自从自己的
   左上过渡到右下，方向统一、不需要知道角色在哪。
   --------------------------------------------------------------- */
const CG = {
  kaoSkin:   ["#FDD6B2", "#EBA97A"],
  kaoHair:   ["#4E3627", "#261A12"],
  kaoHoodie: ["#5E9CDA", "#32649B"],
  kaoPants:  ["#E6DAC0", "#C9BA9C"],
  kaoShoe:   ["#5E4C3A", "#37291D"],
  xiFur:     ["#FF7C55", "#D64E27"],
  xiCream:   ["#FFF9EE", "#E8D9BE"],
  xiGold:    ["#FFDD74", "#E5A318"],
};

const GRAD_IDS = {};

function ensureGrads() {
  if (typeof document === "undefined" || document.getElementById("cgKaoSkin")) return;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.querySelector("svg");
  if (!svg) return;
  let defs = svg.querySelector("defs");
  if (!defs) {
    defs = document.createElementNS(NS, "defs");
    svg.insertBefore(defs, svg.firstChild);
  }
  Object.keys(CG).forEach(name => {
    const id = "cg" + name.charAt(0).toUpperCase() + name.slice(1);
    const [a, b] = CG[name];
    const gd = document.createElementNS(NS, "linearGradient");
    gd.setAttribute("id", id);
    gd.setAttribute("x1", "0.14");
    gd.setAttribute("y1", "0");
    gd.setAttribute("x2", "0.62");
    gd.setAttribute("y2", "1");
    [[0, a], [1, b]].forEach(([off, col]) => {
      const st = document.createElementNS(NS, "stop");
      st.setAttribute("offset", off);
      st.setAttribute("stop-color", col);
      gd.appendChild(st);
    });
    defs.appendChild(gd);
    GRAD_IDS[name] = `url(#${id})`;
  });
}

const G = {
  get skin()   { return GRAD_IDS.kaoSkin   || K.skin; },
  get hair()   { return GRAD_IDS.kaoHair   || K.hair; },
  get hoodie() { return GRAD_IDS.kaoHoodie || K.hoodie; },
  get pants()  { return GRAD_IDS.kaoPants  || K.pants; },
  get shoe()   { return GRAD_IDS.kaoShoe   || K.shoe; },
  get fur()    { return GRAD_IDS.xiFur     || X.fur; },
  get cream()  { return GRAD_IDS.xiCream   || X.cream; },
  get gold()   { return GRAD_IDS.xiGold    || X.gold; },
};

const X = {
  ink: "#3A2A22", sw: 8,
  fur: "#F2603C", furDk: "#C9421F", furLt: "#FF8055",
  cream: "#FFF3E0", ear: "#FFB09A",
  gold: "#FFC93C", goldLt: "#FFF0B0",
  nose: "#2A1710", brass: "#C9963F", brassDk: "#8E6526",
};

/* 一撮毛：从 (cx,cy) 向 -h 方向长出的叶形，lean 让它歪一点，才不像锯齿 */
function tuft(EL, g, cx, cy, w, h, lean, fill, ink, sw) {
  const d = `M ${cx - w} ${cy} C ${cx - w * 0.5} ${cy - h * 0.62} ${cx - w * 0.05 + lean} ${cy - h * 1.02} ${cx + w * 0.42 + lean} ${cy - h * 0.94} ` +
            `C ${cx + w * 0.15 + lean * 0.6} ${cy - h * 0.34} ${cx + w * 0.8} ${cy - h * 0.12} ${cx + w} ${cy} Z`;
  EL("path", { d, fill, stroke: ink, "stroke-width": sw, "stroke-linejoin": "round" }, g);
}

/* ---------------------------------------------------------------
   考考 · 6 岁男孩（按照片转卡通）
   局部原点在脚底中心，全高 560，发尖约 -590
   expr: idle 常态 | silly 大笑 | wow 惊讶 | talk 说话（嘴可动）
   --------------------------------------------------------------- */
function buildKao(EL, expr, parent) {
  expr = expr || "idle";
  ensureGrads();
  // 先挂到父节点再画：Rough.js 要靠 getBBox 取尺寸，离线的子树量不出大小
  const g = EL("g", {}, parent);
  const ink = K.ink, sw = K.sw;

  EL("ellipse", { cx: 0, cy: 4, rx: 126, ry: 19, fill: ink, opacity: 0.10 }, g);

  // 腿 / 袜 / 鞋
  EL("rect", { x: -72, y: -152, width: 56, height: 96, rx: 24, fill: G.pants, stroke: ink, "stroke-width": sw }, g);
  EL("rect", { x: 16, y: -152, width: 56, height: 96, rx: 24, fill: G.pants, stroke: ink, "stroke-width": sw }, g);
  EL("rect", { x: -70, y: -66, width: 52, height: 28, rx: 11, fill: K.sock, stroke: ink, "stroke-width": 6 }, g);
  EL("rect", { x: 18, y: -66, width: 52, height: 28, rx: 11, fill: K.sock, stroke: ink, "stroke-width": 6 }, g);
  [-84, 16].forEach(x => {
    EL("path", { d: `M ${x} -26 q 0 -16 18 -16 h 44 q 16 0 16 16 v 12 q 0 16 -16 16 h -46 q -16 0 -16 -16 z`,
                 fill: G.shoe, stroke: ink, "stroke-width": sw, "stroke-linejoin": "round" }, g);
    EL("path", { d: `M ${x + 12} -12 h 48`, fill: "none", stroke: "#6B5A48", "stroke-width": 5 }, g);
  });

  // 帽子（头后面）：暗蓝，和衣身同色系不同明度
  EL("path", { d: "M -96 -326 q -4 -66 96 -66 q 100 0 96 66 q -30 -26 -96 -26 q -66 0 -96 26 z",
               fill: K.hoodieDk, stroke: ink, "stroke-width": sw, "stroke-linejoin": "round" }, g);
  // 领口：填住下巴和衣身之间的缝
  EL("rect", { x: -86, y: -358, width: 172, height: 48, rx: 20, fill: G.hoodie, stroke: ink, "stroke-width": sw }, g);
  // 脖子
  EL("rect", { x: -28, y: -340, width: 56, height: 44, rx: 14, fill: K.skinSh, stroke: ink, "stroke-width": sw }, g);

  // 手臂
  const lift = expr === "wow" ? 26 : 0;
  [-1, 1].forEach(s => {
    const sx = 96 * s, sy = -292, ex = 166 * s, ey = -176 - lift;
    const d = `M ${sx} ${sy} q ${26 * s} 54 ${ex - sx} ${ey - sy}`;
    EL("path", { d, fill: "none", stroke: ink, "stroke-width": 54, "stroke-linecap": "round" }, g);
    EL("path", { d, fill: "none", stroke: G.hoodie, "stroke-width": 40, "stroke-linecap": "round" }, g);
    EL("circle", { cx: ex - 2 * s, cy: ey + 4, r: 24, fill: G.skin, stroke: ink, "stroke-width": sw }, g);
    // 拇指：一个偏侧的小椭圆，手就从"圆球"变成"能看出来是手"
    EL("ellipse", { cx: ex - 16 * s, cy: ey - 4, rx: 9.5, ry: 14,
                    transform: `rotate(${-24 * s} ${ex - 16 * s} ${ey - 4})`,
                    fill: G.skin, stroke: ink, "stroke-width": 5 }, g);
  });

  // 躯干 + 口袋 + 问号徽记 + 抽绳
  EL("path", { d: "M -100 -150 q -6 -122 4 -160 q 6 -26 96 -26 q 90 0 96 26 q 10 38 4 160 q -60 18 -100 18 q -40 0 -100 -18 z",
               fill: G.hoodie, stroke: ink, "stroke-width": sw, "stroke-linejoin": "round" }, g);
  // 衣褶：腋下两道放射褶 + 腹部一道横褶。两三笔就够，多了显脏
  [-1, 1].forEach(s => {
    EL("path", { d: `M ${78 * s} -286 q ${-20 * s} 24 ${-15 * s} 58`, fill: "none",
                 stroke: K.hoodieDk, "stroke-width": 5, "stroke-linecap": "round", opacity: 0.45 }, g);
  });
  EL("path", { d: "M -52 -176 q 52 11 104 0", fill: "none",
               stroke: K.hoodieDk, "stroke-width": 4.5, "stroke-linecap": "round", opacity: 0.3 }, g);
  EL("path", { d: "M -60 -192 q 60 14 120 0 q 2 42 -16 58 q -44 12 -88 0 q -18 -16 -16 -58 z",
               fill: K.hoodieLt, stroke: ink, "stroke-width": 6, "stroke-linejoin": "round" }, g);
  // 徽记：奶油底 + 芥末黄问号（唯一保留的一点暖色，面积很小）
  EL("circle", { cx: 82, cy: -332, r: 17, fill: K.cream, stroke: ink, "stroke-width": 6 }, g);
  EL("text", { x: 82, y: -324, "font-size": 24, fill: K.accent, "font-weight": 800, "text-anchor": "middle" }, g)
    .textContent = "?";
  [-16, 16].forEach(x => {
    EL("path", { d: `M ${x} -304 q ${x > 0 ? 5 : -5} 26 ${x > 0 ? 3 : -3} 46`, fill: "none",
                 stroke: K.cream, "stroke-width": 6, "stroke-linecap": "round" }, g);
    EL("circle", { cx: x + (x > 0 ? 3 : -3), cy: -256, r: 6, fill: K.accent, stroke: ink, "stroke-width": 3 }, g);
  });

  // 招风耳：画在头之前，让头压住内侧 18°
  [-1, 1].forEach(s => {
    const ex = 104 * s;
    const ear = EL("g", { transform: `rotate(${18 * s} ${ex} -442)` }, g);
    EL("ellipse", { cx: ex, cy: -442, rx: 20, ry: 27, fill: G.skin, stroke: ink, "stroke-width": sw }, ear);
    EL("path", { d: `M ${ex - 4 * s} -452 q ${9 * s} 10 0 19`, fill: "none",
                 stroke: K.skinSh, "stroke-width": 4, "stroke-linecap": "round", opacity: 0.85 }, ear);
  });

  // 头（偏瘦）
  EL("ellipse", { cx: 0, cy: -448, rx: 92, ry: 111, fill: G.skin, stroke: ink, "stroke-width": sw }, g);

  // 头发：底帽 + 顶部朝上 6 撮 + 额前朝下 7 尖 + 鬓角
  EL("path", { d: "M -101 -452 C -110 -512 -88 -548 -52 -560 C -22 -570 26 -570 56 -558 " +
                  "C 90 -546 108 -512 100 -452 C 92 -486 66 -500 34 -505 " +
                  "C 12 -508 -12 -508 -34 -505 C -66 -500 -92 -486 -101 -452 Z",
               fill: G.hair, stroke: ink, "stroke-width": sw, "stroke-linejoin": "round" }, g);
  [[-76, 14, 26, -5], [-46, 16, 32, 4], [-14, 15, 27, -6], [18, 17, 34, 5], [48, 15, 26, -3], [74, 12, 20, 4]]
    .forEach(([x, w, h, ln]) => {
      const yc = -505 - Math.sqrt(Math.max(0, 1 - (x / 100) ** 2)) * 52;
      tuft(EL, g, x, yc, w, h, ln, G.hair, ink, 6);
    });
  [[-86, 11, 8, -2], [-58, 16, 16, 4], [-28, 14, 21, -4], [1, 17, 12, 3], [30, 15, 20, -3], [59, 16, 14, 4], [86, 11, 9, -1]]
    .forEach(([x, w, len, ln]) => {
      const y0 = -512 + 0.0016 * x * x;
      const d = `M ${x - w} ${y0} C ${x - w * 0.3 + ln} ${y0 + len * 0.55} ${x + w * 0.1 + ln} ${y0 + len} ${x + w * 0.45 + ln} ${y0 + len * 0.9} ` +
                `C ${x + w * 0.2} ${y0 + len * 0.4} ${x + w * 0.7} ${y0 + len * 0.1} ${x + w} ${y0} Z`;
      EL("path", { d, fill: G.hair, stroke: ink, "stroke-width": 5, "stroke-linejoin": "round" }, g);
    });
  [-1, 1].forEach(s => {
    EL("path", { d: `M ${84 * s} -492 q ${6 * s} 22 ${2 * s} 38 q ${-10 * s} -14 ${-12 * s} -38 z`,
                 fill: G.hair, stroke: ink, "stroke-width": 4, "stroke-linejoin": "round" }, g);
  });
  // 发丝光泽：比发色亮一档的细弧，顺着发流走。纯色块没有"头发"的质感，加了才有
  [[-48, -546, -60, -508], [-10, -554, -14, -512], [30, -548, 42, -510]].forEach(([x1, y1, x2, y2]) => {
    EL("path", { d: `M ${x1} ${y1} Q ${(x1 + x2) / 2 + 7} ${(y1 + y2) / 2} ${x2} ${y2}`,
                 fill: "none", stroke: "#6E4E34", "stroke-width": 3.5,
                 "stroke-linecap": "round", opacity: 0.5 }, g);
  });

  // 眉毛：细、近直、外端略垂
  const browY = expr === "wow" ? -486 : expr === "silly" ? -474 : -476;
  [-1, 1].forEach(s => {
    EL("path", { d: `M ${12 * s} ${browY + 3} Q ${28 * s} ${browY - 5} ${45 * s} ${browY + 4}`,
                 fill: "none", stroke: K.hair, "stroke-width": 7.5, "stroke-linecap": "round" }, g);
  });

  // 眼睛：眨眼靠眼组整体纵向压缩
  const eyes = EL("g", { "data-crisp": "1" }, g);
  if (expr === "silly") {
    [-1, 1].forEach(s => {
      EL("path", { d: `M ${20 * s} -452 Q ${40 * s} -472 ${60 * s} -452`, fill: "none",
                   stroke: ink, "stroke-width": 9, "stroke-linecap": "round" }, eyes);
    });
  } else {
    const big = expr === "wow";
    [-1, 1].forEach(s => {
      const cx = 38 * s, cy = -450;
      EL("ellipse", { cx, cy, rx: big ? 23 : 21, ry: big ? 16 : 12, fill: "#FFFFFF", stroke: ink, "stroke-width": 6 }, eyes);
      EL("circle", { cx, cy: cy + 1, r: big ? 7.6 : 8.2, fill: "#2A1A12" }, eyes);
      EL("circle", { cx: cx - 3.2 * s, cy: cy - 3, r: big ? 2.8 : 3.4, fill: "#FFFFFF" }, eyes);
      // 上睑压线：控制点 cy-22，弧顶正好压在眼白上缘 —— 单眼皮
      EL("path", { d: `M ${cx - 23} ${cy - 2} Q ${cx} ${cy - 22} ${cx + 23} ${cy - 2}`, fill: "none",
                   stroke: ink, "stroke-width": 7, "stroke-linecap": "round" }, eyes);
    });
  }
  g.__eyes = eyes;

  // 腮红 / 鼻
  [-1, 1].forEach(s => {
    EL("ellipse", { cx: 66 * s, cy: -410, rx: 20, ry: 10, fill: K.blush, opacity: expr === "silly" ? 0.42 : 0.22 }, g);
  });
  EL("path", { d: "M -9 -416 q 9 8 18 0", fill: "none", stroke: K.skinSh, "stroke-width": 5.5, "stroke-linecap": "round" }, g);

  // 嘴：整组可缩放，原点取嘴心 y=-378
  const mouth = EL("g", { "data-crisp": "1" }, g);
  if (expr === "silly") {
    EL("path", { d: "M -34 -400 Q 0 -392 34 -400 Q 31 -360 0 -357 Q -31 -360 -34 -400 Z",
                 fill: K.mouth, stroke: ink, "stroke-width": 6, "stroke-linejoin": "round" }, mouth);
    EL("path", { d: "M -27 -396 Q 0 -390 27 -396 Q 25 -380 0 -378 Q -25 -380 -27 -396 Z", fill: "#FFFBF2" }, mouth);
    EL("ellipse", { cx: 0, cy: -367, rx: 15, ry: 8, fill: "#F0726E" }, mouth);
  } else if (expr === "wow") {
    EL("ellipse", { cx: 0, cy: -382, rx: 15, ry: 18, fill: K.mouth, stroke: ink, "stroke-width": 6 }, mouth);
    EL("path", { d: "M -13 -390 Q 0 -385 13 -390 Q 12 -380 0 -379 Q -12 -380 -13 -390 Z", fill: "#FFFBF2" }, mouth);
  } else if (expr === "talk") {
    EL("ellipse", { cx: 0, cy: -378, rx: 20, ry: 17, fill: K.mouth, stroke: ink, "stroke-width": 6 }, mouth);
    EL("path", { d: "M -16 -387 Q 0 -381 16 -387 Q 15 -375 0 -373 Q -15 -375 -16 -387 Z", fill: "#FFFBF2" }, mouth);
    EL("ellipse", { cx: 0, cy: -368, rx: 11, ry: 6, fill: "#F0726E" }, mouth);
  } else {
    EL("path", { d: "M -20 -382 Q 0 -366 20 -382", fill: "none", stroke: ink, "stroke-width": 8, "stroke-linecap": "round" }, mouth);
  }
  g.__mouth = mouth;

  return g;
}

/* ==================================================================
   小熹 · 火狐（简化重画）
   ------------------------------------------------------------------
   简化原则：一个剪影、三个色块、不叠半透明层。
   形体只用 6 个图元：身（形）+ 头（圆）+ 耳（三角×2）+ 口鼻 + 尾 + 腿。
   高度 212（含耳），局部原点在脚底中心。

   视角 view：front 正面 | q34 三分之二 | side 侧面 | back 背面
   表情 expr：idle | happy | wow | think | scope | talk
   尾巴 tail：still | wag | glow
   ================================================================== */
const XI_VIEW = {
  //           身宽 身顶   头x  头y    头r  口鼻偏移 眼 [dx, 缩放]            尾 x    y    rot
  front: { bw: 52, bt: -118, hx: 0,  hy: -152, hr: 42, mu: 0,  eyes: [[-18, 1], [18, 1]],  tail: { x: -36, y: -26, rot: -20 } },
  q34:   { bw: 48, bt: -116, hx: 8,  hy: -152, hr: 42, mu: 26, eyes: [[-11, 0.72], [23, 1]], tail: { x: -40, y: -28, rot: -26 } },
  side:  { bw: 40, bt: -114, hx: 15, hy: -150, hr: 41, mu: 36, eyes: [[26, 1]],               tail: { x: -34, y: -32, rot: -32 } },
  back:  { bw: 52, bt: -118, hx: 0,  hy: -152, hr: 42, mu: 0,  eyes: [],                      tail: { x: -34, y: -28, rot: -12 } },
};
const TAIL_K = 1.14;

/* 蓬松大尾巴：一个填充的叶形（外缘下压、内缘上收），末端一块金色亮毛。
   用填充形而不是粗描边 —— 粗描边做尾巴会变成一根等粗的香肠，没有蓬松感。 */
function xiTail(EL, g, tx, ty, rot, tailState) {
  const k = TAIL_K;
  const tg = EL("g", { "data-crisp": "1", transform: `translate(${tx} ${ty}) rotate(${rot})` }, g);
  const d = `M 0 0 C ${-18 * k} ${-10 * k} ${-40 * k} ${-28 * k} ${-46 * k} ${-50 * k} ` +
            `C ${-50 * k} ${-66 * k} ${-44 * k} ${-80 * k} ${-32 * k} ${-82 * k} ` +
            `C ${-18 * k} ${-84 * k} ${-10 * k} ${-70 * k} ${-8 * k} ${-54 * k} ` +
            `C ${-6 * k} ${-34 * k} ${-3 * k} ${-14 * k} 0 0 Z`;
  EL("path", { d, fill: G.fur, stroke: X.ink, "stroke-width": X.sw, "stroke-linejoin": "round" }, tg);
  // 尾尖金色亮毛
  EL("ellipse", { cx: -33 * k, cy: -72 * k, rx: 15 * k, ry: 13 * k, fill: G.gold,
                  stroke: X.ink, "stroke-width": 5, transform: `rotate(-30 ${-33 * k} ${-72 * k})` }, tg);
  if (tailState === "glow") {
    EL("circle", { cx: -33 * k, cy: -72 * k, r: 66, fill: "url(#gGold)", opacity: 0.9 }, tg);
    [[-33, -72, 0], [-62, -50, 1], [-10, -88, 2]].forEach(([cx, cy, i]) => {
      const s = 9 + i * 3;
      EL("path", { d: `M ${cx} ${cy - s} L ${cx + s * 0.3} ${cy - s * 0.3} L ${cx + s} ${cy} L ${cx + s * 0.3} ${cy + s * 0.3} ` +
                      `L ${cx} ${cy + s} L ${cx - s * 0.3} ${cy + s * 0.3} L ${cx - s} ${cy} L ${cx - s * 0.3} ${cy - s * 0.3} Z`,
                   fill: X.goldLt, opacity: 0.95 - i * 0.2 }, tg);
    });
  }
  return tg;
}

function buildXi(EL, opt, parent) {
  ensureGrads();
  // 兼容老调用：buildXi(EL, "glow")
  if (typeof opt === "string") opt = { expr: opt === "scope" ? "scope" : "happy", tail: opt === "glow" ? "glow" : "still" };
  opt = opt || {};
  const view = XI_VIEW[opt.view] ? opt.view : "front";
  const V = XI_VIEW[view];
  const expr = opt.expr || "idle";
  const tailState = opt.tail || "still";
  const back = view === "back";

  const g = EL("g", {}, parent);
  const ink = X.ink, sw = X.sw;

  EL("ellipse", { cx: 0, cy: 3, rx: 54, ry: 10, fill: ink, opacity: 0.12 }, g);

  // ---- 1. 尾巴（在身体之后）
  g.__tail = xiTail(EL, g, V.tail.x, V.tail.y, V.tail.rot, tailState);

  // ---- 2. 身体：一个对称梨形
  const bw = V.bw, bt = V.bt;
  EL("path", { d: `M ${-bw} -6 Q ${-bw * 1.08} ${bt * 0.55} ${-bw * 0.66} ${bt * 0.95} ` +
                  `Q 0 ${bt - 12} ${bw * 0.66} ${bt * 0.95} ` +
                  `Q ${bw * 1.08} ${bt * 0.55} ${bw} -6 Q 0 6 ${-bw} -6 Z`,
               fill: G.fur, stroke: ink, "stroke-width": sw, "stroke-linejoin": "round" }, g);
  if (back) {
    EL("ellipse", { cx: 0, cy: -74, rx: 30, ry: 44, fill: X.furDk, opacity: 0.45 }, g);
  } else if (view === "side") {
    EL("path", { d: "M -14 -8 Q -20 -64 -6 -96 Q 6 -68 4 -8 Z", fill: X.cream }, g);
  } else {
    EL("path", { d: `M ${-26} -10 Q ${-32} -66 ${-14} -100 Q 0 -110 ${14} -100 ` +
                    `Q ${32} -66 ${26} -10 Q 0 2 ${-26} -10 Z`, fill: X.cream }, g);
  }

  // ---- 3. 腿
  (view === "side" ? [[-26, 22], [18, 24]] : [[-24, 20], [14, 20]]).forEach(([x, w]) => {
    EL("rect", { x, y: -34, width: w, height: 36, rx: w / 2, fill: X.furDk, stroke: ink, "stroke-width": sw }, g);
  });

  /* ---- 4. 头部整组：think 时整体歪一点，比改各部件坐标省事 ---- */
  const tilt = expr === "think" ? -7 : 0;
  const head = EL("g", { transform: tilt ? `rotate(${tilt} ${V.hx} ${V.hy + 30})` : "" }, g);
  const hx = V.hx, hy = V.hy, hr = V.hr;

  // 耳：画在头之前
  const earUp = expr === "wow" ? 6 : expr === "think" ? -10 : 0;
  const ears = view === "side" ? [[hx - 10, 0.7], [hx + 22, 1]] : [[hx - 26, 1], [hx + 24, 1]];
  ears.forEach(([ex, sc], i) => {
    const far = sc < 1;
    const ey = hy - 26 + earUp;
    EL("path", { d: `M ${ex - 19 * sc} ${ey + 16} Q ${ex - 10 * sc} ${ey - 20 * sc} ${ex + 3} ${ey - 28 * sc} ` +
                    `Q ${ex + 17 * sc} ${ey - 12 * sc} ${ex + 19 * sc} ${ey + 14} Z`,
                 fill: far ? X.furDk : X.fur, stroke: ink, "stroke-width": sw, "stroke-linejoin": "round" }, head);
    if (!back) {
      EL("path", { d: `M ${ex - 10 * sc} ${ey + 12} Q ${ex - 5 * sc} ${ey - 10 * sc} ${ex} ${ey - 18 * sc} ` +
                      `Q ${ex + 9 * sc} ${ey - 8 * sc} ${ex + 10 * sc} ${ey + 10} Z`,
                   fill: X.ear, opacity: far ? 0.45 : 1 }, head);
    }
  });

  EL("circle", { cx: hx, cy: hy, r: hr, fill: G.fur, stroke: ink, "stroke-width": sw }, head);
  if (back) EL("path", { d: `M ${hx - hr} ${hy - 6} A ${hr} ${hr} 0 0 0 ${hx + hr} ${hy - 6} Q ${hx} ${hy + hr * 0.55} ${hx - hr} ${hy - 6} Z`, fill: X.furDk, opacity: 0.55 }, head);


  // 口鼻
  if (!back) {
    if (view === "side") {
      EL("path", { d: `M ${hx + 14} ${hy + 2} q 24 1 28 12 q -7 10 -24 7 q -12 -2 -14 -10 z`,
                   fill: G.cream, stroke: ink, "stroke-width": sw, "stroke-linejoin": "round" }, head);
      EL("ellipse", { cx: hx + 40, cy: hy + 10, rx: 7, ry: 5.5, fill: X.nose }, head);
    } else {
      const mx0 = hx + V.mu * 0.4;
      EL("ellipse", { cx: mx0, cy: hy + 17, rx: 15, ry: 11, fill: G.cream, stroke: ink, "stroke-width": 5 }, head);
      EL("path", { d: `M ${mx0 - 6} ${hy + 10} q 6 -5 12 0 q -6 7 -12 0 z`, fill: X.nose }, head);
      // giggle 加腮红
      if (expr === "giggle" || expr === "happy") {
        [-1, 1].forEach(s => EL("ellipse", { cx: hx + s * 30, cy: hy + 14, rx: 10, ry: 6, fill: "#F2795C", opacity: 0.4 }, head));
      }
    }
  }

  // 眼
  const eyesG = EL("g", { "data-crisp": "1" }, head);
  if (!back) {
    const closedArc = expr === "happy" || expr === "giggle";
    V.eyes.forEach(([dx, sc], i) => {
      const cx = hx + dx, cy = hy - 8;
      if (closedArc) {
        EL("path", { d: `M ${cx - 11 * sc} ${cy + 3} Q ${cx} ${cy - 10 * sc} ${cx + 11 * sc} ${cy + 3}`, fill: "none",
                     stroke: ink, "stroke-width": 6, "stroke-linecap": "round" }, eyesG);
        return;
      }
      if (expr === "think" && i === 0 && V.eyes.length > 1) {
        // 一只眼半眯 = 正在想
        EL("path", { d: `M ${cx - 10} ${cy} q 10 -6 20 0`, fill: "none", stroke: ink, "stroke-width": 5.5, "stroke-linecap": "round" }, eyesG);
        return;
      }
      if (expr === "scope" && V.eyes.length > 1 && i === V.eyes.length - 1 && view !== "side") return;
      const r = (expr === "wow" ? 10 : 8) * sc;
      EL("circle", { cx, cy, r, fill: X.nose }, eyesG);
      EL("circle", { cx: cx - r * 0.3, cy: cy - r * 0.32, r: r * 0.36, fill: "#FFFFFF" }, eyesG);
    });
  }
  g.__eyes = eyesG;

  // 嘴（可动组）；背面视角不画
  const mouth = EL("g", { "data-crisp": "1" }, head);
  if (back) { g.__mouth = mouth; return g; }
  const mx = view === "side" ? hx + 34 : hx + V.mu * 0.35;
  const my = view === "side" ? hy + 22 : hy + 27;
  if (expr === "giggle" || expr === "talk") {
    // 张嘴：深色口腔 + 舌头
    EL("path", { d: `M ${mx - 11} ${my - 4} q 11 3 22 0 q -2 15 -11 15 q -9 0 -11 -15 z`, fill: X.nose }, mouth);
    EL("ellipse", { cx: mx, cy: my + 9, rx: 6, ry: 4, fill: "#F0726E" }, mouth);
  } else if (expr === "wow") {
    EL("ellipse", { cx: mx, cy: my + 1, rx: 6, ry: 8, fill: X.nose }, mouth);
  } else if (expr === "think") {
    EL("path", { d: `M ${mx - 8} ${my} q 4 4 8 0 q 4 4 8 0`, fill: "none", stroke: X.nose, "stroke-width": 4, "stroke-linecap": "round" }, mouth);
  } else {
    EL("path", { d: `M ${mx - 8} ${my} q 8 6 16 0`, fill: "none", stroke: X.nose, "stroke-width": 4, "stroke-linecap": "round" }, mouth);
  }
  g.__mouth = mouth;

  // 望远镜
  if (expr === "scope" && !back) {
    const ex = hx + (view === "side" ? 30 : 26), ey = hy - 12;
    const tube = EL("g", { transform: `rotate(${view === "side" ? -14 : -26} ${ex} ${ey})` }, head);
    EL("rect", { x: ex - 10, y: ey - 8, width: 66, height: 16, rx: 8, fill: X.brass, stroke: ink, "stroke-width": 5 }, tube);
    EL("rect", { x: ex + 48, y: ey - 11, width: 14, height: 22, rx: 6, fill: X.brassDk, stroke: ink, "stroke-width": 5 }, tube);
    EL("rect", { x: ex - 14, y: ey - 10, width: 9, height: 20, rx: 4, fill: X.brassDk, stroke: ink, "stroke-width": 4 }, tube);
  }

  return g;
}
