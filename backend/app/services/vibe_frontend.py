from __future__ import annotations

import html
import json
from typing import Any

from app.prompts.coding_bundle import CODING_PROMPT_VERSION
from app.schemas.contracts import (
    CodingBundle,
    GeneratedCodeFile,
    PrdContent,
    SolutionContent,
)


def _safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


UI_STYLES: dict[str, dict[str, str]] = {
    "slack-aubergine": {
        "name": "Slack 紫色舞台",
        "source": "https://styles.refero.design/style/e26cb9b0-f876-41ff-9f24-fd67a6b9776c",
        "canvas": "#fefbff", "surface": "rgba(255,255,255,.94)", "text": "#1d1c1d",
        "muted": "#696969", "primary": "#611f69", "strong": "#481a54", "accent": "#d17dfe", "on_primary": "#ffffff",
        "border": "#eac8fe", "radius": "20px", "shadow": "0 24px 64px rgba(72,26,84,.16)",
        "background": "radial-gradient(circle at 12% 12%, rgba(209,125,254,.22), transparent 25rem), #fefbff",
    },
    "pirsch-paper": {
        "name": "Pirsch 纸张笔记",
        "source": "https://styles.refero.design/style/e4b9d41a-8165-47dd-818a-5f6810046ea9",
        "canvas": "#f8f5ed", "surface": "rgba(248,245,237,.96)", "text": "#000000",
        "muted": "#707070", "primary": "#6ece9d", "strong": "#3d966b", "accent": "#ffda6e", "on_primary": "#000000",
        "border": "#000000", "radius": "8px", "shadow": "8px 8px 0 rgba(0,0,0,.12)",
        "background": "linear-gradient(rgba(255,218,110,.13) 1px, transparent 1px), #f8f5ed",
    },
    "aira-editorial": {
        "name": "Aira 黑白编辑",
        "source": "https://styles.refero.design/style/750387be-bda4-448b-950f-c9356c3ec25f",
        "canvas": "#fafafb", "surface": "rgba(250,250,251,.96)", "text": "#080808",
        "muted": "#70706f", "primary": "#1f1f1f", "strong": "#080808", "accent": "#cbcbcb", "on_primary": "#ffffff",
        "border": "#2c2c2b", "radius": "2px", "shadow": "0 20px 48px rgba(8,8,8,.08)",
        "background": "linear-gradient(120deg, #fafafb 0 68%, #ededed 68% 100%)",
    },
    "atlassian-confetti": {
        "name": "Atlassian 彩色工程",
        "source": "https://styles.refero.design/style/c08ebca5-87d4-4c19-a5d7-ae5e670dae11",
        "canvas": "#ffffff", "surface": "rgba(255,255,255,.96)", "text": "#101214",
        "muted": "#42526e", "primary": "#1868db", "strong": "#0c4aa2", "accent": "#fca700", "on_primary": "#ffffff",
        "border": "#b7b9be", "radius": "12px", "shadow": "0 22px 54px rgba(24,104,219,.15)",
        "background": "conic-gradient(from 210deg at 12% 12%, #eed7fc, #fff 18%, #fff 75%, rgba(252,167,0,.18), #eed7fc)",
    },
    "ameba-midnight": {
        "name": "Ameba 深夜玻璃",
        "source": "https://styles.refero.design/style/371df039-a090-402b-b2e4-21ab38e07625",
        "canvas": "#00052e", "surface": "rgba(13,23,78,.82)", "text": "#ffffff",
        "muted": "#afb4db", "primary": "#34fcff", "strong": "#16bdc5", "accent": "#6e7cff", "on_primary": "#00052e",
        "border": "rgba(52,252,255,.34)", "radius": "22px", "shadow": "0 24px 80px rgba(52,252,255,.17)",
        "background": "radial-gradient(circle at 80% 18%, rgba(52,252,255,.22), transparent 30rem), #00052e",
    },
    "sprout-contrast": {
        "name": "Sprout 黑白高对比",
        "source": "https://styles.refero.design/style/da7c4464-f135-41fc-b635-99c6f4dc58e6",
        "canvas": "#ffffff", "surface": "#ffffff", "text": "#040404",
        "muted": "#6e797a", "primary": "#040404", "strong": "#162020", "accent": "#98e58e", "on_primary": "#ffffff",
        "border": "#040404", "radius": "0px", "shadow": "10px 10px 0 #98e58e",
        "background": "linear-gradient(135deg, #fff 0 72%, rgba(152,229,142,.38) 72% 100%)",
    },
    "surfshark-coastal": {
        "name": "Surfshark 海岸双色",
        "source": "https://styles.refero.design/style/4fc7a535-3c99-4ffe-8365-7d025d33274e",
        "canvas": "#f9f9f9", "surface": "rgba(255,255,255,.96)", "text": "#16191c",
        "muted": "#5b6065", "primary": "#fa3556", "strong": "#d51e40", "accent": "#1ebfbf", "on_primary": "#ffffff",
        "border": "#dadadd", "radius": "24px", "shadow": "0 24px 60px rgba(30,191,191,.18)",
        "background": "linear-gradient(145deg, rgba(30,191,191,.18), #fff 48%, rgba(250,53,86,.12))",
    },
    "pop-typographic": {
        "name": "Pop Site 巨型排版",
        "source": "https://styles.refero.design/style/e7d4a7de-aeaf-4d49-8c0c-0dedd05a8992",
        "canvas": "#ffffff", "surface": "#ffffff", "text": "#000000",
        "muted": "#5e5e5e", "primary": "#3b82f6", "strong": "#1f5fca", "accent": "#e3eeff", "on_primary": "#ffffff",
        "border": "#000000", "radius": "999px", "shadow": "0 18px 0 #e3eeff",
        "background": "#ffffff",
    },
}


