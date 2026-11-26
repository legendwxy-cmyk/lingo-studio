#!/usr/bin/env python3
"""
Lingo Onboarding Tutorial Film Generator — Direction A (Warm Tactile Studio)
Reads exact measured timeline.json + base64-embeds all real 2x Lingo UI screenshots
and generates video-guide/lingo-guide.html with deterministic window.__seek(t)
plus built-in interactive HTML audio playback mode.
"""
import base64
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
TIMELINE = json.loads((ROOT / "timeline.json").read_text(encoding="utf-8"))


def b64(name: str) -> str:
    return "data:image/png;base64," + base64.b64encode((ASSETS / name).read_bytes()).decode("ascii")


IMG = {
    "logo": b64("lingo-logo.png"),
    "icon": b64("lingo-icon.png"),
    "env": b64("desktop_env_ready.png"),
    "overview": b64("desktop_overview_running.png"),
    "web": b64("web_machine_citrus.png"),
    "library": b64("web_library_upload.png"),
    "ipad": b64("web_ipad_landscape.png"),
}

HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=1920, initial-scale=1" />
<title>Lingo 零基础全流程使用介绍视频（实体精听机工作台）</title>
<style>
  :root {
    --desk-bg: #EFE6D8;
    --desk-light: #F7F1E7;
    --card-bg: #FFFDF8;
    --card-border: #E5D9C7;
    --ink: #1E1730;
    --muted: #5F544B;
    --citrus: #FF7A2D;
    --caramel: #B84209;
    --mint: #0E8A5F;
    --mint-soft: #DCFCE7;
    --sys-blue: #0052B4;
    --sys-blue-light: #007AFF;
    --shadow-soft: 0 26px 68px rgba(48, 32, 18, 0.16), 0 6px 18px rgba(48, 32, 18, 0.08);
    --shadow-deep: 0 34px 86px rgba(34, 22, 14, 0.22), 0 8px 22px rgba(34, 22, 14, 0.10);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 100%;
    height: 100%;
    background: #1A1512;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: "Noto Sans CJK SC", "PingFang SC", -apple-system, BlinkMacSystemFont, sans-serif;
    -webkit-font-smoothing: antialiased;
    user-select: none;
  }
  #viewport-wrap {
    width: 1920px;
    height: 1080px;
    position: relative;
    overflow: hidden;
    transform-origin: center center;
    background:
      radial-gradient(ellipse 78% 70% at 24% 18%, rgba(255, 250, 240, 0.92), transparent 65%),
      radial-gradient(ellipse 65% 60% at 82% 86%, rgba(255, 194, 142, 0.22), transparent 64%),
      linear-gradient(155deg, #F6EFE3 0%, #EFE5D5 52%, #E8DCC8 100%);
  }
  /* Subtle warm studio desk texture rings */
  .desk-glow {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
      radial-gradient(circle at 50% 48%, rgba(255, 255, 255, 0.42) 0%, transparent 56%),
      radial-gradient(circle at 50% 50%, transparent 62%, rgba(84, 58, 34, 0.09) 100%);
  }

  /* Persistent Top Bar */
  #top-bar {
    position: absolute;
    top: 26px;
    left: 48px;
    right: 48px;
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    z-index: 60;
    pointer-events: none;
  }
  .step-tray {
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(255, 253, 248, 0.90);
    border: 1.5px solid rgba(226, 211, 191, 0.95);
    border-radius: 999px;
    padding: 7px 10px;
    box-shadow: 0 10px 26px rgba(48, 32, 18, 0.08);
  }
  .step-pill {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 8px 16px;
    border-radius: 999px;
    font-size: 17px;
    font-weight: 700;
    color: #7A6E63;
    background: transparent;
  }
  .step-pill .snum {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 13px;
    font-weight: 800;
    background: #EDE3D4;
    color: #6B5F55;
  }
  .step-pill.done {
    color: #165B43;
  }
  .step-pill.done .snum {
    background: var(--mint);
    color: #FFFFFF;
  }
  .step-pill.active {
    background: var(--caramel);
    color: #FFFFFF;
    box-shadow: 0 6px 16px rgba(184, 66, 9, 0.28);
  }
  .step-pill.active .snum {
    background: rgba(255, 255, 255, 0.24);
    color: #FFFFFF;
  }
  #top-logo {
    height: 50px;
    width: auto;
    filter: drop-shadow(0 6px 14px rgba(48, 32, 18, 0.14));
  }

  /* Camera Rig — continuous zoom/pan around center stage */
  #camera-rig {
    position: absolute;
    inset: 0;
    transform-origin: 960px 510px;
    will-change: transform;
  }

  /* Common Layer Wrapper */
  .scene-layer {
    position: absolute;
    inset: 0;
    pointer-events: none;
    opacity: 0;
    will-change: transform, opacity;
  }

  /* ==================== S01: INTRO + DMG INSTALL ==================== */
  #intro-hero {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding-bottom: 50px;
  }
  .intro-halo {
    position: absolute;
    width: 680px;
    height: 680px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(255, 138, 66, 0.22) 0%, rgba(255, 198, 128, 0.08) 48%, transparent 72%);
    z-index: 0;
  }
  .intro-logo {
    width: 420px;
    height: auto;
    z-index: 1;
    filter: drop-shadow(0 22px 38px rgba(68, 34, 12, 0.20));
    margin-bottom: 24px;
  }
  .intro-title {
    z-index: 1;
    font-size: 62px;
    font-weight: 900;
    color: var(--ink);
    letter-spacing: 0.02em;
    margin-bottom: 20px;
  }
  .intro-pills {
    z-index: 1;
    display: flex;
    gap: 14px;
  }
  .intro-pill {
    background: var(--card-bg);
    border: 1.5px solid var(--card-border);
    color: var(--ink);
    font-size: 21px;
    font-weight: 700;
    padding: 11px 22px;
    border-radius: 999px;
    box-shadow: 0 8px 20px rgba(48, 32, 18, 0.07);
  }
  .intro-pill.hi {
    background: var(--caramel);
    border-color: var(--caramel);
    color: #FFFFFF;
  }

  /* macOS DMG Window */
  #dmg-win {
    position: absolute;
    left: 440px;
    top: 196px;
    width: 1040px;
    height: 610px;
    background: var(--card-bg);
    border: 2px solid #E3D6C3;
    border-radius: 26px;
    box-shadow: var(--shadow-deep);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .mac-titlebar {
    height: 54px;
    background: linear-gradient(180deg, #FBF6EE 0%, #F2E9DB 100%);
    border-bottom: 1.5px solid #E5D9C7;
    padding: 0 22px;
    display: flex;
    align-items: center;
    gap: 10px;
    flex: none;
  }
  .tl { width: 14px; height: 14px; border-radius: 50%; }
  .tl.r { background: #FF5F56; border: 1px solid #E0443E; }
  .tl.y { background: #FFBD2E; border: 1px solid #DEA123; }
  .tl.g { background: #27C93F; border: 1px solid #1AAB29; }
  .mac-title {
    margin-left: 14px;
    font-size: 19px;
    font-weight: 800;
    color: var(--ink);
  }
  .dmg-body {
    flex: 1;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-around;
    padding: 0 90px;
    background: radial-gradient(circle at 50% 45%, #FFFDF9 0%, #F8F1E6 100%);
  }
  .dmg-slot {
    width: 240px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 18px;
    position: relative;
  }
  .dmg-app-icon {
    width: 176px;
    height: 176px;
    filter: drop-shadow(0 16px 26px rgba(48, 32, 18, 0.22));
  }
  .dmg-label {
    font-size: 24px;
    font-weight: 800;
    color: var(--ink);
    background: rgba(255, 255, 255, 0.85);
    padding: 6px 18px;
    border-radius: 999px;
    border: 1px solid #E7DCCB;
  }
  .dmg-arrow-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }
  .dmg-hint-pill {
    background: #FFF3E8;
    border: 1.5px solid #F7B788;
    color: var(--caramel);
    font-size: 19px;
    font-weight: 800;
    padding: 8px 18px;
    border-radius: 999px;
  }
  #dmg-drag-ghost {
    position: absolute;
    width: 164px;
    height: 164px;
    left: 204px;
    top: 158px;
    opacity: 0;
    filter: drop-shadow(0 24px 36px rgba(48, 32, 18, 0.34));
    z-index: 12;
  }
  #dmg-done-badge {
    position: absolute;
    bottom: 42px;
    left: 50%;
    transform: translateX(-50%) scale(0.8);
    background: var(--mint);
    color: #FFFFFF;
    font-size: 23px;
    font-weight: 800;
    padding: 13px 28px;
    border-radius: 999px;
    box-shadow: 0 14px 30px rgba(14, 138, 95, 0.30);
    opacity: 0;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  /* ==================== S02: macOS PRIVACY & SECURITY ==================== */
  #mac-settings-win {
    position: absolute;
    left: 360px;
    top: 170px;
    width: 1200px;
    height: 676px;
    background: #F6F5F3;
    border: 2px solid #DFD5C5;
    border-radius: 24px;
    box-shadow: var(--shadow-deep);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .ms-grid {
    flex: 1;
    display: grid;
    grid-template-columns: 296px 1fr;
    min-height: 0;
  }
  .ms-sidebar {
    background: #EFECE6;
    border-right: 1.5px solid #DFD7C9;
    padding: 22px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .ms-nav {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 16px;
    border-radius: 12px;
    font-size: 20px;
    font-weight: 700;
    color: #3A342F;
  }
  .ms-nav-ico {
    width: 30px;
    height: 30px;
    border-radius: 8px;
    display: grid;
    place-items: center;
    font-size: 16px;
    color: #FFFFFF;
    font-weight: 800;
    flex: none;
  }
  .ms-nav.active {
    background: var(--sys-blue);
    color: #FFFFFF;
    box-shadow: 0 6px 16px rgba(0, 82, 180, 0.24);
  }
  .ms-content {
    padding: 28px 34px;
    display: flex;
    flex-direction: column;
    gap: 18px;
    background: #FBF9F6;
    position: relative;
  }
  .ms-sec-title {
    font-size: 24px;
    font-weight: 900;
    color: var(--ink);
  }
  .ms-allow-card {
    background: #FFFFFF;
    border: 2.5px solid var(--citrus);
    border-radius: 18px;
    padding: 22px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    box-shadow: 0 12px 28px rgba(255, 122, 45, 0.14);
    position: relative;
  }
  .ms-allow-card.unlocked {
    border-color: var(--mint);
    background: #F2FDF7;
    box-shadow: 0 12px 28px rgba(14, 138, 95, 0.16);
  }
  .ms-allow-left {
    display: flex;
    align-items: center;
    gap: 18px;
  }
  .ms-allow-left img {
    width: 64px;
    height: 64px;
    border-radius: 14px;
  }
  .ms-allow-h {
    font-size: 22px;
    font-weight: 900;
    color: var(--ink);
    margin-bottom: 5px;
  }
  .ms-allow-p {
    font-size: 17px;
    color: #5E544C;
    font-weight: 600;
  }
  #btn-open-anyway {
    background: var(--caramel);
    color: #FFFFFF;
    font-size: 21px;
    font-weight: 800;
    padding: 14px 28px;
    border-radius: 14px;
    box-shadow: 0 10px 22px rgba(184, 66, 9, 0.28);
    white-space: nowrap;
    flex: none;
  }
  #btn-open-anyway.done {
    background: var(--mint);
    box-shadow: 0 10px 22px rgba(14, 138, 95, 0.25);
  }
  .ms-perm-group {
    background: #FFFFFF;
    border: 1.5px solid #E5DDD0;
    border-radius: 18px;
    overflow: hidden;
  }
  .ms-perm-row {
    padding: 20px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #EFE8DC;
  }
  .ms-perm-row:last-child { border-bottom: none; }
  .ms-perm-row.hl-row {
    background: #FFF9F2;
  }
  .ms-perm-txt h4 {
    font-size: 21px;
    font-weight: 800;
    color: var(--ink);
    margin-bottom: 4px;
  }
  .ms-perm-txt p {
    font-size: 16.5px;
    color: #63584E;
    font-weight: 600;
  }
  .mac-switch {
    width: 72px;
    height: 40px;
    border-radius: 999px;
    background: #D6CEC2;
    padding: 4px;
    position: relative;
    flex: none;
  }
  .mac-switch.on {
    background: var(--mint);
  }
  .mac-switch-knob {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #FFFFFF;
    box-shadow: 0 3px 8px rgba(0,0,0,0.22);
    transform: translateX(0px);
  }
  .mac-switch.on .mac-switch-knob {
    transform: translateX(32px);
  }
  #mac-rightclick-tip {
    background: #1E1730;
    color: #FFFDF8;
    font-size: 19px;
    font-weight: 700;
    padding: 13px 22px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    align-self: flex-start;
    box-shadow: 0 12px 26px rgba(30, 23, 48, 0.22);
    opacity: 0;
  }
  #mac-rightclick-tip .tag {
    background: var(--citrus);
    color: #1E1730;
    font-weight: 900;
    font-size: 15px;
    padding: 3px 10px;
    border-radius: 8px;
  }
  /* Floating dark badge above Open Anyway */
  #badge-open-anyway {
    position: absolute;
    right: 26px;
    top: -54px;
    background: #1E1730;
    color: #FFFFFF;
    font-size: 19px;
    font-weight: 800;
    padding: 10px 20px;
    border-radius: 999px;
    box-shadow: 0 12px 24px rgba(30, 23, 48, 0.28);
    opacity: 0;
  }
  #badge-open-anyway span { color: #FFAB6E; }

  /* macOS Gatekeeper Block Alert Modal */
  #gk-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(38, 28, 20, 0.28);
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    z-index: 25;
  }
  #gk-modal {
    width: 520px;
    background: #FFFDF9;
    border: 2px solid #E2D5C3;
    border-radius: 26px;
    padding: 34px 36px 28px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    box-shadow: 0 32px 72px rgba(24, 16, 10, 0.32);
  }
  #gk-modal img { width: 92px; height: 92px; margin-bottom: 16px; }
  #gk-modal h3 { font-size: 26px; font-weight: 900; color: var(--ink); margin-bottom: 10px; }
  #gk-modal p { font-size: 18px; line-height: 1.55; color: #5C5249; margin-bottom: 24px; font-weight: 600; }
  .gk-btns { display: flex; gap: 14px; width: 100%; }
  .gk-btn {
    flex: 1;
    padding: 13px 0;
    border-radius: 13px;
    font-size: 19px;
    font-weight: 800;
    background: #EDE6DA;
    color: #4D443D;
  }
  .gk-btn.primary {
    background: var(--sys-blue);
    color: #FFFFFF;
    box-shadow: 0 8px 18px rgba(0, 82, 180, 0.28);
  }

  /* ==================== S03: NATIVE SETUP HUD ==================== */
  #native-hud {
    position: absolute;
    left: 530px;
    top: 315px;
    width: 860px;
    background: var(--card-bg);
    border: 2px solid #E3D4BE;
    border-radius: 28px;
    padding: 36px 40px;
    box-shadow: var(--shadow-deep);
    display: flex;
    flex-direction: column;
    gap: 22px;
  }
  .hud-head {
    display: flex;
    align-items: center;
    gap: 22px;
  }
  .hud-head img { width: 86px; height: 86px; filter: drop-shadow(0 10px 18px rgba(48,32,18,0.18)); }
  .hud-head h3 { font-size: 28px; font-weight: 900; color: var(--ink); margin-bottom: 6px; }
  .hud-head p { font-size: 19px; color: #5E534A; font-weight: 600; }
  .hud-bar-track {
    width: 100%;
    height: 18px;
    background: #EDE3D4;
    border-radius: 999px;
    overflow: hidden;
  }
  #hud-bar-fill {
    height: 100%;
    width: 35%;
    border-radius: 999px;
    background: linear-gradient(90deg, #FF7A2D 0%, #FFB057 100%);
  }
  .hud-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  #hud-step-txt { font-size: 19px; font-weight: 800; color: var(--caramel); }
  .hud-no-term {
    background: var(--mint-soft);
    color: #14532D;
    border: 1.5px solid #86EFAC;
    font-size: 17px;
    font-weight: 800;
    padding: 8px 18px;
    border-radius: 999px;
    white-space: nowrap;
    flex: none;
  }

  /* ==================== S03 & S04: REAL DESKTOP CONTROL CENTER ==================== */
  #console-win {
    position: absolute;
    left: 444px;
    top: 148px;
    width: 1032px;
    height: 700px;
    border-radius: 22px;
    box-shadow: var(--shadow-deep);
    overflow: hidden;
    background: #FF7A2D;
    border: 2.5px solid #DFCBB0;
  }
  #console-win img.screen {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: fill;
    display: block;
  }
  /* Crisp spotlight overlay boxes positioned in exact % matching measured grid! */
  .spot-box {
    position: absolute;
    border: 4px solid var(--citrus);
    border-radius: 16px;
    box-shadow: 0 0 0 5px rgba(255, 122, 45, 0.24), 0 12px 30px rgba(184, 66, 9, 0.25);
    opacity: 0;
    pointer-events: none;
  }
  .spot-box.green {
    border-color: var(--mint);
    box-shadow: 0 0 0 5px rgba(14, 138, 95, 0.24), 0 12px 28px rgba(14, 138, 95, 0.22);
  }
  .float-callout {
    position: absolute;
    background: #1E1730;
    color: #FFFDF8;
    font-size: 20px;
    font-weight: 800;
    padding: 12px 22px;
    border-radius: 14px;
    box-shadow: 0 14px 32px rgba(30, 23, 48, 0.30);
    white-space: nowrap;
    opacity: 0;
    z-index: 30;
  }
  .float-callout .accent { color: #FFAD70; }
  .float-callout.caramel {
    background: var(--caramel);
    color: #FFFFFF;
    box-shadow: 0 14px 32px rgba(184, 66, 9, 0.34);
  }
  .float-callout.mint {
    background: var(--mint);
    color: #FFFFFF;
    box-shadow: 0 14px 32px rgba(14, 138, 95, 0.34);
  }

  /* ==================== S05: MAC BROWSER LEARNING MACHINE ==================== */
  #browser-win {
    position: absolute;
    left: 400px;
    top: 130px;
    width: 1120px;
    height: 748px;
    background: #FBF7F0;
    border: 2px solid #DFD2BE;
    border-radius: 22px;
    box-shadow: var(--shadow-deep);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .browser-chrome {
    height: 48px;
    background: linear-gradient(180deg, #FBF6EE 0%, #F0E6D6 100%);
    border-bottom: 1.5px solid #E3D6C3;
    padding: 0 18px;
    display: flex;
    align-items: center;
    gap: 10px;
    flex: none;
  }
  .url-bar {
    margin: 0 auto;
    width: 440px;
    height: 30px;
    background: #FFFFFF;
    border: 1px solid #DFD3C2;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-size: 15px;
    font-weight: 700;
    color: #3D342E;
  }
  .url-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--mint); }
  .browser-viewport {
    position: relative;
    width: 1120px;
    height: 700px;
    flex: none;
    overflow: hidden;
  }
  .browser-viewport img.screen {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: fill;
  }
  /* Floating drag file card over upload dropzone */
  #drag-video-chip {
    position: absolute;
    left: 205px;
    top: 185px;
    background: #1E1730;
    color: #FFFFFF;
    padding: 12px 20px;
    border-radius: 14px;
    font-size: 18px;
    font-weight: 800;
    box-shadow: 0 16px 32px rgba(30,23,48,0.34);
    display: flex;
    align-items: center;
    gap: 10px;
    opacity: 0;
    z-index: 20;
  }
  /* Live animated audio waveform bars beside Shadowing button */
  #shadow-wave {
    position: absolute;
    left: 162px;
    top: 392px;
    background: #1E1730;
    color: #FFFFFF;
    padding: 10px 18px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    gap: 10px;
    box-shadow: 0 12px 26px rgba(30, 23, 48, 0.34);
    opacity: 0;
    z-index: 22;
  }
  .w-bars { display: flex; align-items: center; gap: 4px; height: 22px; }
  .w-bar { width: 4px; border-radius: 3px; background: #34D399; height: 10px; }
  #shadow-wave span { font-size: 16px; font-weight: 800; }

  /* ==================== S06: DUAL DEVICE MAC + IPAD LAN ==================== */
  #dual-wrap {
    position: absolute;
    inset: 0;
  }
  #dual-mac {
    position: absolute;
    left: 112px;
    top: 244px;
    width: 750px;
    background: #231D2B;
    padding: 14px 14px 16px;
    border-radius: 22px;
    box-shadow: var(--shadow-deep);
    border: 2px solid #3C3348;
  }
  .dev-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 8px 10px;
    font-size: 15px;
    font-weight: 800;
    color: #EFE6D8;
  }
  .dev-tag {
    background: var(--mint);
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 800;
    padding: 3px 11px;
    border-radius: 999px;
  }
  .dual-mac-screen {
    position: relative;
    width: 722px;
    height: 490px;
    border-radius: 12px;
    overflow: hidden;
  }
  .dual-mac-screen img { width: 100%; height: 100%; display: block; }

  #dual-ipad {
    position: absolute;
    left: 1034px;
    top: 202px;
    width: 774px;
    background: #1B1724;
    padding: 16px;
    border-radius: 30px;
    box-shadow: var(--shadow-deep);
    border: 2.5px solid #393148;
  }
  .ipad-safari-bar {
    height: 42px;
    background: #2A2436;
    border-radius: 14px 14px 0 0;
    padding: 0 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  #ipad-addr-pill {
    flex: 1;
    height: 30px;
    background: #16121E;
    border: 1.5px solid #514765;
    border-radius: 999px;
    padding: 0 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15.5px;
    font-weight: 800;
    color: #FFFDF8;
    font-family: "Noto Sans Mono CJK SC", ui-monospace, monospace;
  }
  .ipad-screen-box {
    position: relative;
    width: 742px;
    height: 556px;
    border-radius: 0 0 16px 16px;
    overflow: hidden;
    background: #FAF5EC;
  }
  #ipad-placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 14px;
    color: #6B5F55;
    font-size: 20px;
    font-weight: 700;
  }
  #ipad-real-img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: 0;
  }
  /* Wi-Fi Arc & Flying URL Capsule */
  #wifi-arc-svg {
    position: absolute;
    left: 760px;
    top: 104px;
    width: 400px;
    height: 170px;
    z-index: 18;
    overflow: visible;
  }
  #wifi-bridge-pill {
    position: absolute;
    left: 50%;
    top: 118px;
    transform: translateX(-50%);
    background: #FFFDF8;
    border: 2.5px solid var(--caramel);
    color: var(--caramel);
    font-size: 21px;
    font-weight: 900;
    padding: 11px 26px;
    border-radius: 999px;
    box-shadow: 0 14px 30px rgba(184, 66, 9, 0.18);
    z-index: 24;
    opacity: 0;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  #flying-url-pill {
    position: absolute;
    background: var(--caramel);
    color: #FFFFFF;
    font-family: "Noto Sans Mono CJK SC", ui-monospace, monospace;
    font-size: 19px;
    font-weight: 800;
    padding: 10px 20px;
    border-radius: 999px;
    box-shadow: 0 16px 32px rgba(184, 66, 9, 0.38);
    z-index: 35;
    opacity: 0;
    white-space: nowrap;
  }
  #lan-checks {
    position: absolute;
    left: 50%;
    bottom: 150px;
    transform: translateX(-50%);
    display: flex;
    gap: 18px;
    z-index: 25;
  }
  .lan-chk {
    background: rgba(255, 253, 248, 0.96);
    border: 1.5px solid #D8CBB7;
    color: var(--ink);
    font-size: 19px;
    font-weight: 800;
    padding: 11px 22px;
    border-radius: 999px;
    box-shadow: 0 10px 24px rgba(48, 32, 18, 0.12);
    display: flex;
    align-items: center;
    gap: 9px;
    opacity: 0;
  }
  .lan-chk .ok-dot {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--mint);
    color: #FFFFFF;
    font-size: 14px;
    font-weight: 900;
    display: grid;
    place-items: center;
  }

  /* ==================== S07: 4-STEP RECAP & OUTRO ==================== */
  #recap-stage {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding-bottom: 48px;
  }
  .recap-logo {
    width: 310px;
    height: auto;
    filter: drop-shadow(0 18px 34px rgba(68, 34, 12, 0.18));
    margin-bottom: 18px;
  }
  .recap-sub {
    font-size: 40px;
    font-weight: 900;
    color: var(--ink);
    margin-bottom: 42px;
    letter-spacing: 0.03em;
  }
  .recap-grid {
    display: grid;
    grid-template-columns: repeat(4, 386px);
    gap: 24px;
  }
  .recap-card {
    background: var(--card-bg);
    border: 2px solid var(--card-border);
    border-radius: 24px;
    padding: 28px 26px 30px;
    box-shadow: var(--shadow-soft);
    display: flex;
    flex-direction: column;
    gap: 12px;
    opacity: 0;
  }
  .rc-num {
    width: 48px;
    height: 48px;
    border-radius: 14px;
    background: var(--caramel);
    color: #FFFFFF;
    font-size: 22px;
    font-weight: 900;
    display: grid;
    place-items: center;
    box-shadow: 0 8px 18px rgba(184, 66, 9, 0.24);
  }
  .rc-num.green {
    background: var(--mint);
    box-shadow: 0 8px 18px rgba(14, 138, 95, 0.24);
  }
  .recap-card h4 {
    font-size: 27px;
    font-weight: 900;
    color: var(--ink);
  }
  .recap-card p {
    font-size: 19px;
    line-height: 1.55;
    color: var(--muted);
    font-weight: 700;
  }

  /* ==================== ANIMATED MAC CURSOR & CLICK RIPPLE ==================== */
  #cursor-layer {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 75;
  }
  #cursor {
    position: absolute;
    left: 0;
    top: 0;
    width: 44px;
    height: 44px;
    opacity: 0;
    filter: drop-shadow(0 6px 12px rgba(20, 14, 10, 0.34));
    transform-origin: 6px 4px;
  }
  #click-ripple {
    position: absolute;
    left: 0;
    top: 0;
    width: 72px;
    height: 72px;
    margin-left: -36px;
    margin-top: -36px;
    border-radius: 50%;
    border: 4px solid var(--citrus);
    background: rgba(255, 122, 45, 0.20);
    opacity: 0;
  }

  /* ==================== SUBTITLE BAR (B-STATION FRAMELESS) ==================== */
  #subtitle-wrap {
    position: absolute;
    left: 120px;
    right: 120px;
    bottom: 42px;
    height: 62px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 80;
    pointer-events: none;
  }
  #subtitle-text {
    font-size: 38px;
    font-weight: 900;
    color: #1E1730;
    letter-spacing: 0.02em;
    text-align: center;
    line-height: 1.25;
    text-shadow:
      0 0 18px rgba(248, 242, 232, 0.98),
      0 0 8px rgba(255, 253, 248, 0.98),
      0 2px 3px rgba(255, 253, 248, 0.95);
    opacity: 0;
  }
  #subtitle-text .hl { color: var(--caramel); }

  #watermark {
    position: absolute;
    right: 26px;
    bottom: 14px;
    font-size: 13px;
    font-weight: 700;
    color: rgba(30, 23, 48, 0.36);
    letter-spacing: 0.03em;
    z-index: 82;
    pointer-events: none;
  }

  /* Interactive Player HUD (hidden in ?render=1 mode) */
  #player-hud {
    position: fixed;
    left: 50%;
    bottom: 16px;
    transform: translateX(-50%);
    background: rgba(26, 21, 18, 0.88);
    backdrop-filter: blur(12px);
    color: #FFFDF8;
    border-radius: 999px;
    padding: 8px 18px;
    display: flex;
    align-items: center;
    gap: 14px;
    z-index: 200;
    box-shadow: 0 12px 30px rgba(0,0,0,0.35);
    opacity: 0.15;
    transition: opacity 0.2s;
  }
  #player-hud:hover { opacity: 1; }
  body.render-mode #player-hud { display: none !important; }
  #player-hud button {
    background: var(--citrus);
    color: #1E1730;
    border: none;
    border-radius: 999px;
    padding: 6px 16px;
    font-size: 14px;
    font-weight: 800;
    cursor: pointer;
  }
  #player-hud input[type=range] { width: 380px; accent-color: var(--citrus); cursor: pointer; }
  #player-time { font-size: 13px; font-weight: 700; font-family: monospace; min-width: 105px; }
