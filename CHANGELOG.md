# Changelog

## 6.1
- Turns on "Start when Windows starts" by default, with a switch in the quick panel
- New `launcher.pyw` keeps the app running: restarts it after a crash or a hang
- Reconnects the deck after the PC wakes from sleep
- Watchdog now catches a stuck USB connection even when nothing is queued

## 6.0
- Driver rewrite to stop freezes: one I/O thread, per key queues, rate limiting, unchanged images skipped, auto reconnect
- Quick panel next to the clock
- Lighter: data is only read when something on screen needs it, smaller image caches
- Studio: Ctrl+K search, Deck health, Export and Import, log file

## 5.0
- 3D icon pack and brand tiles, real app icons, animated GIF keys
- Tap, double tap and hold on every key and button
- Smart pages that follow the app in front
- Big knob modes with an on deck dashboard, per app volume
- Now Playing tile, focus timer, mic tile, Outlook and mic badges
- AI keys, macros, Arcade page with two mini games, stats and heatmap

## 4.0
- Gaming page with RGB glow, System page with live CPU and GPU tiles
- Credits banner, boot animation, screen glow

## 3.0
- Pages, page banner on the deck, wallpapers, app library, local web studio

## 2.0
- Modern look, no forced backgrounds, big sharp icons, start with Windows

## 1.0
- First driver and a simple editor