def _is_timer_product(prd: PrdContent) -> bool:
    haystack = " ".join(
        [
            prd.title,
            prd.summary,
            *prd.features,
            *prd.acceptance_criteria,
            *prd.scope.get("included", []),
            prd.full_document.model_dump_json() if prd.full_document else "",
        ]
    )
    explicit_keywords = (
        "番茄钟",
        "倒计时",
        "计时器",
        "学习闹钟",
        "专注计时",
        "25 分钟",
        "25分钟",
    )
    interaction_keywords = ("暂停", "继续", "剩余时间", "短休息", "长休息", "完成轮数")
    return any(keyword in haystack for keyword in explicit_keywords) or (
        "专注" in haystack and any(keyword in haystack for keyword in interaction_keywords)
    )


def _adaptation_document(prd: PrdContent) -> str:
    return f"""# 前端技术适配声明

## 1. 项目判断
- 产品类型：{prd.title}
- 主要终端：桌面 Web 与移动 Web
- 本阶段目标：把已确认 PRD 与方案生成一个可直接操作的本地 HTML 产品预览。

## 2. 输入资料
- PRD：已读取，使用确认版本及其 full_document
- 技术方案：已读取，使用确认版本
- 前端手册：已读取《AI 产品 Vibe Coding 通用前端技术栈手册》V1.0
- 设计稿：无，采用中性、清晰、响应式的代表页方向

## 3. 技术选择
- 交付形式：单文件语义化 HTML，内联 CSS 与原生 JavaScript
- 偏离默认 Next.js 的原因：当前是由受控 Python 预览运行时承载的单页 MVP，用户明确要求 HTML；不增加 Node 构建链可减少生成和恢复成本
- 状态策略：页面临时状态留在浏览器；任务、代码版本和预览状态以后端为最终事实来源
- 安全：不写入密钥，不调用第三方脚本，不渲染不可信 HTML
- 测试：Python 契约测试、真实 HTTP 冒烟、桌面与 390px 移动端浏览器验收

## 4. 产物与恢复
- 页面入口：生成运行时根路径 `/`
- 健康检查：`GET /api/v1/health`
- 追溯：`product_factory.json` 记录 PRD、方案和产品决策来源
- 恢复：生成文件进入项目隔离工作区并保存 Git commit
"""