</style>
</head>
<body>
<div id="viewport-wrap">
  <div class="desk-glow"></div>

  <!-- Persistent Top Chrome -->
  <header id="top-bar">
    <div class="step-tray" id="step-tray">
      <div class="step-pill" data-step="1"><span class="snum">1</span>拖拽安装</div>
      <div class="step-pill" data-step="2"><span class="snum">2</span>隐私放行</div>
      <div class="step-pill" data-step="3"><span class="snum">3</span>环境依赖</div>
      <div class="step-pill" data-step="4"><span class="snum">4</span>发布共享</div>
      <div class="step-pill" data-step="5"><span class="snum">5</span>电脑使用</div>
      <div class="step-pill" data-step="6"><span class="snum">6</span>平板访问</div>
    </div>
    <img id="top-logo" src="__IMG_LOGO__" alt="Lingo" />
  </header>

  <!-- Continuous Camera Rig -->
  <div id="camera-rig">

    <!-- ==================== S01: INTRO + DMG ==================== -->
    <section class="scene-layer" id="layer-s01">
      <div id="intro-hero">
        <div class="intro-halo"></div>
        <img class="intro-logo" id="intro-logo-img" src="__IMG_LOGO__" alt="Lingo" />
        <h1 class="intro-title" id="intro-title">零基础全流程上手指南</h1>
        <div class="intro-pills" id="intro-pills">
          <span class="intro-pill hi">拖拽安装</span>
          <span class="intro-pill">Mac 隐私放行</span>
          <span class="intro-pill">依赖自检</span>
          <span class="intro-pill">发布网站</span>
          <span class="intro-pill">电脑与平板精听</span>
        </div>
      </div>

      <div id="dmg-win">
        <div class="mac-titlebar">
          <span class="tl r"></span><span class="tl y"></span><span class="tl g"></span>
          <span class="mac-title">Lingo-macOS.dmg</span>
        </div>
        <div class="dmg-body">
          <div class="dmg-slot" id="dmg-src-slot">
            <img class="dmg-app-icon" src="__IMG_ICON__" alt="Lingo.app" />
            <span class="dmg-label">Lingo.app</span>
          </div>
          <div class="dmg-arrow-wrap">
            <svg width="160" height="54" viewBox="0 0 160 54" fill="none">
              <path d="M10 27 H132" stroke="#B84209" stroke-width="5" stroke-dasharray="10 10" stroke-linecap="round"/>
              <path d="M116 11 L144 27 L116 43" stroke="#B84209" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span class="dmg-hint-pill">拖入右侧即可安装</span>
          </div>
          <div class="dmg-slot" id="dmg-dst-slot">
            <!-- Realistic macOS Applications Folder SVG -->
            <svg class="dmg-app-icon" viewBox="0 0 180 180" fill="none">
              <defs>
                <linearGradient id="fBack" x1="0" y1="20" x2="0" y2="155" gradientUnits="userSpaceOnUse">
                  <stop stop-color="#5EB6FF"/><stop offset="1" stop-color="#2982E3"/>
                </linearGradient>
                <linearGradient id="fFront" x1="0" y1="48" x2="0" y2="160" gradientUnits="userSpaceOnUse">
                  <stop stop-color="#76C6FF"/><stop offset="1" stop-color="#2E8DF0"/>
                </linearGradient>
              </defs>
              <path d="M16 44C16 34 24 26 34 26H68C75 26 81 30 85 36L92 44H146C156 44 164 52 164 62V138C164 148 156 156 146 156H34C24 156 16 148 16 138V44Z" fill="url(#fBack)"/>
              <rect x="16" y="54" width="148" height="102" rx="18" fill="url(#fFront)"/>
              <path d="M90 77L65 130H77L82.5 117H97.5L103 130H115L90 77ZM86 108L90 97L94 108H86Z" fill="rgba(255,255,255,0.88)"/>
            </svg>
            <span class="dmg-label">应用程序</span>
          </div>
          <img id="dmg-drag-ghost" src="__IMG_ICON__" alt="" />
          <div id="dmg-done-badge">✓ 已成功安装到「应用程序」</div>
        </div>
      </div>
    </section>

    <!-- ==================== S02: macOS PRIVACY & SECURITY ==================== -->
    <section class="scene-layer" id="layer-s02">
      <div id="mac-settings-win">
        <div class="mac-titlebar">
          <span class="tl r"></span><span class="tl y"></span><span class="tl g"></span>
          <span class="mac-title">系统设置 — 隐私与安全性</span>
        </div>
        <div class="ms-grid">
          <aside class="ms-sidebar">
            <div class="ms-nav"><span class="ms-nav-ico" style="background:#8E8E93">⚙</span>通用</div>
            <div class="ms-nav"><span class="ms-nav-ico" style="background:#34C759">▦</span>桌面与程序坞</div>
            <div class="ms-nav active" id="nav-privacy"><span class="ms-nav-ico" style="background:#1A73E8">🛡</span>隐私与安全性</div>
            <div class="ms-nav"><span class="ms-nav-ico" style="background:#FF9500">🎙</span>麦克风</div>
            <div class="ms-nav"><span class="ms-nav-ico" style="background:#007AFF">📡</span>本地网络</div>
          </aside>
          <div class="ms-content">
            <div class="ms-sec-title">安全性</div>
            <div class="ms-allow-card" id="ms-allow-card">
              <div id="badge-open-anyway">只需点这里：<span>仍要打开</span></div>
              <div class="ms-allow-left">
                <img src="__IMG_ICON__" alt="Lingo" />
                <div>
                  <div class="ms-allow-h" id="ms-allow-h">已阻止使用「Lingo」，因为无法验证开发者</div>
                  <div class="ms-allow-p" id="ms-allow-p">点击右侧按钮并输入 Mac 开机密码，即可永久放行</div>
                </div>
              </div>
              <div id="btn-open-anyway">仍要打开</div>
            </div>

            <div class="ms-sec-title" style="margin-top:4px">常用权限开关</div>
            <div class="ms-perm-group">
              <div class="ms-perm-row" id="row-localnet">
                <div class="ms-perm-txt">
                  <h4>本地网络（允许同 Wi-Fi 设备访问 Lingo）</h4>
                  <p>开启后，同一 Wi-Fi 下的 iPad 平板和手机才能连接电脑</p>
                </div>
                <div class="mac-switch" id="sw-localnet"><div class="mac-switch-knob"></div></div>
              </div>
              <div class="ms-perm-row" id="row-mic">
                <div class="ms-perm-txt">
                  <h4>麦克风（允许网页端录音做跟读对比）</h4>
                  <p>开启后，可在学习机内边听原文边连续跟读打分</p>
                </div>
                <div class="mac-switch" id="sw-mic"><div class="mac-switch-knob"></div></div>
              </div>
            </div>

            <div id="mac-rightclick-tip">
              <span class="tag">快捷备选</span>
              <span>若找不到按钮，在「应用程序」右键点 Lingo 选「打开」即可放行</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Initial Gatekeeper Warning Modal -->
      <div id="gk-backdrop">
        <div id="gk-modal">
          <img src="__IMG_ICON__" alt="Lingo" />
          <h3>无法打开「Lingo」</h3>
          <p>Apple 无法验证「Lingo」是否包含可能危害 Mac 的恶意软件。请先点「完成」，再到系统设置放行。</p>
          <div class="gk-btns">
            <div class="gk-btn">移到废纸篓</div>
            <div class="gk-btn primary" id="gk-btn-ok">完成</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== S03: NATIVE SETUP HUD ==================== -->
    <section class="scene-layer" id="layer-s03-hud">
      <div id="native-hud">
        <div class="hud-head">
          <img src="__IMG_ICON__" alt="Lingo" />
          <div>
            <h3>正在自动准备 Lingo 运行环境</h3>
            <p>首次启动约需数秒，请稍候，完成后将自动打开控制台</p>
          </div>
        </div>
        <div class="hud-bar-track"><div id="hud-bar-fill"></div></div>
        <div class="hud-foot">
          <span id="hud-step-txt">正在检测独立 Python 与音频引擎...</span>
          <span class="hud-no-term">✓ 全程原生浮窗，免开黑色命令行</span>
        </div>
      </div>
    </section>

    <!-- ==================== S03 & S04: REAL DESKTOP CONTROL CENTER ==================== -->
    <section class="scene-layer" id="layer-console">
      <div id="console-win">
        <img class="screen" id="img-console-env" src="__IMG_ENV__" alt="环境与依赖" />
        <img class="screen" id="img-console-overview" src="__IMG_OVERVIEW__" alt="服务总览" style="opacity:0" />

        <!-- Pixel-accurate overlays measured from 10% grid -->
        <!-- S03 Environment highlights -->
        <div class="spot-box green" id="spot-env-list" style="left:4.2%;top:50.9%;width:91.6%;height:43.8%;"></div>
        <div class="spot-box" id="spot-env-repair" style="left:4.9%;top:34.2%;width:13.2%;height:7.2%;"></div>
        <div class="float-callout mint" id="call-env-ok" style="right:42px;top:292px;">✓ 五项全部亮绿「已就绪」即可发布</div>
        <div class="float-callout caramel" id="call-env-repair" style="left:202px;top:236px;">有缺失点这里：内置国内镜像自动补齐</div>

        <!-- S04 Overview highlights -->
        <div class="spot-box" id="spot-pub-port" style="left:4.6%;top:69.6%;width:36.2%;height:7.6%;"></div>
        <div class="spot-box" id="spot-pub-lan" style="left:25.8%;top:77.2%;width:30.2%;height:5.8%;"></div>
        <div class="spot-box" id="spot-pub-pass" style="left:4.6%;top:83.2%;width:89.5%;height:6.4%;"></div>
        <div class="spot-box green" id="spot-pub-onair" style="left:4.5%;top:25.2%;width:91.2%;height:24.8%;"></div>
        <div class="spot-box" id="spot-pub-openbtn" style="left:15.2%;top:35.0%;width:14.6%;height:6.5%;"></div>

        <div class="float-callout" id="call-pub-port" style="left:432px;top:484px;">默认端口 <span class="accent">8000</span>，新手不用改动</div>
        <div class="float-callout caramel" id="call-pub-lan" style="left:584px;top:532px;">重点：拨开「局域网共享」开关</div>
        <div class="float-callout" id="call-pub-pass" style="left:460px;top:528px;">家里自用留空免密，共用网络可设口令</div>
        <div class="float-callout mint" id="call-pub-onair" style="right:36px;top:108px;">✓ 8000 运行中 + 局域网网址亮起 = 发布成功</div>
      </div>
    </section>

    <!-- ==================== S05: MAC BROWSER LEARNING MACHINE ==================== -->
    <section class="scene-layer" id="layer-browser">
      <div id="browser-win">
        <div class="browser-chrome">
          <span class="tl r"></span><span class="tl y"></span><span class="tl g"></span>
          <div class="url-bar"><span class="url-dot"></span><span>http://127.0.0.1:8000</span></div>
        </div>
        <div class="browser-viewport">
          <img class="screen" id="img-web-machine" src="__IMG_WEB__" alt="Lingo 学习机" />
          <img class="screen" id="img-web-library" src="__IMG_LIBRARY__" alt="Lingo 资料库" style="opacity:0" />

          <!-- Upload dropzone highlight & floating file -->
          <div class="spot-box" id="spot-web-upload" style="left:3.4%;top:15.6%;width:49.4%;height:30.8%;"></div>
          <div class="spot-box green" id="spot-web-5steps" style="left:3.2%;top:52.4%;width:93.6%;height:11.6%;"></div>
          <div id="drag-video-chip"><svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="3" y="5" width="18" height="14" rx="3" stroke="#FFAD70" stroke-width="2.2"/><polygon points="10,9 16,12 10,15" fill="#FFAD70"/></svg><span>TED_English_Talk.mp4</span></div>
          <div class="float-callout caramel" id="call-web-upload" style="left:602px;top:172px;">拖入英语视频/音频，5 步全自动拆解</div>

          <!-- Shadowing & Deck highlight -->
          <div class="spot-box green" id="spot-web-shadow" style="left:16.0%;top:64.8%;width:32.8%;height:26.0%;"></div>
          <div id="shadow-wave">
            <div class="w-bars" id="w-bars">
              <div class="w-bar"></div><div class="w-bar"></div><div class="w-bar"></div><div class="w-bar"></div><div class="w-bar"></div>
            </div>
            <span>边播原文边连续跟读，自动逐句保存</span>
          </div>

          <!-- Top-right 3D theme switcher highlight -->
          <div class="spot-box" id="spot-web-skins" style="left:74.4%;top:1.2%;width:7.8%;height:5.6%;border-radius:999px;"></div>
          <div class="float-callout" id="call-web-skins" style="right:36px;top:62px;">一键切换 <span class="accent">三套玩味 3D 皮肤</span></div>
        </div>
      </div>
    </section>

    <!-- ==================== S06: DUAL DEVICE MAC + IPAD ==================== -->
    <section class="scene-layer" id="layer-dual">
      <div id="dual-wrap">
        <div id="wifi-bridge-pill"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M2.5 9.2C7.8 4.4 16.2 4.4 21.5 9.2" stroke="#B84209" stroke-width="2.4" stroke-linecap="round"/><path d="M6.2 13C9.5 10.1 14.5 10.1 17.8 13" stroke="#B84209" stroke-width="2.4" stroke-linecap="round"/><path d="M9.8 16.6C11.1 15.5 12.9 15.5 14.2 16.6" stroke="#B84209" stroke-width="2.4" stroke-linecap="round"/><circle cx="12" cy="19.6" r="1.6" fill="#B84209"/></svg><span>同一 Wi-Fi 无线直连（免装 App）</span></div>

        <svg id="wifi-arc-svg" viewBox="0 0 400 190" fill="none">
          <path id="wifi-arc-path" d="M 18 158 Q 200 22 368 118" stroke="#B84209" stroke-width="5" stroke-dasharray="12 10" stroke-linecap="round" fill="none" />
        </svg>

        <div id="dual-mac">
          <div class="dev-header">
            <span>Mac 电脑 — Lingo 桌面控制台</span>
            <span class="dev-tag">服务运行中 :8000</span>
          </div>
          <div class="dual-mac-screen">
            <img src="__IMG_OVERVIEW__" alt="Mac Lingo 控制台" />
            <div class="spot-box" id="spot-dual-url" style="left:4.5%;top:42.4%;width:90.5%;height:6.4%;border-width:3px;"></div>
          </div>
        </div>

        <div id="dual-ipad">
          <div class="ipad-safari-bar">
            <span style="color:#A89EB8;font-size:14px;font-weight:800">iPad / 平板浏览器</span>
            <div id="ipad-addr-pill"><span id="ipad-typed-text">在地址栏输入局域网网址...</span></div>
            <span class="dev-tag" id="ipad-conn-tag" style="opacity:0">已直连</span>
          </div>
          <div class="ipad-screen-box">
            <div id="ipad-placeholder">
              <img src="__IMG_LOGO__" style="width:210px;opacity:0.45" alt="" />
              <span>等待输入电脑控制台显示的局域网地址</span>
            </div>
            <img id="ipad-real-img" src="__IMG_IPAD__" alt="iPad Lingo 学习机" />
          </div>
        </div>

        <div id="flying-url-pill">http://192.168.1.28:8000</div>

        <div id="lan-checks">
          <div class="lan-chk" id="lchk-1"><span class="ok-dot">✓</span>Mac 与平板连同一个 Wi-Fi</div>
          <div class="lan-chk" id="lchk-2"><span class="ok-dot">✓</span>电脑保持 Lingo 运行中</div>
          <div class="lan-chk" id="lchk-3"><span class="ok-dot">✓</span>手机用同样网址也可直接访问</div>
        </div>
      </div>
    </section>

    <!-- ==================== S07: 4-STEP RECAP & OUTRO ==================== -->
    <section class="scene-layer" id="layer-recap">
      <div id="recap-stage">
        <img class="recap-logo" id="recap-logo" src="__IMG_LOGO__" alt="Lingo" />
        <div class="recap-sub" id="recap-sub">四步速记，轻松上手</div>
        <div class="recap-grid">
          <div class="recap-card" id="rc-1">
            <div class="rc-num">01</div>
            <h4>拖入安装</h4>
            <p>打开 Lingo-macOS.dmg，将图标拖进「应用程序」即可。</p>
          </div>
          <div class="recap-card" id="rc-2">
            <div class="rc-num">02</div>
            <h4>隐私放行</h4>
            <p>系统设置点「仍要打开」，开启「本地网络」与「麦克风」。</p>
          </div>
          <div class="recap-card" id="rc-3">
            <div class="rc-num">03</div>
            <h4>一键发布</h4>
            <p>确认依赖 5 项全绿，拨开「局域网共享」启动 8000 服务。</p>
          </div>
          <div class="recap-card" id="rc-4">
            <div class="rc-num green">04</div>
            <h4>双端精听</h4>
            <p>电脑一键直达浏览器，同 Wi-Fi 平板输网址免装 App 同步学。</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Animated macOS Cursor & Ripple (inside camera rig so it zooms faithfully with UI!) -->
    <div id="cursor-layer">
      <div id="click-ripple"></div>
      <svg id="cursor" viewBox="0 0 40 40" fill="none">
        <path d="M6 3L6 31L13.5 24L19 35L23.5 32.8L18 22L28 22L6 3Z" fill="#1E1730" stroke="#FFFFFF" stroke-width="2.5" stroke-linejoin="round"/>
      </svg>
    </div>

  </div><!-- /#camera-rig -->

  <!-- Frameless B-Station Style Subtitle Safe Zone -->
  <div id="subtitle-wrap">
    <div id="subtitle-text"></div>
  </div>
  <div id="watermark">Created by Huashu-Design</div>
