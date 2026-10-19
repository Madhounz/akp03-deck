"""Live PC stats for the live tiles.

CPU usage, RAM, disk, network, battery: psutil (always works).
NVIDIA GPU (usage, temp, memory, power): nvidia-ml-py, uses the driver directly.
CPU temperature (and AMD / Intel GPUs): Windows does not share these without a helper.
  Run LibreHardwareMonitor and turn on Options > Remote Web Server (port 8085).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from collections import defaultdict, deque

import psutil

LHM_URL = "http://127.0.0.1:8085/data.json"

# id, name shown in the studio, short label on the key, style, unit
METRICS = [
    ("cpu_usage", "CPU usage", "CPU", "ring", "%"),
    ("cpu_temp", "CPU temperature", "CPU", "ring", "°C"),
    ("gpu_usage", "GPU usage", "GPU", "ring", "%"),
    ("gpu_temp", "GPU temperature", "GPU", "ring", "°C"),
    ("gpu_vram", "GPU memory", "VRAM", "ring", "%"),
    ("gpu_power", "GPU power", "POWER", "ring", "W"),
    ("ram", "RAM", "RAM", "ring", "%"),
    ("disk", "Disk space", "DISK", "ring", "%"),
    ("net_down", "Download speed", "DOWN", "spark", ""),
    ("net_up", "Upload speed", "UP", "spark", ""),
    ("battery", "Battery", "BATT", "ring", "%"),
    ("clock", "Clock", "", "clock", ""),
]
META = {m[0]: m for m in METRICS}


def _num(s):
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(s or ""))
    return float(m.group().replace(",", ".")) if m else None


def _walk(node, path):
    yield node, path
    for c in node.get("Children", []) or []:
        yield from _walk(c, path + [node.get("Text", "")])


_GPU_WORDS = ("geforce", "radeon", "nvidia", "rtx", "gtx", " arc", "graphics", "rx ")
_CPU_WORDS = ("ryzen", "core i", "core(tm)", "intel core", "core ultra", "cpu", "processor", "xeon", "threadripper", "athlon", "pentium")
_CPU_TEMP_ORDER = ("CPU Package", "Core (Tctl/Tdie)", "Tctl/Tdie", "CPU (Tctl/Tdie)", "Core Average", "Package")


def parse_lhm(tree: dict) -> dict:
    cpu_temps, out = {}, {}
    gpus = {}
    for node, path in _walk(tree, []):
        if node.get("Children") or len(path) < 3:
            continue
        hw, group, text = path[2].lower(), path[-1], node.get("Text", "")
        val = _num(node.get("Value"))
        if val is None:
            continue
        is_gpu = any(w in hw for w in _GPU_WORDS)
        is_cpu = not is_gpu and any(w in hw for w in _CPU_WORDS)
        if is_cpu and group == "Temperatures":
            cpu_temps[text] = val
        elif is_cpu and group == "Load" and text == "CPU Total":
            out["cpu_usage_lhm"] = val
        elif is_gpu:
            g = gpus.setdefault(hw, {"discrete": not hw.rstrip().endswith("graphics")})
            if group == "Temperatures" and text in ("GPU Core", "GPU Temperature", "GPU Hot Spot") and "temp" not in g:
                g["temp"] = val
            elif group == "Load" and text in ("GPU Core", "D3D 3D") and "load" not in g:
                g["load"] = val
    if cpu_temps:
        out["cpu_temp"] = next((cpu_temps[n] for n in _CPU_TEMP_ORDER if n in cpu_temps), max(cpu_temps.values()))
    if gpus:
        best = sorted(gpus.values(), key=lambda g: (not g["discrete"], "temp" not in g))[0]
        if "temp" in best:
            out["gpu_temp"] = best["temp"]
        if "load" in best:
            out["gpu_usage"] = best["load"]
    return out


class Monitor:
    def __init__(self):
        self.values: dict = {}
        self.hist = defaultdict(lambda: deque(maxlen=48))
        self.lhm_ok = False
        self.gpu_name = ""
        self._lhm_next = 0.0
        self._lhm_cache: dict = {}
        self.wanted = lambda: {"cpu_usage"}  # core replaces this
        self._nv = None
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nv = pynvml
            self._h = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(self._h)
            self.gpu_name = name.decode() if isinstance(name, bytes) else str(name)
        except Exception:
            self._nv = None
        psutil.cpu_percent(None)
        self._net = psutil.net_io_counters()
        self._t = time.time()
        self._sample()
        threading.Thread(target=self._loop, daemon=True).start()

    # ----- sources -----
    def _lhm(self) -> dict:
        if not getattr(self, "_need_lhm", True):
            return {}
        now = time.time()
        if now < self._lhm_next:
            return self._lhm_cache if self.lhm_ok else {}
        try:
            with urllib.request.urlopen(LHM_URL, timeout=0.5) as r:
                self._lhm_cache = parse_lhm(json.loads(r.read().decode("utf-8", "ignore")))
            self.lhm_ok = True
            self._lhm_next = now + 1.0
        except Exception:
            self.lhm_ok = False
            self._lhm_next = now + 10.0  # try again later, stay cheap
            self._lhm_cache = {}
        return self._lhm_cache

    def _sample(self):
        d: dict = {}
        d["cpu_usage"] = psutil.cpu_percent(None)
        vm = psutil.virtual_memory()
        d["ram"], d["ram_used"] = vm.percent, vm.used / 1024 ** 3
        try:
            drive = (os.environ.get("SystemDrive", "C:") + "\\") if os.name == "nt" else "/"
            d["disk"] = psutil.disk_usage(drive).percent
        except Exception:
            pass
        now, net = time.time(), psutil.net_io_counters()
        dt = max(0.2, now - self._t)
        d["net_down"] = max(0.0, (net.bytes_recv - self._net.bytes_recv) / dt)
        d["net_up"] = max(0.0, (net.bytes_sent - self._net.bytes_sent) / dt)
        self._net, self._t = net, now
        try:
            b = psutil.sensors_battery()
            if b:
                d["battery"] = b.percent
        except Exception:
            pass
        if self._nv:
            nv, h = self._nv, self._h
            try:
                d["gpu_usage"] = float(nv.nvmlDeviceGetUtilizationRates(h).gpu)
                d["gpu_temp"] = float(nv.nvmlDeviceGetTemperature(h, 0))
                mem = nv.nvmlDeviceGetMemoryInfo(h)
                d["gpu_vram"] = mem.used / mem.total * 100
                d["gpu_power"] = nv.nvmlDeviceGetPowerUsage(h) / 1000
                d["gpu_power_max"] = nv.nvmlDeviceGetEnforcedPowerLimit(h) / 1000
            except Exception:
                pass
        for k, v in self._lhm().items():
            if k == "cpu_usage_lhm":
                continue
            d.setdefault(k, v)
        for k, v in d.items():
            self.hist[k].append(v)
        self.values = d

    def _loop(self):
        while True:
            time.sleep(1.0)
            try:
                w = self.wanted()
                if not (w & set(META)):
                    time.sleep(2.0)  # nobody is looking: stay asleep
                    continue
                self._need_lhm = bool(w & {"cpu_temp", "gpu_temp", "gpu_usage"})
                self._sample()
            except Exception as e:
                print("Monitor error:", e)

    # ----- for tiles and the studio -----
    def get(self, kind: str) -> dict:
        """Everything a tile needs: text, unit, fill 0..1, label."""
        _, _, label, style, unit = META.get(kind, (kind, kind, kind.upper(), "ring", ""))
        v = self.values.get(kind)
        out = {"kind": kind, "style": style, "label": label, "unit": unit, "value": v}
        if style == "clock":
            return out
        if v is None:
            out.update(text="--", frac=0.0, missing=True)
            return out
        if style == "spark":
            out["text"], out["unit"] = _speed(v)
            hist = list(self.hist[kind])
            out["hist"] = hist
            out["frac"] = 0 if not hist else v / max(max(hist), 1)
            return out
        if unit == "°C":
            out["frac"] = (v - 30) / 70  # 30..100 °C
        elif kind == "gpu_power":
            out["frac"] = v / max(self.values.get("gpu_power_max", 300), 1)
        else:
            out["frac"] = v / 100
        out["frac"] = max(0.0, min(1.0, out["frac"]))
        out["text"] = f"{v:.0f}"
        return out

    def status(self) -> dict:
        return {
            "nvidia": self._nv is not None,
            "gpu_name": self.gpu_name,
            "lhm": self.lhm_ok,
            "available": {m[0]: (m[0] == "clock" or self.values.get(m[0]) is not None) for m in METRICS},
        }

    def summary(self, kinds) -> dict:
        res = {}
        for k in kinds:
            g = self.get(k)
            if g["style"] == "clock":
                res[k] = time.strftime("%H:%M")
            else:
                res[k] = f"{g.get('text', '--')}{g.get('unit', '')}" if not g.get("missing") else "--"
        return res


def _speed(bps: float):
    for unit, div in (("GB/s", 1024 ** 3), ("MB/s", 1024 ** 2), ("KB/s", 1024)):
        if bps >= div * 0.95:
            v = bps / div
            return (f"{v:.1f}" if v < 100 else f"{v:.0f}"), unit
    return f"{bps:.0f}", "B/s"