def _stage_document(prd: PrdContent) -> str:
    criteria = "\n".join(f"- {item}" for item in prd.acceptance_criteria)
    return f"""# 第三阶段前端开发文档

## 1. 本阶段目标
生成并运行“{prd.title}”的第一条可操作业务闭环。

## 2. 范围
- 页面：单页产品预览
- 状态：初始、运行、暂停、继续、重置、完成和安全兜底
- 产物：HTML 页面、后端运行入口、自动测试与追溯清单
- 不包含：PRD 明确排除的功能、账号体系和公网部署

## 3. 验收标准
{criteria}

## 4. 自动检查
- Python 语法编译
- pytest 契约测试
- 启动真实预览进程
- 访问 HTML 页面与健康接口
- 在浏览器检查桌面端和移动端
"""


def _timer_html(prd: PrdContent, ui_style_key: str) -> str:
    title = html.escape(prd.title)
    summary = html.escape(prd.summary)
    theme = UI_STYLES.get(ui_style_key, UI_STYLES["pirsch-paper"])
    style_name = html.escape(theme["name"])
    config = _safe_json(
        {
            "title": prd.title,
            "focusSeconds": 25 * 60,
            "shortBreakSeconds": 5 * 60,
            "longBreakSeconds": 15 * 60,
            "roundsBeforeLongBreak": 4,
        }
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{title}</title>
  <style>
    :root {{
      --color-bg: {theme["canvas"]};
      --color-surface: {theme["surface"]};
      --color-text: {theme["text"]};
      --color-muted: {theme["muted"]};
      --color-primary: {theme["primary"]};
      --color-primary-strong: {theme["strong"]};
      --color-on-primary: {theme["on_primary"]};
      --color-accent: {theme["accent"]};
      --color-border: {theme["border"]};
      --radius-card: {theme["radius"]};
      --shadow-card: {theme["shadow"]};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      min-height: 100vh; margin: 0; color: var(--color-text);
      font-family: Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
      background: {theme["background"]};
    }}
    button {{ font: inherit; }}
    button:focus-visible {{ outline: 3px solid rgba(31, 157, 98, .35); outline-offset: 3px; }}
    .page {{ width: min(1120px, calc(100% - 40px)); margin: 0 auto; padding: 34px 0 48px; }}
    .topbar {{ display: flex; align-items: center; justify-content: space-between; gap: 20px; }}
    .brand {{ display: flex; align-items: center; gap: 12px; font-weight: 800; letter-spacing: -.02em; }}
    .brand-mark {{ width: 42px; height: 42px; border-radius: 14px; display: grid; place-items: center; color: var(--color-on-primary); background: var(--color-primary); box-shadow: 0 10px 22px color-mix(in srgb, var(--color-primary) 28%, transparent); }}
    .status-pill {{ padding: 8px 12px; border: 1px solid var(--color-border); border-radius: 999px; color: var(--color-muted); background: rgba(255,255,255,.66); font-size: 13px; }}
    main {{ min-height: calc(100vh - 124px); display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); gap: 28px; align-items: center; }}
    .intro small {{ color: var(--color-primary-strong); font-weight: 800; letter-spacing: .12em; }}
    .intro h1 {{ max-width: 680px; margin: 14px 0 18px; font-size: clamp(40px, 6vw, 76px); line-height: .98; letter-spacing: -.055em; }}
    .intro p {{ max-width: 620px; margin: 0; color: var(--color-muted); font-size: 17px; line-height: 1.8; }}
    .features {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 30px; padding: 0; list-style: none; }}
    .features li {{ padding: 10px 13px; border: 1px solid var(--color-border); border-radius: 12px; background: rgba(255,255,255,.7); font-size: 14px; }}
    .timer-card {{ position: relative; padding: 30px; border: 1px solid rgba(255,255,255,.8); border-radius: var(--radius-card); background: var(--color-surface); box-shadow: var(--shadow-card); backdrop-filter: blur(18px); overflow: hidden; }}
    .timer-card::before {{ content: ""; position: absolute; width: 180px; height: 180px; border-radius: 50%; top: -90px; right: -70px; background: rgba(240,68,91,.1); }}
    .timer-heading {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .timer-heading span {{ color: var(--color-muted); font-size: 14px; }}
    .timer-heading strong {{ color: var(--color-primary-strong); }}
    .timer {{ margin: 36px 0 28px; text-align: center; font-variant-numeric: tabular-nums; font-size: clamp(64px, 10vw, 96px); line-height: 1; font-weight: 800; letter-spacing: -.06em; }}
    .progress {{ height: 9px; border-radius: 999px; background: #e7ece8; overflow: hidden; }}
    .progress > span {{ display: block; width: 100%; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--color-primary), #65ca8e); transition: width .25s linear; }}
    .timer-state {{ min-height: 24px; margin: 16px 0 24px; text-align: center; color: var(--color-muted); }}
    .session-stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; margin: 0 0 22px; }}
    .session-stats div {{ padding: 11px 8px; text-align: center; border: 1px solid color-mix(in srgb, var(--color-border) 48%, transparent); border-radius: 12px; background: color-mix(in srgb, var(--color-surface) 82%, white); }}
    .session-stats span {{ display: block; color: var(--color-muted); font-size: 11px; }}
    .session-stats strong {{ display: block; margin-top: 4px; font-size: 14px; }}
    .actions {{ display: grid; grid-template-columns: 1.2fr 1fr 1fr; gap: 10px; }}
    .actions button {{ min-height: 50px; border: 0; border-radius: 14px; cursor: pointer; font-weight: 750; transition: transform .18s ease, background .18s ease; }}
    .actions button:hover {{ transform: translateY(-1px); }}
    .primary {{ color: var(--color-on-primary); background: var(--color-primary); }}
    .primary:hover {{ background: var(--color-primary-strong); }}
    .secondary {{ color: var(--color-text); background: #edf1ee; }}
    .tertiary {{ color: var(--color-text); background: transparent; border: 1px solid var(--color-border) !important; }}
    .notification-control {{ display: block; margin: 14px auto 0; padding: 6px 8px; color: var(--color-primary-strong); background: transparent; border: 0; cursor: pointer; font-size: 12px; text-decoration: underline; text-underline-offset: 3px; }}
    .note {{ margin-top: 16px; color: var(--color-muted); text-align: center; font-size: 12px; line-height: 1.6; }}
    @media (max-width: 820px) {{
      .page {{ width: min(100% - 28px, 620px); padding-top: 22px; }}
      main {{ grid-template-columns: 1fr; gap: 28px; padding-top: 56px; }}
      .intro {{ text-align: center; }} .intro p {{ margin-inline: auto; }} .features {{ justify-content: center; }}
    }}
    @media (max-width: 430px) {{
      .page {{ width: min(100% - 20px, 390px); }}
      .status-pill {{ display: none; }}
      main {{ padding-top: 34px; }}
      .intro h1 {{ font-size: 42px; }} .intro p {{ font-size: 15px; }}
      .timer-card {{ padding: 24px 18px; border-radius: 22px; }}
      .timer {{ font-size: 68px; }} .actions {{ grid-template-columns: 1fr 1fr; }} .actions .primary {{ grid-column: 1 / -1; }} .actions button {{ min-height: 48px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior: auto !important; transition: none !important; }} }}
  </style>
</head>
<body data-product-preview="controlled-html-webapp-v1" data-ui-style="{html.escape(ui_style_key)}">
  <div class="page">
    <header class="topbar">
      <div class="brand"><span class="brand-mark" aria-hidden="true">W</span><span>西瓜时间</span></div>
      <span class="status-pill">{style_name}</span>
    </header>
    <main>
      <section class="intro" aria-labelledby="product-title">
        <small>FOCUS WITH CLARITY</small>
        <h1 id="product-title">{title}</h1>
        <p>{summary}</p>
        <ul class="features"><li>固定 25/5/15 循环</li><li>暂停后继续</li><li>每 4 轮长休息</li><li>本地今日统计</li></ul>
      </section>
      <section class="timer-card" aria-labelledby="timer-label">
        <div class="timer-heading"><span id="timer-label">当前阶段</span><strong id="modeLabel">专注 · 准备开始</strong></div>
        <div class="timer" id="timer" aria-live="off">25:00</div>
        <div class="progress" aria-hidden="true"><span id="progress"></span></div>
        <p class="timer-state" id="timerState" aria-live="polite">准备好后，开始这一轮专注。</p>
        <div class="session-stats" aria-label="本次与今日统计">
          <div><span>完成轮数</span><strong id="roundCount">0 / 4</strong></div>
          <div><span>下一阶段</span><strong id="nextPhase">短休息</strong></div>
          <div><span>今日专注</span><strong id="todayFocus">0 分钟</strong></div>
        </div>
        <div class="actions">
          <button class="primary" id="toggleButton" type="button">开始专注</button>
          <button class="secondary" id="finishButton" type="button">结束本轮</button>
          <button class="tertiary" id="resetButton" type="button">重置本阶段</button>
        </div>
        <button class="notification-control" id="notificationButton" type="button">启用浏览器阶段通知</button>
        <p class="note">专注 25 分钟、短休息 5 分钟；每完成 4 轮专注进入 15 分钟长休息。统计只保存在当前浏览器。</p>
      </section>
    </main>
  </div>
  <script>
    (() => {{
      const config = {config};
      const timer = document.querySelector('#timer');
      const state = document.querySelector('#timerState');
      const mode = document.querySelector('#modeLabel');
      const progress = document.querySelector('#progress');
      const toggle = document.querySelector('#toggleButton');
      const finish = document.querySelector('#finishButton');
      const reset = document.querySelector('#resetButton');
      const notificationButton = document.querySelector('#notificationButton');
      const roundCount = document.querySelector('#roundCount');
      const nextPhase = document.querySelector('#nextPhase');
      const todayFocus = document.querySelector('#todayFocus');
      const durations = {{ focus: config.focusSeconds, shortBreak: config.shortBreakSeconds, longBreak: config.longBreakSeconds }};
      const labels = {{ focus: '专注', shortBreak: '短休息', longBreak: '长休息' }};
      const now = new Date();
      const today = `${{now.getFullYear()}}-${{String(now.getMonth() + 1).padStart(2, '0')}}-${{String(now.getDate()).padStart(2, '0')}}`;
      const storageKey = `watermelon-focus:${{today}}`;
      let saved = {{ rounds: 0, minutes: 0 }};
      try {{ saved = {{ ...saved, ...JSON.parse(localStorage.getItem(storageKey) || '{{}}') }}; }} catch (_error) {{}}
      let phase = Object.hasOwn(labels, saved.phase) ? saved.phase : 'focus';
      let completedRounds = Number(saved.rounds) || 0;
      let todayMinutes = Number(saved.minutes) || 0;
      let targetTime = Number(saved.targetTime) || 0;
      let running = Boolean(saved.running && targetTime > 0);
      const storedRemaining = Number(saved.remaining);
      let remaining = running
        ? Math.max(0, Math.ceil((targetTime - Date.now()) / 1000))
        : Number.isFinite(storedRemaining) && storedRemaining > 0 && storedRemaining <= durations[phase]
          ? storedRemaining
          : durations[phase];
      let intervalId = null;

      function plannedNextPhase() {{
        if (phase !== 'focus') return 'focus';
        return (completedRounds + 1) % config.roundsBeforeLongBreak === 0 ? 'longBreak' : 'shortBreak';
      }}

      function persist() {{
        try {{
          localStorage.setItem(storageKey, JSON.stringify({{
            rounds: completedRounds,
            minutes: todayMinutes,
            phase,
            remaining,
            running,
            targetTime: running ? targetTime : 0,
          }}));
        }} catch (_error) {{}}
      }}

      function render() {{
        const minutes = Math.floor(remaining / 60).toString().padStart(2, '0');
        const seconds = Math.max(0, remaining % 60).toString().padStart(2, '0');
        timer.textContent = `${{minutes}}:${{seconds}}`;
        progress.style.width = `${{Math.max(0, remaining / durations[phase] * 100)}}%`;
        toggle.textContent = running ? '暂停' : remaining < durations[phase] && remaining > 0 ? '继续' : `开始${{labels[phase]}}`;
        mode.textContent = `${{labels[phase]}} · ${{running ? '进行中' : remaining < durations[phase] ? '已暂停' : '准备开始'}}`;
        roundCount.textContent = `${{completedRounds % config.roundsBeforeLongBreak}} / ${{config.roundsBeforeLongBreak}}`;
        nextPhase.textContent = labels[plannedNextPhase()];
        todayFocus.textContent = `${{todayMinutes}} 分钟`;
      }}

      function stopTicker() {{ if (intervalId !== null) window.clearInterval(intervalId); intervalId = null; }}
      function notifyPhase() {{
        try {{
          const context = new (window.AudioContext || window.webkitAudioContext)();
          const oscillator = context.createOscillator(); const gain = context.createGain();
          gain.gain.value = .035; oscillator.frequency.value = 660;
          oscillator.connect(gain); gain.connect(context.destination); oscillator.start(); oscillator.stop(context.currentTime + .16);
        }} catch (_error) {{}}
        if ('Notification' in window && Notification.permission === 'granted') new Notification(`${{labels[phase]}}开始`, {{ body: config.title }});
      }}
      function completePhase() {{
        running = false; stopTicker();
        if (phase === 'focus') {{ completedRounds += 1; todayMinutes += Math.round(config.focusSeconds / 60); phase = completedRounds % config.roundsBeforeLongBreak === 0 ? 'longBreak' : 'shortBreak'; }}
        else {{ phase = 'focus'; }}
        remaining = durations[phase]; persist(); notifyPhase();
        state.textContent = `已切换到${{labels[phase]}}，准备好后点击开始。`; render();
      }}
      function finishCurrentPhase() {{
        const endedPhase = phase;
        running = false; stopTicker();
        if (phase !== 'focus') phase = 'focus';
        remaining = durations[phase]; persist();
        state.textContent = endedPhase === 'focus'
          ? '已结束本轮专注；未完整完成，因此没有计入今日统计。'
          : '已结束休息，返回下一轮专注。';
        render();
      }}
      function tick() {{
        remaining = Math.max(0, Math.ceil((targetTime - Date.now()) / 1000));
        if (remaining === 0) {{ completePhase(); return; }}
        render();
      }}
      function start() {{
        if (running || remaining === 0) return;
        running = true; targetTime = Date.now() + remaining * 1000;
        state.textContent = `${{labels[phase]}}进行中，计时以系统时间校准。`;
        stopTicker(); intervalId = window.setInterval(tick, 250); persist(); render();
      }}
      function pause() {{
        if (!running) return;
        remaining = Math.max(0, Math.ceil((targetTime - Date.now()) / 1000));
        running = false; stopTicker(); persist(); state.textContent = '计时已暂停，可以从当前时间继续。'; render();
      }}
      toggle.addEventListener('click', () => running ? pause() : start());
      finish.addEventListener('click', finishCurrentPhase);
      reset.addEventListener('click', () => {{ running = false; stopTicker(); remaining = durations[phase]; persist(); state.textContent = `已重置当前${{labels[phase]}}阶段。`; render(); }});
      notificationButton.addEventListener('click', async () => {{
        if (!('Notification' in window)) {{ state.textContent = '当前浏览器不支持系统通知，页面提醒和声音仍可使用。'; return; }}
        const permission = await Notification.requestPermission();
        notificationButton.textContent = permission === 'granted' ? '浏览器通知已启用' : '浏览器通知未启用';
        state.textContent = permission === 'granted' ? '阶段结束时将发送浏览器通知。' : '通知未授权，计时、页面提醒和声音不受影响。';
      }});
      document.addEventListener('visibilitychange', () => {{ if (!document.hidden && running) tick(); }});
      if (running && remaining === 0) completePhase();
      else if (running) {{ state.textContent = `已恢复进行中的${{labels[phase]}}，并按真实时间校准。`; intervalId = window.setInterval(tick, 250); render(); }}
      else render();
    }})();
  </script>
</body>
</html>
"""


def _generic_html(prd: PrdContent, ui_style_key: str) -> str:
    title = html.escape(prd.title)
    summary = html.escape(prd.summary)
    theme = UI_STYLES.get(ui_style_key, UI_STYLES["pirsch-paper"])
    features = "".join(f"<li>{html.escape(item)}</li>" for item in prd.features[:6])
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>:root{{--bg:{theme["canvas"]};--surface:{theme["surface"]};--text:{theme["text"]};--muted:{theme["muted"]};--primary:{theme["primary"]};--border:{theme["border"]};--radius:{theme["radius"]};--shadow:{theme["shadow"]}}}*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,"PingFang SC",system-ui,sans-serif;background:{theme["background"]};color:var(--text)}}main{{width:min(100% - 32px,1040px);margin:auto;padding:72px 0}}header{{max-width:720px}}small{{color:var(--primary);font-weight:700}}h1{{font-size:clamp(40px,7vw,72px);line-height:1;letter-spacing:-.05em}}p{{color:var(--muted);font-size:18px;line-height:1.75}}ul{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;padding:0;margin-top:40px;list-style:none}}li{{padding:24px;border:1px solid var(--border);border-radius:var(--radius);background:var(--surface);box-shadow:var(--shadow)}}@media(max-width:640px){{main{{padding:44px 0}}ul{{grid-template-columns:1fr}}}}</style></head>
<body data-product-preview="controlled-html-webapp-v1" data-ui-style="{html.escape(ui_style_key)}"><main><header><small>{html.escape(theme["name"])}</small><h1>{title}</h1><p>{summary}</p></header><ul>{features}</ul></main></body></html>"""


def build_vibe_html_bundle(
    *,
    provider_name: str,
    model: str,
    verification: str,
    project_name: str,
    idea: str,
    prd: PrdContent,
    solution: SolutionContent,
    product_context: dict[str, object],
) -> tuple[CodingBundle, dict[str, Any]]:
    ui_style_key = str(product_context.get("ui_style_key") or "pirsch-paper")
    page = _timer_html(prd, ui_style_key) if _is_timer_product(prd) else _generic_html(prd, ui_style_key)
    manifest = {
        "template": "controlled_html_webapp_v1",
        "project_name": project_name,
        "idea": idea,
        "prd_title": prd.title,
        "solution_title": solution.title,
        "product_context": product_context,
        "ui_style_key": ui_style_key,
        "ui_style": UI_STYLES.get(ui_style_key, UI_STYLES["pirsch-paper"]),
        "frontend_manual": "AI产品Vibe Coding通用前端技术栈手册.md",
        "verification": "generated_not_tested",
    }
    main_py = '''from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Generated HTML product", version="0.1.0")
PAGE_PATH = Path(__file__).resolve().parents[1] / "web" / "index.html"
history_items: list[dict[str, object]] = []


class AnalyzeRequest(BaseModel):
    input: str = Field(min_length=1, max_length=5000)


@app.get("/", response_class=HTMLResponse)
def product_page() -> HTMLResponse:
    return HTMLResponse(PAGE_PATH.read_text(encoding="utf-8"))


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "product": "html_webapp"}


@app.get("/api/v1/product-spec")
def product_spec() -> dict[str, str]:
    return {"entry": "/", "kind": "html", "state_source": "browser"}


@app.post("/api/v1/analyze")
def analyze(body: AnalyzeRequest) -> dict[str, object]:
    result = {
        "summary": "HTML 产品页面已收到本次验收记录。",
        "key_points": [body.input[:160]],
        "next_step": "请在页面中继续操作核心功能并检查状态变化。",
    }
    history_items.insert(0, {"id": len(history_items) + 1, "input": body.input, **result})
    return result


@app.get("/api/v1/history")
def history() -> list[dict[str, object]]:
    return history_items
'''
    test_py = '''from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_html_product_contract() -> None:
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert 'data-product-preview="controlled-html-webapp-v1"' in page.text
'''
    files = [
        GeneratedCodeFile(path="README.md", language="markdown", product_purpose="说明生成页面的范围、启动方式和验收边界。", content=f"# {project_name}\n\n{idea}\n\n这是依据已确认 PRD、方案和前端技术栈手册生成的本地 HTML 产品预览。\n\n```bash\nuv run uvicorn app.main:app --reload\n```\n"),
        GeneratedCodeFile(path="pyproject.toml", language="toml", product_purpose="固定 HTML 预览后端的 Python 运行与测试依赖。", content='[project]\nname = "generated-html-product"\nversion = "0.1.0"\nrequires-python = ">=3.11,<3.12"\ndependencies = ["fastapi>=0.115,<1", "httpx>=0.27,<1", "pydantic>=2.10,<3", "uvicorn[standard]>=0.32,<1"]\n\n[dependency-groups]\ndev = ["pytest>=8.3,<9"]\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'),
        GeneratedCodeFile(path=".gitignore", language="gitignore", product_purpose="避免本地环境和缓存进入生成代码版本。", content=".env\n.venv/\n__pycache__/\n*.pyc\n.pytest_cache/\n"),
        GeneratedCodeFile(path="app/__init__.py", language="python", product_purpose="声明 HTML 产品预览后端包。", content='"""Generated HTML product runtime."""\n'),
        GeneratedCodeFile(path="app/main.py", language="python", product_purpose="提供 HTML 产品页面、健康检查和受控验收接口。", content=main_py),
        GeneratedCodeFile(path="web/index.html", language="html", product_purpose="依据已确认 PRD 生成、可在桌面和移动端操作的产品页面。", content=page),
        GeneratedCodeFile(path="docs/frontend-adaptation.md", language="markdown", product_purpose="记录本项目对通用前端手册的技术适配与偏离。", content=_adaptation_document(prd)),
        GeneratedCodeFile(path="docs/stage-development.md", language="markdown", product_purpose="记录本阶段页面、状态、验收和回退边界。", content=_stage_document(prd)),
        GeneratedCodeFile(path="tests/test_contract.py", language="python", product_purpose="验证真实 HTML 页面入口和健康接口。", content=test_py),
        GeneratedCodeFile(path="product_factory.json", language="json", product_purpose="追溯页面使用的 PRD、方案、手册和产品决策。", content=json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"),
    ]
    usage: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated": True,
        "prompt_version": CODING_PROMPT_VERSION,
    }
    generation = {
        "provider": provider_name,
        "model": model,
        "provider_verification": verification,
        "usage": usage,
    }
    return (
        CodingBundle(
            template="controlled_html_webapp_v1",
            summary=f"已依据确认制品为“{project_name}”生成可运行 HTML 产品页面。",
            files=files,
            run_instructions=["启动 FastAPI 受控预览", "打开根路径体验 HTML 页面", "完成桌面与移动端浏览器验收"],
            generation=generation,
        ),
        usage,
    )