</div>

<!-- Interactive Player Controls (auto-hidden in ?render=1) -->
<div id="player-hud">
  <button id="btn-play">▶ 播放教程</button>
  <input id="scrub" type="range" min="0" max="100" step="0.05" value="0" />
  <span id="player-time">00:00 / 00:00</span>
</div>
<audio id="audio-el" src="audio/audio_master.m4a" preload="auto"></audio>

<script>
const TIMELINE = __TIMELINE_JSON__;

// Easing & math helpers
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const easeOutCubic = x => 1 - Math.pow(1 - clamp(x), 3);
const easeInOutCubic = x => { x = clamp(x); return x < 0.5 ? 4*x*x*x : 1 - Math.pow(-2*x + 2, 3)/2; };
const easeOutBack = x => { x = clamp(x); const c1 = 1.45, c3 = c1 + 1; return 1 + c3*Math.pow(x - 1, 3) + c1*Math.pow(x - 1, 2); };
const prog = (t, a, b) => clamp((t - a) / Math.max(0.001, b - a));
const smoothWindow = (t, a, b, fadeIn = 0.35, fadeOut = 0.35) => {
  if (t < a || t > b) return 0;
  const fi = fadeIn > 0 ? easeOutCubic((t - a) / fadeIn) : 1;
  const fo = fadeOut > 0 ? easeOutCubic((b - t) / fadeOut) : 1;
  return Math.min(fi, fo);
};

