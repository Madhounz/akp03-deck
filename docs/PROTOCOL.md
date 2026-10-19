# AKP03E USB protocol

Notes for anyone writing their own software for the Ajazz AKP03E and its clones.
This is the "mirajazz v3" protocol, first documented by the projects listed in the README credits.

## Connecting

The device shows up as several HID interfaces. Use the one with a vendor usage page (`0xFF00` or higher,
`0xFFA0` on the AKP03E). The keyboard interface opens fine but rejects writes.

## Output reports

Every report is 1025 bytes: a report ID byte `0x00` followed by 1024 bytes of data.
Commands start with `CRT\0\0` (`43 52 54 00 00`) and are zero padded.

| Command | Bytes after `CRT\0\0` | Meaning |
|---|---|---|
| Wake | `DIS` | Wake the screens |
| Brightness | `LIG 00 00 <0..100>` | Screen brightness in percent |
| Clear | `CLE 00 00 00 <key+1>` | Clear one key, `0xFF` clears all |
| Image header | `BAT 00 00 <len hi> <len lo> <key+1>` | A JPEG of `len` bytes for this key follows |
| Commit | `STP` | Show what was sent |
| Keep alive | `CONNECT` | Sent every few seconds |
| Sleep | `HAN` | Turn the screens off |

### Sending a key image

1. Make a 60 × 60 RGB image and rotate it 90° clockwise (the panel is mounted sideways).
2. Encode it as JPEG. Quality 90 to 100 works. Some units only accept 4:2:0 chroma subsampling.
3. Send the `BAT` header with the JPEG length and the key number plus one.
4. Send the JPEG in 1024 byte chunks, each as its own zero padded report.
5. Send `STP`.

Only keys 0 to 5 have screens.

## Input reports

Input reports are 512 bytes. Valid ones start with `ACK` (`41 43 4B`).
Byte 9 says what was used and byte 10 is the state (1 pressed, 0 released).

| Byte 9 | Control |
|---|---|
| `0x01` to `0x06` | Screen keys 0 to 5 |
| `0x25`, `0x30`, `0x31` | Round buttons 1, 2, 3 |
| `0x33`, `0x35`, `0x34` | Knob press: left small, big, right small |
| `0x90` / `0x91` | Left small knob turn left / right |
| `0x50` / `0x51` | Big knob turn left / right |
| `0x60` / `0x61` | Right small knob turn left / right |

Knob turns send one report per click and have no release.

## Lessons learned

- Talk to the device from one thread only. Interleaved writes from different threads corrupt images and
  can lock the device up until it is reconnected.
- Do not flood it. Around 20 to 25 images a second is comfortable. Keep only the newest pending image per key.
- Skip images that did not change.
- Expect the device to need a fresh connection after the PC sleeps.
- The screens keep their last image while powered, even when no software is running.
