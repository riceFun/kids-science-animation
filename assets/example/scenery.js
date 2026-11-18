/* 本集场景｜为什么天是蓝的
 * ---------------------------------------------------------------
 * 没有背景库，也没有话题映射表。这一集讲到哪些地方，就画哪些地方。
 * 台本里的 "bg" 就是这里注册的名字。
 *
 * 规则：
 *   1) 每个场景返回 update(t)，让画面会呼吸（云飘、星闪、尘埃漂）；
 *   2) 挂 .light 指定光源，主光光晕会移过去；
 *   3) 挂 .prof 定后期档位，亮场景要轻，暗场景要重。
 * --------------------------------------------------------------- */
(function () {
  const K = window.SCENE_KIT;
  const { el, rnd, nearSil, W, H } = K;

  /* ---------------- 午后草地：开场提问 ----------------- */
  const afternoon = K.scene("午后草地", (root) => {
    el("rect", { width: W, height: H, fill: "url(#gSkyDay)" }, root);
    const sun = el("g", { transform: "translate(1600 200)" }, root);
    el("circle", { cx: 0, cy: 0, r: 220, fill: "url(#gSun)" }, sun);
    el("circle", { cx: 0, cy: 0, r: 70, fill: "#FFF3B8" }, sun);

    const clouds = el("g", {}, root);
    [[420, 210, 1.0], [980, 150, 0.72], [1420, 300, 0.86]].forEach(([x, y, s]) => {
      const g = el("g", { transform: `translate(${x} ${y}) scale(${s})` }, clouds);
      [[0, 0, 74], [78, 12, 56], [-76, 14, 50], [30, -34, 54]].forEach(([cx, cy, r]) => {
        el("circle", { cx, cy, r, fill: "#FFFFFF", opacity: 0.9 }, g);
      });
    });

    el("path", { d: "M0 700 Q 480 620 960 700 T 1920 680 V1080 H0 Z", fill: "#CDEBA4" }, root);
    el("path", { d: "M0 820 Q 520 740 1080 830 T 1920 810 V1080 H0 Z", fill: "#ABE664" }, root);
    el("path", { d: "M0 920 Q 600 860 1200 940 T 1920 910 V1080 H0 Z", fill: "#8FD44B" }, root);
    nearSil(root, "grass", "#4B8620", 0.95);

    return (t) => { clouds.setAttribute("transform", `translate(${(t * 6) % 240} 0)`); };
  });
  afternoon.light = { x: 1600, y: 175 };
  afternoon.prof = { grade: 0.02, vig: 0.06 };

  /* ---------------- 光的实验室：白光 / 水杯分光 ---------------- */
  const lab = K.scene("光的实验室", (root, seg) => {
    el("rect", { width: W, height: H, fill: "url(#gRoom)" }, root);
    // 右侧窗
    el("rect", { x: 1380, y: 110, width: 420, height: 360, rx: 18, fill: "#BFE4F5", stroke: "#B08A5E", "stroke-width": 14 }, root);
    el("line", { x1: 1590, y1: 110, x2: 1590, y2: 470, stroke: "#B08A5E", "stroke-width": 12 }, root);
    el("line", { x1: 1380, y1: 290, x2: 1800, y2: 290, stroke: "#B08A5E", "stroke-width": 12 }, root);
    // 桌面
    el("rect", { x: 0, y: 830, width: W, height: 250, fill: "#C79B6B" }, root);
    el("rect", { x: 0, y: 818, width: W, height: 30, fill: "#A97C4E" }, root);
    // 一束白光 + 水杯（分光实验的核心）
    const beam = el("path", { d: "M 1380 260 L 760 470 L 800 540 L 1400 300 Z", fill: "#FFF6C8", opacity: 0.5 }, root);
    el("path", { d: "M 740 470 L 700 620 L 820 620 L 800 470 Z", fill: "#DFF3FF", opacity: 0.55 }, root);
    el("rect", { x: 722, y: 470, width: 76, height: 150, rx: 12, fill: "none", stroke: "#8FB8CF", "stroke-width": 6 }, root);
    // 分出的淡蓝
    el("path", { d: "M 800 540 L 980 700 L 1040 660 L 840 500 Z", fill: "#7FB4E8", opacity: 0.42 }, root);
    return (t) => { beam.setAttribute("opacity", 0.42 + 0.12 * Math.sin(t * 1.6)); };
  });
  lab.light = { x: 1420, y: 300 };
  lab.prof = { grade: 0.03, vig: 0.1 };

  /* ---------------- 高空云海：雨后彩虹 ---------------- */
  const highSky = K.scene("高空云海", (root) => {
    el("rect", { width: W, height: H, fill: "url(#gSkyHigh)" }, root);
    const sun = el("g", { transform: "translate(1480 190)" }, root);
    el("circle", { cx: 0, cy: 0, r: 190, fill: "url(#gSun)" }, sun);
    el("circle", { cx: 0, cy: 0, r: 60, fill: "#FFF3B8" }, sun);
    // 云海：三层扁平云团
    [[0.95, 880, "#FFFFFF"], [0.85, 930, "#F2FAFF"], [0.75, 980, "#E2F3FD"]].forEach(([op, y, col], li) => {
      const g = el("g", { opacity: op }, root);
      for (let i = 0; i < 9; i++) {
        const cx = -80 + i * 260 + (li % 2) * 90, r = 80 + rnd(i * 3.7 + li) * 60;
        el("ellipse", { cx, cy: y + (i % 3) * 26, rx: r * 1.6, ry: r * 0.62, fill: col }, g);
      }
    });
    // 彩虹弧
    const rb = el("g", { opacity: 0.5 }, root);
    ["#F5813C", "#F4C93C", "#8FD44B", "#5FB8E8", "#8E6CC4"].forEach((c, i) => {
      el("path", { d: `M ${300 + i * 16} 900 A ${660 - i * 16} ${660 - i * 16} 0 0 1 ${1620 - i * 16} 900`,
                   fill: "none", stroke: c, "stroke-width": 16, opacity: 0.55 }, rb);
    });
    return (t) => { rb.setAttribute("opacity", 0.35 + 0.2 * Math.abs(Math.sin(t * 0.6))); };
  });
  highSky.light = { x: 1480, y: 175 };
  highSky.prof = { grade: 0.02, vig: 0.08 };

  /* ---------------- 微观空气：悬浮的小分子 ---------------- */
  const micro = K.scene("微观空气", (root, seg) => {
    el("rect", { width: W, height: H, fill: "url(#gMicro)" }, root);
    el("rect", { width: W, height: H, fill: "url(#pGrid)", opacity: 0.5 }, root);
    // 小分子：暗底上的淡蓝小球，大小不一
    const mols = el("g", {}, root), M = [];
    for (let i = 0; i < 40; i++) {
      const r = 6 + rnd(i * 4.1) * 14;
      const x0 = rnd(i * 3.3) * W, y0 = rnd(i * 7.9) * H;
      const c = el("circle", { cx: x0, cy: y0, r,
                               fill: i % 3 ? "#7FB4E8" : "#BFE4FF", opacity: 0.55 }, mols);
      // 存基坐标，按 t 绝对求值：同一 t 永远同一位置（分片渲染/预览才不会错位）
      M.push({ c, x0, y0, ph: rnd(i * 2.7) * 6.28, amp: 14 + rnd(i * 5.3) * 22 });
    }
    // 一条光的波：正弦曲线，示意"光在往前跑"
    const wave = el("path", { d: "", fill: "none", stroke: "#FFE98A", "stroke-width": 7,
                              "stroke-linecap": "round", opacity: 0.8 }, root);
    return (t) => {
      M.forEach(m => {
        m.c.setAttribute("cx", m.x0 + Math.sin(t * 0.4 + m.ph) * m.amp);
        m.c.setAttribute("cy", m.y0 + Math.cos(t * 0.5 + m.ph) * m.amp);
      });
      let d = "M 60 540";
      for (let x = 60; x <= 1860; x += 20) d += ` L ${x} ${540 + Math.sin(x * 0.012 + t * 3) * 90}`;
      wave.setAttribute("d", d);
    };
  });
  micro.light = { x: 960, y: 80 };
  micro.prof = { grade: 0.06, vig: 0.3 };

  /* ---------------- 傍晚天空：斜射的光 ---------------- */
  const dusk = K.scene("傍晚天空", (root) => {
    // 从上到下：深蓝 → 橙红 → 金
    el("rect", { width: W, height: 420, fill: "#2E4A82" }, root);
    el("rect", { y: 260, width: W, height: 380, fill: "#C6663E" }, root);
    el("rect", { y: 520, width: W, height: 300, fill: "#E89A4E" }, root);
    el("rect", { y: 720, width: W, height: 360, fill: "#F3C27A" }, root);
    // 落日
    const sun = el("g", { transform: "translate(1380 760)" }, root);
    el("circle", { cx: 0, cy: 0, r: 230, fill: "url(#gSun)", opacity: 0.75 }, sun);
    el("circle", { cx: 0, cy: 0, r: 72, fill: "#FFE9A8" }, sun);
    // 远山
    el("path", { d: "M0 880 Q 460 800 960 870 T 1920 850 V1080 H0 Z", fill: "#7A4A3C" }, root);
    el("path", { d: "M0 960 Q 540 900 1120 970 T 1920 940 V1080 H0 Z", fill: "#4E2E2A" }, root);
    return (t) => { sun.setAttribute("opacity", 0.8 + 0.1 * Math.sin(t * 0.5)); };
  });
  dusk.light = { x: 1380, y: 620 };
  dusk.prof = { grade: 0.04, vig: 0.16 };

  /* ---------------- 夜色草地：收尾 / 儿歌 ---------------- */
  const night = K.scene("夜色草地", (root) => {
    el("rect", { width: W, height: H, fill: "url(#gSkyNight)" }, root);
    const stars = el("g", {}, root);
    for (let i = 0; i < 120; i++) {
      el("circle", { cx: rnd(i * 3.1) * W, cy: rnd(i * 7.7) * 620, r: 1.5 + rnd(i * 2.3) * 2.4,
                     fill: "#FFFFFF", opacity: 0.55 }, stars);
    }
    const moon = el("g", { transform: "translate(1560 190)" }, root);
    el("circle", { cx: 0, cy: 0, r: 200, fill: "url(#gSun)", opacity: 0.5 }, moon);
    el("circle", { cx: 0, cy: 0, r: 74, fill: "#FFF6D8" }, moon);
    el("path", { d: "M0 760 Q 380 680 780 740 T 1920 720 V1080 H0 Z", fill: "#24486F" }, root);
    el("path", { d: "M0 860 Q 460 800 960 840 T 1920 830 V1080 H0 Z", fill: "#1C3A5C" }, root);
    nearSil(root, "grass", "#122A45", 0.9);
    // 萤火虫
    const F = [];
    for (let i = 0; i < 14; i++) {
      const g = el("g", {}, root);
      el("circle", { cx: 0, cy: 0, r: 42, fill: "url(#gSun)", opacity: 0.5 }, g);
      el("circle", { cx: 0, cy: 0, r: 4.5, fill: "#FFF6B0" }, g);
      F.push({ g, x: 140 + rnd(i * 5.3) * 1640, y: 480 + rnd(i * 9.1) * 420, ph: rnd(i * 1.7) * 6.28 });
    }
    return (t) => {
      stars.setAttribute("opacity", 0.75 + 0.25 * Math.sin(t * 1.3));
      F.forEach(f => {
        f.g.setAttribute("transform",
          `translate(${f.x + Math.sin(t * 0.5 + f.ph) * 50} ${f.y + Math.cos(t * 0.42 + f.ph) * 30})`);
        f.g.setAttribute("opacity", 0.4 + 0.6 * Math.abs(Math.sin(t * 1.6 + f.ph)));
      });
    };
  });
  night.light = { x: 1560, y: 165 };
  night.prof = { grade: 0.07, vig: 0.28 };

  /* ================= 光学示意图（替掉原来的圆盘图标） ================= */

  /* 三棱镜把白光拆成七色 */
  K.figure("三棱镜分色", (g) => {
    el("path", { d: "M 700 260 L 980 720 L 420 720 Z", fill: "#CFE6F2", stroke: "#2E4A66", "stroke-width": 8,
                 opacity: 0.9 }, g);
    // 入射白光
    el("path", { d: "M 120 470 L 640 620", stroke: "#FFFFFF", "stroke-width": 26, opacity: 0.95 }, g);
    // 出射七色
    ["#F0453A", "#F58A2E", "#F4C93C", "#7FBF4E", "#4FA8D8", "#4A5FB5", "#7C4FA8"].forEach((c, i) => {
      el("path", { d: `M 900 ${470 + i * 10} L 1700 ${300 + i * 74}`, stroke: c, "stroke-width": 14,
                   opacity: 0.95, "stroke-linecap": "round" }, g);
    });
    return () => {};
  });

  /* 一杯水把光分开 */
  K.figure("水杯分光", (g) => {
    el("path", { d: "M 200 420 L 660 470", stroke: "#FFFFFF", "stroke-width": 26, opacity: 0.9 }, g);
    el("rect", { x: 700, y: 380, width: 300, height: 400, rx: 16, fill: "#DFF3FF", opacity: 0.55,
                 stroke: "#8FB8CF", "stroke-width": 8 }, g);
    el("rect", { x: 712, y: 500, width: 276, height: 268, fill: "#BFE4FF", opacity: 0.55 }, g);
    ["#7FB4E8", "#A8C8F0", "#C9D8F5"].forEach((c, i) => {
      el("path", { d: `M 1000 ${430 + i * 90} L 1600 ${380 + i * 120}`, stroke: c, "stroke-width": 22,
                   opacity: 0.7, "stroke-linecap": "round" }, g);
    });
    return (tt) => {};
  });

  /* 空气里的小分子：放大一颗，周围一片 */
  K.figure("小分子", (g) => {
    for (let i = 0; i < 22; i++) {
      el("circle", { cx: 180 + rnd(i * 3.3) * 1560, cy: 240 + rnd(i * 7.9) * 560,
                     r: 8 + rnd(i * 2.3) * 14, fill: "#8FC4E8", opacity: 0.5 }, g);
    }
    const m = el("g", { transform: "translate(960 520)" }, g);
    el("circle", { cx: -96, cy: 0, r: 78, fill: "#7FB4E8", stroke: "#2E4A66", "stroke-width": 7 }, m);
    el("circle", { cx: 96, cy: 0, r: 78, fill: "#7FB4E8", stroke: "#2E4A66", "stroke-width": 7 }, m);
    el("circle", { cx: 0, cy: 0, r: 62, fill: "#FFD34D", stroke: "#2E4A66", "stroke-width": 7 }, m);
    const t = K.txt(g, "比光的波长还小", 960, 760, 40, "#FDF4E2", 700, "middle");
    t.setAttribute("stroke", "#3A2A1C"); t.setAttribute("stroke-width", 9); t.setAttribute("paint-order", "stroke fill");
    return (tt) => m.setAttribute("transform", `translate(960 ${520 + Math.sin(tt * 1.2) * 10})`);
  });

  /* 光撞上小分子拐弯 */
  K.figure("散射光路", (g) => {
    el("path", { d: "M 100 540 H 1740", stroke: "#FFE9A8", "stroke-width": 14, opacity: 0.85 }, g);
    for (let i = 0; i < 5; i++) {
      const x = 420 + i * 280;
      el("circle", { cx: x, cy: 540, r: 34, fill: "#7FB4E8", stroke: "#2E4A66", "stroke-width": 6 }, g);
      el("path", { d: `M ${x} 540 L ${x + 120} ${540 - 150}`, stroke: "#7FB4E8", "stroke-width": 10,
                   "stroke-linecap": "round", opacity: 0.85 }, g);
      el("path", { d: `M ${x} 540 L ${x + 90} ${540 + 170}`, stroke: "#7FB4E8", "stroke-width": 10,
                   "stroke-linecap": "round", opacity: 0.85 }, g);
    }
    return () => {};
  });

  /* 长波 vs 短波 */
  K.figure("波长对比", (g) => {
    let d1 = "M 200 400";
    for (let x = 200; x <= 1700; x += 20) d1 += ` L ${x} ${400 + Math.sin(x * 0.008) * 70}`;
    el("path", { d: d1, fill: "none", stroke: "#F0453A", "stroke-width": 10 }, g);
    let d2 = "M 200 660";
    for (let x = 200; x <= 1700; x += 20) d2 += ` L ${x} ${660 + Math.sin(x * 0.028) * 70}`;
    el("path", { d: d2, fill: "none", stroke: "#4FA8D8", "stroke-width": 10 }, g);
    const a = K.txt(g, "红光：波长大", 240, 300, 38, "#FDF4E2", 700, "start");
    a.setAttribute("stroke", "#3A2A1C"); a.setAttribute("stroke-width", 9); a.setAttribute("paint-order", "stroke fill");
    const b = K.txt(g, "蓝光：波长小", 240, 800, 38, "#FDF4E2", 700, "start");
    b.setAttribute("stroke", "#3A2A1C"); b.setAttribute("stroke-width", 9); b.setAttribute("paint-order", "stroke fill");
    return () => {};
  });

  /* 傍晚：光走的路变长，蓝光半路散掉 */
  K.figure("傍晚光路", (g) => {
    const sun = el("g", { transform: "translate(280 300)" }, g);
    el("circle", { cx: 0, cy: 0, r: 130, fill: "url(#gSun)", opacity: 0.85 }, sun);
    el("circle", { cx: 0, cy: 0, r: 54, fill: "#FFE9A8" }, sun);
    el("path", { d: "M 380 340 L 1620 720", stroke: "#F0453A", "stroke-width": 16, opacity: 0.9 }, g);
    el("path", { d: "M 380 300 L 1200 520", stroke: "#4FA8D8", "stroke-width": 14, opacity: 0.8 }, g);
    for (let i = 0; i < 6; i++) {
      const x = 980 + i * 90;
      el("circle", { cx: x, cy: 700 - i * 20, r: 12, fill: "#4FA8D8", opacity: 0.5 }, g);
    }
    const t = K.txt(g, "蓝光半路就散了", 1180, 860, 40, "#FDF4E2", 700, "middle");
    t.setAttribute("stroke", "#3A2A1C"); t.setAttribute("stroke-width", 9); t.setAttribute("paint-order", "stroke fill");
    return () => {};
  });

  /* 没有空气：光直着走，不拐弯 */
  K.figure("无散射", (g) => {
    el("path", { d: "M 160 540 H 1740", stroke: "#FFE9A8", "stroke-width": 16, opacity: 0.95 }, g);
    for (let i = 0; i < 8; i++) {
      el("path", { d: `M ${160 + i * 210} 500 l 40 0`, stroke: "#FFF6C4", "stroke-width": 5, opacity: 0.5 }, g);
    }
    const t = K.txt(g, "没有小分子，光一路直着走", 960, 760, 40, "#FDF4E2", 700, "middle");
    t.setAttribute("stroke", "#3A2A1C"); t.setAttribute("stroke-width", 9); t.setAttribute("paint-order", "stroke fill");
    return () => {};
  });
})();