// DOM references
const $ = id => document.getElementById(id);
const rig = $("camera-rig");
const topBar = $("top-bar");
const stepPills = Array.from(document.querySelectorAll(".step-pill"));
const subText = $("subtitle-text");
const cursorEl = $("cursor");
const rippleEl = $("click-ripple");

const C = TIMELINE.cues;
const CH = Object.fromEntries(TIMELINE.chapters.map(c => [c.scene, c]));

// Highlight key UI terms in subtitles cleanly
const HL_TERMS = [
  "「应用程序」", "「完成」", "「安全性」", "「仍要打开」", "「本地网络」", "「麦克风」",
  "「打开」", "「环境与依赖」", "「已就绪」", "「修复 / 更新依赖」", "「服务总览」",
  "「局域网共享」", "「在浏览器打开学习机」", "「资料库」", "「局域网访问地址」",
  "8000", "http://192.168.1.28:8000", "Lingo"
];
function formatSubtitle(txt) {
  let out = txt;
  for (const term of HL_TERMS) {
    if (out.includes(term)) {
      out = out.replace(term, `<span class="hl">${term}</span>`);
      break;
    }
  }
  return out;
}

// Flatten subtitle items for O(n) crisp lookup
const ALL_SUBS = [];
for (const ck of TIMELINE.chunks) {
  for (const s of ck.subs) ALL_SUBS.push(s);
}

