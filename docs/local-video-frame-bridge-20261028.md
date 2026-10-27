# BOAT LAB on-device video frame bridge (2026-10-28)

## What this fixes

The BOATRACE/JLC/BOATCAST site lets an end user watch official exhibition replays in a supported browser. This does **not** imply third-party clients can obtain decoded frames or programmatically fetch streams. The research pipeline previously had no legal/supported frame transfer into BOAT LAB.

This patch adds an **explicitly user-controlled, local-to-the-browser** capture and frame extraction path, avoiding both cross-origin access and remote video uploads.

- iPhone/iPad/desktop: File picker for a video the user is permitted to process. Supports platform-decodable MP4/MOV/M4V/WebM/AVI formats, capped at 250MB. On iOS Safari, tap Play once if video frames are not made available until user interaction.
- Desktops and **only browsers exposing** navigator.mediaDevices.getDisplayMedia: User manually selects a screen/tab through the browser's native permission UI. Captures at most 16 short-duration frames; supports Stop and track-end cleanup. iOS browsers may not support this method.
- Video decode: HTMLVideoElement + same-page CanvasRenderingContext2D.drawImage. No YouTube/BOATCAST/JLC stream URL extraction, iframe circumvention, token reuse, DRM bypass or automated bulk recording.
- Canvas: downscaled to at most 640 pixels width to limit phone memory. File sampling: 24 frames at configured start/interval, currently default 0.5 s. Permissioned screen-share: up to 16 frames over ~8 seconds.
- Frame analysis: center of *unverified* white/black/red/blue/yellow/green pixel regions. Colored region can be overlay, reflection, water, etc. Never infer a boat identity or official ST from color. Blank/black frames are flagged as unusable; protected frames are not bypassed.
- Optional annotation: tap video frames to label first-mark center or boat #1–#6 *as a manual annotation*, without asserting correct racer identification. Work remains pixel-only and not converted to physical metres or m/s until fixed camera and perspective calibration are independently established.
- Research export: JSON includes frame timestamps, unverified color candidates and manual coordinates. The original video and thumbnail images **are not exported**. Nothing is posted to a server.
- Forecast isolation: no BUY/bet reallocation, no re-frozen pre-start forecast, no official result or payout ledger change.

## Not solved

This patch does not grant ChatGPT itself unattended access to official video pixels, and does not automatically read/track six boats from a third-party official live stream. User interaction is essential to provide valid input. End-user visual access and permitted automatic reproduction are not the same. Do not assume lawful reuse simply because a video is watchable; follow source terms and applicable copyright exceptions.

## Entry points

- BOAT LAB `app/exhibition-watch.html`, race-prefilled link to `app/local-video-bridge.html?date=2026-10-28&venue=唐津&race=1`.
- BOAT LAB `app/turn-vision-pilot-20261028.html`, per-race link for all 10 study venues.
- Research stream can be checked manually on [JLC official exhibition replay](https://livebb.jlc.ne.jp/bb_top/sp_bb/tvod_23.php) and [BOATCAST](https://boatcast.jp/).

## Tests and limits

`node --check app/local-video-bridge.js`

`node app/tests/local-video-bridge.test.js`

Pixel analysis and audit invariants are unit-tested with generated RGBA arrays. Browser screen-share, protected stream playback, iOS-specific file codecs, and **real official footage are not automatically integration-tested**. Dedicated official footage licenses/camera calibration/six-boat labels are needed before exporting any physical turn or stretch metrics into a trained research model.

Official resources: [JLC mobile help](https://livebb.jlc.ne.jp/bb_top/sp_bb/qa.php), [BOATCAST policy](https://boatcast.jp/static/sitepolicy/index.html).