// Camera keyframe interpolation helper (smooth continuous segments)
function evalKeyframes(t, kfs, keys) {
  if (t <= kfs[0].t) {
    const o = {}; keys.forEach(k => o[k] = kfs[0][k]); return o;
  }
  for (let i = 0; i < kfs.length - 1; i++) {
    const a = kfs[i], b = kfs[i + 1];
    if (t >= a.t && t <= b.t) {
      const p = easeInOutCubic((t - a.t) / Math.max(0.001, b.t - a.t));
      const o = {};
      keys.forEach(k => o[k] = lerp(a[k], b[k], p));
      return o;
    }
  }
  const last = kfs[kfs.length - 1];
  const o = {}; keys.forEach(k => o[k] = last[k]); return o;
}

// Precompute camera timeline aligned to exact measured cues!
// PanX/PanY shift content BEFORE scale around (960, 510): transform = scale(s) translate(px, py)
const CAM_KFS = [
  { t: 0, s: 1.0, x: 0, y: 0 },
  { t: C.mac_settings.start, s: 1.0, x: 0, y: 0 },
  // S02 push into "仍要打开" card (balanced inside safe zone)
  { t: C.mac_open_anyway.start + 0.1, s: 1.0, x: 0, y: 0 },
  { t: C.mac_open_anyway.start + 1.0, s: 1.18, x: -78, y: 28 },
  { t: C.mac_open_anyway.end, s: 1.18, x: -78, y: 28 },
  // S02 pan gently down to Local Network & Microphone switches
  { t: C.mac_local_net.start + 0.9, s: 1.16, x: -72, y: -32 },
  { t: C.mac_local_net.end, s: 1.16, x: -72, y: -32 },
  // S02 pull back for right-click tip
  { t: C.mac_tip.start + 0.8, s: 1.0, x: 0, y: 0 },
  { t: C.env_open.end, s: 1.0, x: 0, y: 0 },
  // S03 push gently into 5 green ready items
  { t: C.env_check.start + 0.9, s: 1.14, x: 0, y: -58 },
  { t: C.env_check.end, s: 1.14, x: 0, y: -58 },
  // S03 pan gently up-left to "修复 / 更新依赖" without hitting bottom subtitle
  { t: C.env_repair.start + 0.9, s: 1.16, x: 145, y: 12 },
  { t: C.env_repair.end - 0.3, s: 1.16, x: 145, y: 12 },
  // S04 pull out on tab switch, then push into Port 8000 + LAN Sharing
  { t: C.pub_tab.start + 0.7, s: 1.0, x: 0, y: 0 },
  { t: C.pub_tab.start + 2.4, s: 1.0, x: 0, y: 0 },
  { t: C.pub_tab.end, s: 1.18, x: 75, y: -78 },
  { t: C.pub_lan.start + 0.7, s: 1.22, x: 18, y: -115 },
  { t: C.pub_lan.end - 0.2, s: 1.22, x: 18, y: -115 },
  // S04 pan cleanly up to :8000 ON AIR + LAN URL
  { t: C.pub_onair.start + 0.9, s: 1.14, x: 14, y: 14 },
  { t: C.pub_onair.end, s: 1.14, x: 14, y: 14 },
  // S05 Browser full view -> Upload -> Shadowing -> Skins
  { t: C.web_open.start + 0.7, s: 1.0, x: 0, y: 0 },
  { t: C.web_upload.start + 0.5, s: 1.0, x: 0, y: 0 },
  { t: C.web_upload.start + 1.4, s: 1.10, x: 64, y: 4 },
  { t: C.web_upload.end - 0.3, s: 1.10, x: 64, y: 4 },
  { t: C.web_shadow.start + 0.6, s: 1.0, x: 0, y: 0 },
  { t: C.web_shadow.start + 1.8, s: 1.18, x: 118, y: -72 },
  { t: C.web_shadow.end - 0.3, s: 1.18, x: 118, y: -72 },
  { t: C.web_skin.start + 0.8, s: 1.18, x: -165, y: 76 },
  { t: C.web_skin.end - 0.1, s: 1.18, x: -165, y: 76 },
  // S06 Dual device desk -> focus iPad during typing -> wide dual finish
  { t: C.ipad_intro.start + 0.6, s: 1.0, x: 0, y: 0 },
  { t: C.ipad_copy.end, s: 1.0, x: 0, y: 0 },
  { t: C.ipad_type.start + 0.9, s: 1.12, x: -170, y: 12 },
  { t: C.ipad_type.end + 0.3, s: 1.12, x: -170, y: 12 },
  { t: C.ipad_ready.start + 1.2, s: 1.0, x: 0, y: 0 },
  { t: TIMELINE.totalDuration, s: 1.0, x: 0, y: 0 },
];

// Cursor waypoint choreography (exact visual clicks synced with audio cues!)
function evalCursor(t) {
  // Default hidden
  let vis = 0, x = 960, y = 540, pressed = 0, rip = 0, rx = 0, ry = 0;

  const setClick = (clickT, cx, cy, win = 0.42) => {
    const dt = t - clickT;
    if (dt >= -0.06 && dt <= 0.12) pressed = 1;
    if (dt >= 0 && dt <= win) {
      rip = 1 - dt / win;
      rx = cx; ry = cy;
    }
  };

  // S01: Drag Lingo.app from (732, 480) to Applications (1190, 480)
  if (t >= C.dmg_open.start + 1.6 && t <= C.dmg_done.end + 0.1) {
    vis = smoothWindow(t, C.dmg_open.start + 1.6, C.dmg_done.end + 0.1, 0.3, 0.3);
    const pMove = easeInOutCubic(prog(t, C.dmg_open.start + 1.6, C.dmg_open.start + 2.4));
    const pDrag = easeInOutCubic(prog(t, C.dmg_open.start + 2.6, C.dmg_done.start + 0.35));
    if (t < C.dmg_open.start + 2.5) {
      x = lerp(610, 732, pMove);
      y = lerp(650, 485, pMove) - Math.sin(pMove * Math.PI) * 35;
    } else {
      x = lerp(732, 1188, pDrag);
      y = 485 - Math.sin(pDrag * Math.PI) * 58;
      if (pDrag > 0 && pDrag < 0.98) pressed = 1;
    }
    setClick(C.dmg_open.start + 2.4, 732, 485);
    setClick(C.dmg_done.start + 0.45, 1188, 485);
  }
  // S02A: Click Gatekeeper "完成" at (1076, 650)
  else if (t >= C.mac_block.start + 3.0 && t <= C.mac_block.end + 0.2) {
    vis = smoothWindow(t, C.mac_block.start + 3.0, C.mac_block.end + 0.2, 0.25, 0.25);
    const p = easeInOutCubic(prog(t, C.mac_block.start + 3.0, C.mac_block.start + 4.1));
    x = lerp(1240, 1076, p);
    y = lerp(760, 654, p) - Math.sin(p * Math.PI) * 28;
    setClick(C.mac_block.start + 4.2, 1076, 654);
  }
  // S02B: Click "隐私与安全性" sidebar (510, 388) -> "仍要打开" (1446, 360) -> "本地网络" (1480, 536) -> "麦克风" (1480, 636)
  else if (t >= C.mac_settings.start + 0.5 && t <= C.mac_local_net.end + 0.3) {
    vis = smoothWindow(t, C.mac_settings.start + 0.5, C.mac_local_net.end + 0.3, 0.25, 0.3);
    const kfs = [
      { t: C.mac_settings.start + 0.5, x: 700, y: 500 },
      { t: C.mac_settings.start + 1.4, x: 515, y: 388 },
      { t: C.mac_open_anyway.start + 0.6, x: 1120, y: 410 },
      { t: C.mac_open_anyway.start + 2.1, x: 1446, y: 358 },
      { t: C.mac_open_anyway.end, x: 1446, y: 358 },
      { t: C.mac_local_net.start + 1.5, x: 1482, y: 544 },
      { t: C.mac_local_net.start + 2.3, x: 1482, y: 544 },
      { t: C.mac_local_net.start + 3.5, x: 1482, y: 642 },
      { t: C.mac_local_net.end + 0.3, x: 1482, y: 642 },
    ];
    const c = evalKeyframes(t, kfs, ["x", "y"]);
    x = c.x; y = c.y;
    setClick(C.mac_settings.start + 1.4, 515, 388);
    setClick(C.mac_open_anyway.start + 2.2, 1446, 358);
    setClick(C.mac_local_net.start + 1.6, 1482, 544);
    setClick(C.mac_local_net.start + 3.6, 1482, 642);
  }
  // S03: Click "环境与依赖" tab at console (444 + 1032*0.412 = 869, 162 + 700*0.073 = 213)
  else if (t >= C.env_open.start + 0.6 && t <= C.env_open.end + 0.2) {
    vis = smoothWindow(t, C.env_open.start + 0.6, C.env_open.end + 0.2, 0.25, 0.25);
    const p = easeInOutCubic(prog(t, C.env_open.start + 0.6, C.env_open.start + 1.55));
    x = lerp(740, 869, p); y = lerp(296, 199, p);
    setClick(C.env_open.start + 1.6, 869, 199);
  }
  // S04: Click "服务总览" (782, 213) -> Click "局域网共享" toggle (444+1032*0.292=745, 162+700*0.801=722) -> Click "在浏览器打开学习机" (676, 430)
  else if (t >= C.pub_tab.start + 0.8 && t <= C.pub_onair.end + 0.1) {
    vis = smoothWindow(t, C.pub_tab.start + 0.8, C.pub_onair.end + 0.1, 0.25, 0.25);
    const kfs = [
      { t: C.pub_tab.start + 0.8, x: 870, y: 199 },
      { t: C.pub_tab.start + 2.1, x: 782, y: 199 },
      { t: C.pub_tab.end, x: 782, y: 230 },
      { t: C.pub_lan.start + 1.15, x: 745, y: 708 },
      { t: C.pub_lan.end, x: 745, y: 708 },
      { t: C.pub_onair.start + 1.2, x: 676, y: 416 },
      { t: C.pub_onair.end, x: 676, y: 416 },
    ];
    const c = evalKeyframes(t, kfs, ["x", "y"]);
    x = c.x; y = c.y;
    setClick(C.pub_tab.start + 2.2, 782, 199);
    setClick(C.pub_lan.start + 1.2, 745, 708);
    setClick(C.pub_onair.start + 1.3, 676, 416);
  }
  // S05: Click "资料库" (400+1120*0.518=980, 190+700*0.042=219) -> Click "跟读对比" (831, 670) -> Click skins (1278, 218)
  else if (t >= C.web_open.start + 2.6 && t <= C.web_skin.end) {
    vis = smoothWindow(t, C.web_open.start + 2.6, C.web_skin.end, 0.25, 0.25);
    const kfs = [
      { t: C.web_open.start + 2.6, x: 960, y: 460 },
      { t: C.web_upload.start + 0.35, x: 980, y: 207 },
      { t: C.web_upload.start + 2.1, x: 710, y: 398 },
      { t: C.web_shadow.start + 1.2, x: 831, y: 658 },
      { t: C.web_shadow.start + 2.6, x: 831, y: 658 },
      { t: C.web_shadow.end, x: 831, y: 658 },
      { t: C.web_skin.start + 0.85, x: 1278, y: 206 },
      { t: C.web_skin.end, x: 1278, y: 206 },
    ];
    const c = evalKeyframes(t, kfs, ["x", "y"]);
    x = c.x; y = c.y;
    setClick(C.web_upload.start + 0.4, 980, 207);
    setClick(C.web_shadow.start + 2.6, 831, 658);
    setClick(C.web_skin.start + 0.9, 1278, 206);
  }
  // S06: Click Mac copy LAN URL button (126 + 722*0.88 = 761, 306 + 490*0.455 = 529)
  else if (t >= C.ipad_copy.start + 0.5 && t <= C.ipad_copy.end + 0.2) {
    vis = smoothWindow(t, C.ipad_copy.start + 0.5, C.ipad_copy.end + 0.2, 0.25, 0.25);
    const p = easeInOutCubic(prog(t, C.ipad_copy.start + 0.5, C.ipad_copy.start + 1.55));
    x = lerp(520, 761, p); y = lerp(618, 507, p);
    setClick(C.ipad_copy.start + 1.6, 761, 507);
  }

  return { vis, x, y, pressed, rip, rx, ry };
}

function renderFrame(t) {
  t = clamp(t, 0, TIMELINE.totalDuration);

  // 1. Top progress bar visibility & active step
  const showTop = smoothWindow(t, C.dmg_open.start - 0.4, C.recap_cards.start + 0.2, 0.45, 0.45);
  topBar.style.opacity = showTop.toFixed(3);
  topBar.style.transform = `translateY(${lerp(-18, 0, showTop).toFixed(1)}px)`;

  let curStep = 0;
  if (t >= CH.S06.start) curStep = 6;
  else if (t >= CH.S05.start) curStep = 5;
  else if (t >= CH.S04.start) curStep = 4;
  else if (t >= CH.S03.start) curStep = 3;
  else if (t >= CH.S02.start) curStep = 2;
  else if (t >= C.dmg_open.start - 0.3) curStep = 1;

  stepPills.forEach(el => {
    const n = Number(el.dataset.step);
    el.classList.toggle("active", n === curStep);
    el.classList.toggle("done", n < curStep);
    el.querySelector(".snum").textContent = n < curStep ? "✓" : String(n);
  });

  // 2. Camera continuous zoom & pan
  const cam = evalKeyframes(t, CAM_KFS, ["s", "x", "y"]);
  rig.style.transform = `scale(${cam.s.toFixed(4)}) translate(${cam.x.toFixed(1)}px, ${cam.y.toFixed(1)}px)`;

  // 3. Subtitle sync (B-station frameless, exact proportional chunks)
  let activeSub = null;
  for (let i = 0; i < ALL_SUBS.length; i++) {
    const s = ALL_SUBS[i];
    if (t >= s.start - 0.04 && t <= s.end + 0.14) { activeSub = s; break; }
  }
  if (activeSub) {
    const op = smoothWindow(t, activeSub.start - 0.04, activeSub.end + 0.14, 0.12, 0.14);
    subText.innerHTML = formatSubtitle(activeSub.text);
    subText.style.opacity = op.toFixed(3);
    subText.style.transform = `translateY(${lerp(8, 0, op).toFixed(1)}px)`;
  } else {
    subText.style.opacity = "0";
  }

  // ==================== S01: INTRO + DMG ====================
  const s01Op = smoothWindow(t, 0, CH.S01.end + 0.35, 0.01, 0.38);
  $("layer-s01").style.opacity = s01Op.toFixed(3);
  if (s01Op > 0) {
    // Intro Hero: visible during c01, lifts smoothly out as DMG enters
    const introIn = easeOutBack(prog(t, 0.05, 0.85));
    const introOut = easeInOutCubic(prog(t, C.dmg_open.start - 0.45, C.dmg_open.start + 0.25));
    const introOp = clamp(prog(t, 0.02, 0.45)) * (1 - introOut);
    $("intro-hero").style.opacity = introOp.toFixed(3);
    $("intro-hero").style.transform = `translateY(${lerp(36, 0, clamp(introIn)) - introOut * 55}px) scale(${lerp(0.92, 1.0, clamp(introIn)) * lerp(1, 0.94, introOut)})`;

    // DMG Window enters smoothly as intro lifts out
    const dmgIn = easeOutBack(prog(t, C.dmg_open.start - 0.15, C.dmg_open.start + 0.65));
    const dmgOut = easeInOutCubic(prog(t, CH.S01.end - 0.1, CH.S01.end + 0.35));
    const dmgOp = clamp(prog(t, C.dmg_open.start - 0.15, C.dmg_open.start + 0.3)) * (1 - dmgOut);
    $("dmg-win").style.opacity = dmgOp.toFixed(3);
    $("dmg-win").style.transform = `translateY(${lerp(42, 0, clamp(dmgIn))}px) scale(${lerp(0.9, 1.0, clamp(dmgIn)) * lerp(1, 1.06, dmgOut)})`;

    // Drag ghost from Lingo.app to Applications
    const pDrag = easeInOutCubic(prog(t, C.dmg_open.start + 2.55, C.dmg_done.start + 0.35));
    const ghostEl = $("dmg-drag-ghost");
    if (pDrag > 0 && pDrag < 1) {
      ghostEl.style.opacity = "0.92";
      const gx = lerp(196, 652, pDrag);
      const gy = 148 - Math.sin(pDrag * Math.PI) * 64;
      ghostEl.style.left = gx.toFixed(1) + "px";
      ghostEl.style.top = gy.toFixed(1) + "px";
      ghostEl.style.transform = `scale(${lerp(1.06, 0.88, pDrag).toFixed(3)})`;
    } else {
      ghostEl.style.opacity = "0";
    }

    // Folder bounce + Done badge
    const pDone = easeOutBack(prog(t, C.dmg_done.start + 0.35, C.dmg_done.start + 0.95));
    const bounce = t >= C.dmg_done.start + 0.35 ? 1 + 0.10 * Math.sin(clamp((t - (C.dmg_done.start + 0.35)) / 0.45) * Math.PI) : 1;
    $("dmg-dst-slot").style.transform = `scale(${bounce.toFixed(3)})`;
    $("dmg-done-badge").style.opacity = clamp(prog(t, C.dmg_done.start + 0.35, C.dmg_done.start + 0.7)).toFixed(3);
    $("dmg-done-badge").style.transform = `translateX(-50%) scale(${lerp(0.82, 1.0, clamp(pDone)).toFixed(3)})`;
  }

  // ==================== S02: macOS PRIVACY & SECURITY ====================
  const s02Op = smoothWindow(t, CH.S02.start - 0.15, CH.S02.end + 0.35, 0.42, 0.38);
  $("layer-s02").style.opacity = s02Op.toFixed(3);
  if (s02Op > 0) {
    const winIn = easeOutCubic(prog(t, CH.S02.start - 0.15, CH.S02.start + 0.5));
    const winOut = easeInOutCubic(prog(t, CH.S02.end - 0.05, CH.S02.end + 0.35));
    $("mac-settings-win").style.transform = `scale(${lerp(0.93, 1.0, winIn) * lerp(1, 0.84, winOut)})`;

    // Gatekeeper block alert shown during mac_block until click OK at mac_block.start + 4.25
    const gkOp = smoothWindow(t, C.mac_block.start + 0.2, C.mac_block.start + 4.55, 0.32, 0.28);
    $("gk-backdrop").style.opacity = gkOp.toFixed(3);
    const gkScale = easeOutBack(prog(t, C.mac_block.start + 0.2, C.mac_block.start + 0.65));
    $("gk-modal").style.transform = `scale(${lerp(0.86, 1.0, clamp(gkScale)).toFixed(3)})`;

    // "仍要打开" floating badge & unlock transition at mac_open_anyway.start + 2.3
    const unlocked = t >= C.mac_open_anyway.start + 2.35;
    const badgeOp = smoothWindow(t, C.mac_open_anyway.start + 0.3, C.mac_open_anyway.start + 2.4, 0.28, 0.22);
    $("badge-open-anyway").style.opacity = badgeOp.toFixed(3);
    $("badge-open-anyway").style.transform = `translateY(${lerp(10, 0, badgeOp).toFixed(1)}px)`;

    const allowCard = $("ms-allow-card");
    const btnOpen = $("btn-open-anyway");
    allowCard.classList.toggle("unlocked", unlocked);
    btnOpen.classList.toggle("done", unlocked);
    $("ms-allow-h").textContent = unlocked ? "已永久放行「Lingo」" : "已阻止使用「Lingo」，因为无法验证开发者";
    $("ms-allow-p").textContent = unlocked ? "验证通过，以后直接双击即可顺利打开" : "点击右侧按钮并输入 Mac 开机密码，即可永久放行";
    btnOpen.textContent = unlocked ? "✓ 已放行" : "仍要打开";

    // Switches: Local Network turns ON at mac_local_net.start + 1.65; Mic turns ON at mac_local_net.start + 3.65
    const lnOn = t >= C.mac_local_net.start + 1.65;
    const micOn = t >= C.mac_local_net.start + 3.65;
    $("sw-localnet").classList.toggle("on", lnOn);
    $("row-localnet").classList.toggle("hl-row", t >= C.mac_local_net.start && t < C.mac_local_net.start + 2.8);
    $("sw-mic").classList.toggle("on", micOn);
    $("row-mic").classList.toggle("hl-row", t >= C.mac_local_net.start + 2.8 && t <= C.mac_local_net.end + 0.2);

    // Right-click tip slides in during mac_tip
    const tipOp = smoothWindow(t, C.mac_tip.start - 0.1, CH.S02.end + 0.2, 0.35, 0.25);
    $("mac-rightclick-tip").style.opacity = tipOp.toFixed(3);
    $("mac-rightclick-tip").style.transform = `translateY(${lerp(14, 0, tipOp).toFixed(1)}px)`;
  }

  // ==================== S03A: NATIVE PROGRESS HUD ====================
  const hudOp = smoothWindow(t, C.hud_init.start - 0.35, C.env_open.start + 0.25, 0.38, 0.32);
  $("layer-s03-hud").style.opacity = hudOp.toFixed(3);
  if (hudOp > 0) {
    const hudIn = easeOutBack(prog(t, C.hud_init.start - 0.35, C.hud_init.start + 0.3));
    const hudExpand = easeInOutCubic(prog(t, C.env_open.start - 0.15, C.env_open.start + 0.25));
    $("native-hud").style.transform = `scale(${lerp(0.88, 1.0, clamp(hudIn)) * lerp(1.0, 1.18, hudExpand)})`;
    const pBar = easeInOutCubic(prog(t, C.hud_init.start + 0.3, C.hud_init.start + 4.4));
    $("hud-bar-fill").style.width = `${lerp(24, 100, pBar).toFixed(1)}%`;
    $("hud-step-txt").textContent =
      pBar < 0.45 ? "正在检测独立 Python 运行环境..." :
      pBar < 0.88 ? "正在校验音频引擎与核心学习机依赖..." :
      "✓ 准备完成，正在自动打开桌面控制台";
  }

  // ==================== S03B & S04: REAL DESKTOP CONTROL CENTER ====================
  const conOp = smoothWindow(t, C.env_open.start - 0.05, CH.S04.end + 0.35, 0.35, 0.38);
  $("layer-console").style.opacity = conOp.toFixed(3);
  if (conOp > 0) {
    const conIn = easeOutCubic(prog(t, C.env_open.start - 0.05, C.env_open.start + 0.4));
    const conOut = easeInOutCubic(prog(t, CH.S04.end - 0.05, CH.S04.end + 0.35));
    $("console-win").style.transform = `scale(${lerp(0.91, 1.0, conIn) * lerp(1, 1.05, conOut)})`;

    // Cross-morph from env screenshot -> overview screenshot right when clicking 服务总览 tab!
    const tabBlend = easeInOutCubic(prog(t, C.pub_tab.start + 2.2, C.pub_tab.start + 2.65));
    $("img-console-overview").style.opacity = tabBlend.toFixed(3);
    $("img-console-env").style.opacity = (1 - tabBlend).toFixed(3);

    // S03 Highlights
    const sEnvList = smoothWindow(t, C.env_check.start + 0.2, C.env_check.end + 0.1, 0.3, 0.25);
    $("spot-env-list").style.opacity = sEnvList.toFixed(3);
    $("call-env-ok").style.opacity = sEnvList.toFixed(3);
    $("call-env-ok").style.transform = `translateY(${lerp(12, 0, sEnvList).toFixed(1)}px)`;

    const sEnvRep = smoothWindow(t, C.env_repair.start + 0.2, C.env_repair.end - 0.1, 0.3, 0.25);
    $("spot-env-repair").style.opacity = sEnvRep.toFixed(3);
    $("call-env-repair").style.opacity = sEnvRep.toFixed(3);
    $("call-env-repair").style.transform = `translateY(${lerp(10, 0, sEnvRep).toFixed(1)}px)`;

    // S04 Highlights: Port 8000 -> LAN Sharing -> Password Lock -> :8000 ON AIR + Open Browser
    const sPort = smoothWindow(t, C.pub_tab.start + 3.0, C.pub_lan.start + 0.15, 0.28, 0.25);
    $("spot-pub-port").style.opacity = sPort.toFixed(3);
    $("call-pub-port").style.opacity = sPort.toFixed(3);

    const sLan = smoothWindow(t, C.pub_lan.start + 0.2, C.pub_lan.start + 3.9, 0.28, 0.25);
    $("spot-pub-lan").style.opacity = sLan.toFixed(3);
    $("call-pub-lan").style.opacity = sLan.toFixed(3);

    const sPass = smoothWindow(t, C.pub_lan.start + 4.0, C.pub_lan.end + 0.1, 0.25, 0.22);
    $("spot-pub-pass").style.opacity = sPass.toFixed(3);
    $("call-pub-pass").style.opacity = sPass.toFixed(3);

    const sOnAir = smoothWindow(t, C.pub_onair.start + 0.3, CH.S04.end + 0.1, 0.3, 0.25);
    $("spot-pub-onair").style.opacity = sOnAir.toFixed(3);
    $("call-pub-onair").style.opacity = sOnAir.toFixed(3);
    $("spot-pub-openbtn").style.opacity = smoothWindow(t, C.pub_onair.start + 0.8, C.pub_onair.start + 2.6, 0.2, 0.25).toFixed(3);
  }

  // ==================== S05: MAC BROWSER LEARNING MACHINE ====================
  const brOp = smoothWindow(t, CH.S05.start - 0.1, CH.S05.end + 0.35, 0.4, 0.38);
  $("layer-browser").style.opacity = brOp.toFixed(3);
  if (brOp > 0) {
    const brIn = easeOutCubic(prog(t, CH.S05.start - 0.1, CH.S05.start + 0.45));
    const brOut = easeInOutCubic(prog(t, CH.S05.end - 0.05, CH.S05.end + 0.35));
    $("browser-win").style.transform = `scale(${lerp(0.92, 1.0, brIn) * lerp(1, 0.90, brOut)}) translateX(${-brOut * 120}px)`;

    // Switch to Library screenshot during web_upload
    const libOp = smoothWindow(t, C.web_upload.start + 0.45, C.web_shadow.start + 0.2, 0.3, 0.3);
    $("img-web-library").style.opacity = libOp.toFixed(3);
    $("spot-web-upload").style.opacity = smoothWindow(t, C.web_upload.start + 0.8, C.web_upload.end - 0.2, 0.28, 0.25).toFixed(3);
    $("spot-web-5steps").style.opacity = smoothWindow(t, C.web_upload.start + 2.5, C.web_upload.end - 0.1, 0.28, 0.25).toFixed(3);
    $("call-web-upload").style.opacity = smoothWindow(t, C.web_upload.start + 0.9, C.web_upload.end - 0.2, 0.28, 0.25).toFixed(3);

    // Drag video chip glides into upload zone
    const pDrop = easeInOutCubic(prog(t, C.web_upload.start + 1.0, C.web_upload.start + 2.2));
    const chipOp = smoothWindow(t, C.web_upload.start + 0.9, C.web_upload.start + 2.6, 0.2, 0.3);
    $("drag-video-chip").style.opacity = chipOp.toFixed(3);
    $("drag-video-chip").style.transform = `translate(${lerp(-90, 65, pDrop).toFixed(1)}px, ${lerp(-60, 12, pDrop).toFixed(1)}px)`;

    // Shadowing & Deck highlight + live animated audio waveform bars!
    const shOp = smoothWindow(t, C.web_shadow.start + 0.7, C.web_shadow.end - 0.1, 0.3, 0.25);
    $("spot-web-shadow").style.opacity = shOp.toFixed(3);
    $("shadow-wave").style.opacity = shOp.toFixed(3);
    if (shOp > 0) {
      const bars = $("w-bars").children;
      for (let i = 0; i < bars.length; i++) {
        const h = 6 + 15 * (0.5 + 0.5 * Math.sin(t * 11 + i * 1.35));
        bars[i].style.height = `${h.toFixed(1)}px`;
      }
    }

    // Skins highlight
    const skOp = smoothWindow(t, C.web_skin.start + 0.2, CH.S05.end + 0.1, 0.25, 0.25);
    $("spot-web-skins").style.opacity = skOp.toFixed(3);
    $("call-web-skins").style.opacity = skOp.toFixed(3);
  }

  // ==================== S06: DUAL DEVICE MAC + IPAD ====================
  const duOp = smoothWindow(t, CH.S06.start - 0.1, CH.S06.end + 0.38, 0.42, 0.4);
  $("layer-dual").style.opacity = duOp.toFixed(3);
  if (duOp > 0) {
    const macSlide = easeOutBack(prog(t, CH.S06.start - 0.1, CH.S06.start + 0.7));
    const ipadSlide = easeOutBack(prog(t, CH.S06.start + 0.1, CH.S06.start + 0.85));
    const duOut = easeInOutCubic(prog(t, CH.S06.end - 0.05, CH.S06.end + 0.38));

    $("dual-mac").style.transform = `translateX(${lerp(-140, 0, clamp(macSlide)) - duOut * 60}px) scale(${lerp(0.95, 1, clamp(macSlide)) * lerp(1, 0.92, duOut)})`;
    $("dual-ipad").style.transform = `translateX(${lerp(180, 0, clamp(ipadSlide)) + duOut * 60}px) scale(${lerp(0.94, 1, clamp(ipadSlide)) * lerp(1, 0.92, duOut)})`;

    // Wi-Fi arc & bridge pill appear during ipad_wifi
    const wifiOp = smoothWindow(t, C.ipad_wifi.start - 0.2, CH.S06.end + 0.1, 0.45, 0.3);
    $("wifi-bridge-pill").style.opacity = wifiOp.toFixed(3);
    $("wifi-bridge-pill").style.transform = `translateX(-50%) translateY(${lerp(-12, 0, wifiOp).toFixed(1)}px)`;
    $("wifi-arc-svg").style.opacity = wifiOp.toFixed(3);
    $("wifi-arc-path").style.strokeDashoffset = `${(-t * 36).toFixed(1)}`;

    // Highlight LAN URL on Mac during ipad_copy
    $("spot-dual-url").style.opacity = smoothWindow(t, C.ipad_copy.start + 0.2, C.ipad_type.start + 0.4, 0.25, 0.25).toFixed(3);

    // Flying URL pill arcs from Mac (520, 520) -> iPad Safari bar (1410, 248)
    const pFly = easeInOutCubic(prog(t, C.ipad_copy.start + 1.65, C.ipad_type.start + 0.85));
    const flyOp = smoothWindow(t, C.ipad_copy.start + 1.65, C.ipad_type.start + 0.95, 0.15, 0.2);
    $("flying-url-pill").style.opacity = flyOp.toFixed(3);
    if (flyOp > 0) {
      const fx = lerp(420, 1280, pFly);
      const fy = lerp(520, 240, pFly) - Math.sin(pFly * Math.PI) * 140;
      $("flying-url-pill").style.left = fx.toFixed(1) + "px";
      $("flying-url-pill").style.top = fy.toFixed(1) + "px";
    }

    // iPad typing animation during ipad_type
    const fullUrl = "http://192.168.1.28:8000";
    if (t < C.ipad_type.start + 0.8) {
      $("ipad-typed-text").textContent = "在地址栏输入局域网网址...";
      $("ipad-typed-text").style.color = "#9B90AF";
    } else {
      const pType = prog(t, C.ipad_type.start + 0.85, C.ipad_type.start + 2.55);
      const chars = Math.max(1, Math.round(pType * fullUrl.length));
      const blink = (pType < 1 && Math.floor(t * 6) % 2 === 0) ? "|" : "";
      $("ipad-typed-text").textContent = fullUrl.slice(0, chars) + blink;
      $("ipad-typed-text").style.color = "#FFFDF8";
    }

    // Real iPad screen blooms crisp right on ipad_ready!
    const ipadReadyOp = easeOutCubic(prog(t, C.ipad_type.end - 0.15, C.ipad_ready.start + 0.45));
    $("ipad-real-img").style.opacity = ipadReadyOp.toFixed(3);
    $("ipad-real-img").style.transform = `scale(${lerp(1.03, 1.0, ipadReadyOp).toFixed(4)})`;
    $("ipad-conn-tag").style.opacity = ipadReadyOp.toFixed(3);

    // Bottom 3 checklist pills stay visible on wide dual views & step aside cleanly during ipad_type zoom
    const zoomHide = 1 - smoothWindow(t, C.ipad_type.start + 0.15, C.ipad_ready.start + 0.85, 0.3, 0.35);
    const c1 = smoothWindow(t, C.ipad_wifi.start + 0.4, CH.S06.end + 0.1, 0.3, 0.25) * zoomHide;
    const c2 = smoothWindow(t, C.ipad_wifi.start + 2.2, CH.S06.end + 0.1, 0.3, 0.25) * zoomHide;
    const c3 = smoothWindow(t, C.ipad_ready.start + 1.3, CH.S06.end + 0.1, 0.3, 0.25);
    [["lchk-1", c1], ["lchk-2", c2], ["lchk-3", c3]].forEach(([id, v]) => {
      $(id).style.opacity = v.toFixed(3);
      $(id).style.transform = `translateY(${lerp(16, 0, v).toFixed(1)}px)`;
    });
  }

  // ==================== S07: 4-STEP RECAP & OUTRO ====================
  const recOp = smoothWindow(t, CH.S07.start - 0.1, TIMELINE.totalDuration + 1, 0.45, 0);
  $("layer-recap").style.opacity = recOp.toFixed(3);
  if (recOp > 0) {
    const logoP = easeOutBack(prog(t, CH.S07.start, CH.S07.start + 0.75));
    const floatY = Math.sin((t - CH.S07.start) * 2.2) * 5;
    $("recap-logo").style.transform = `translateY(${(lerp(28, 0, clamp(logoP)) + floatY).toFixed(1)}px) scale(${lerp(0.88, 1.0, clamp(logoP)).toFixed(3)})`;
    $("recap-sub").textContent = t >= C.outro_logo.start - 0.1 ? "打开声音，精听每一句" : "四步速记，轻松上手";

    const cardStarts = [
      C.recap_cards.start + 0.9,
      C.recap_cards.start + 2.1,
      C.recap_cards.start + 3.3,
      C.recap_cards.start + 4.5,
    ];
    cardStarts.forEach((st, idx) => {
      const p = easeOutBack(prog(t, st, st + 0.55));
      const el = $(`rc-${idx + 1}`);
      el.style.opacity = clamp(prog(t, st, st + 0.28)).toFixed(3);
      el.style.transform = `translateY(${lerp(34, 0, clamp(p)).toFixed(1)}px) scale(${lerp(0.92, 1.0, clamp(p)).toFixed(3)})`;
    });
  }

  // ==================== CURSOR & CLICK RIPPLE ====================
  const cur = evalCursor(t);
  cursorEl.style.opacity = cur.vis.toFixed(3);
  cursorEl.style.transform = `translate(${cur.x.toFixed(1)}px, ${cur.y.toFixed(1)}px) scale(${cur.pressed ? 0.84 : 1.0})`;
  if (cur.rip > 0) {
    rippleEl.style.opacity = (cur.rip * 0.88).toFixed(3);
    const rs = lerp(0.35, 1.55, 1 - cur.rip);
    rippleEl.style.transform = `translate(${cur.rx.toFixed(1)}px, ${cur.ry.toFixed(1)}px) scale(${rs.toFixed(3)})`;
  } else {
    rippleEl.style.opacity = "0";
  }
}

// Expose deterministic frame render API for Playwright video exporter
window.__TIMELINE__ = TIMELINE;
window.__seek = function(t) { renderFrame(t); };

// Responsive scale-to-fit for interactive browser viewing
function fitStage() {
  if (document.body.classList.contains("render-mode")) {
    $("viewport-wrap").style.transform = "none";
    return;
  }
  const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
  $("viewport-wrap").style.transform = `scale(${s})`;
}
if (new URLSearchParams(location.search).get("render") === "1") {
  document.body.classList.add("render-mode");
}
window.addEventListener("resize", fitStage);
fitStage();

// Interactive HTML player sync with audio_master.m4a
const audioEl = $("audio-el");
const btnPlay = $("btn-play");
const scrub = $("scrub");
const timeEl = $("player-time");
scrub.max = TIMELINE.totalDuration.toFixed(2);

const fmt = s => `${String(Math.floor(s/60)).padStart(2,"0")}:${String(Math.floor(s%60)).padStart(2,"0")}`;
let playing = false, rafId = 0;

function tick() {
  if (!playing) return;
  const t = audioEl.currentTime;
  renderFrame(t);
  scrub.value = t.toFixed(2);
  timeEl.textContent = `${fmt(t)} / ${fmt(TIMELINE.totalDuration)}`;
  if (!audioEl.ended) rafId = requestAnimationFrame(tick);
  else { playing = false; btnPlay.textContent = "↻ 重播"; }
}
btnPlay.onclick = () => {
  if (playing) {
    audioEl.pause(); playing = false; cancelAnimationFrame(rafId); btnPlay.textContent = "▶ 继续播放";
  } else {
    if (audioEl.ended) audioEl.currentTime = 0;
    audioEl.play().catch(() => {});
    playing = true; btnPlay.textContent = "❚❚ 暂停"; tick();
  }
};
scrub.oninput = () => {
  const t = parseFloat(scrub.value);
  audioEl.currentTime = t;
  renderFrame(t);
  timeEl.textContent = `${fmt(t)} / ${fmt(TIMELINE.totalDuration)}`;
};

// Initial hero frame
renderFrame(0.8);
timeEl.textContent = `00:00 / ${fmt(TIMELINE.totalDuration)}`;
</script>
</body>
</html>
"""

out = HTML_TEMPLATE
out = out.replace("__IMG_LOGO__", IMG["logo"])
out = out.replace("__IMG_ICON__", IMG["icon"])
out = out.replace("__IMG_ENV__", IMG["env"])
out = out.replace("__IMG_OVERVIEW__", IMG["overview"])
out = out.replace("__IMG_WEB__", IMG["web"])
out = out.replace("__IMG_LIBRARY__", IMG["library"])
out = out.replace("__IMG_IPAD__", IMG["ipad"])
out = out.replace("__TIMELINE_JSON__", json.dumps(TIMELINE, ensure_ascii=False))

out_path = ROOT / "lingo-guide.html"
out_path.write_text(out, encoding="utf-8")
print(f"BUILT_FILM_HTML_OK: {out_path} ({out_path.stat().st_size / 1024 / 1024:.2f} MB)")

