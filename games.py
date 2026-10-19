"""Mini games played on the six screens. Any round button or knob press quits."""
from __future__ import annotations

import queue
import random
import threading
import time

import render

COLORS = [(239, 68, 68), (34, 197, 94), (59, 130, 246), (234, 179, 8), (168, 85, 247), (6, 182, 212)]


class Game:
    name = "game"

    def __init__(self, core):
        self.core = core
        self.q: queue.Queue = queue.Queue()
        self.alive = True

    def start(self):
        threading.Thread(target=self._wrap, daemon=True).start()

    def _wrap(self):
        try:
            self.run()
        except Exception as e:
            print("Game error:", e)
        finally:
            self.core.end_game(self)

    def press(self, i):
        self.q.put(i)

    def stop(self):
        self.alive = False
        self.q.put(None)

    def wait(self, timeout):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return "timeout"

    def drain(self):
        while not self.q.empty():
            self.q.get_nowait()

    def sleep(self, s):
        end = time.time() + s
        while self.alive and time.time() < end:
            time.sleep(0.03)

    def show(self, tiles):
        if self.alive:
            self.core.show_tiles(tiles)

    def banner(self, lines, secs, rgb=True):
        self.show(render.banner(lines, self.core.accent(), rgb=rgb))
        self.sleep(secs)

    def countdown(self, title):
        self.banner([(title, 0, 0.42), ("ready", 1, 0.3)], 1.0)
        for n in ("3", "2", "1"):
            self.banner([(title, 0, 0.42), (n, 1, 0.5)], 0.55)

    def best(self, key, value, lower_is_better=False):
        b = self.core.cfg.setdefault("stats", {}).setdefault("best", {})
        old = b.get(key)
        if old is None or (value < old if lower_is_better else value > old):
            b[key] = value
            self.core.save()
            return value, True
        return old, False


class Simon(Game):
    name = "simon"

    def run(self):
        dim = [render.solid_glow(c, False) for c in COLORS]
        lit = [render.solid_glow(c, True) for c in COLORS]
        self.countdown("simon")
        seq = []
        while self.alive:
            seq.append(random.randrange(6))
            speed = max(0.22, 0.5 - len(seq) * 0.02)
            self.show(dim)
            self.sleep(0.5)
            for k in seq:  # watch
                if not self.alive:
                    return
                self.show([lit[i] if i == k else dim[i] for i in range(6)])
                self.sleep(speed)
                self.show(dim)
                self.sleep(0.12)
            self.drain()
            for want in seq:  # repeat
                got = self.wait(6)
                if got is None or not self.alive:
                    return
                if got == "timeout" or got != want:
                    return self.game_over(len(seq) - 1)
                self.show([lit[i] if i == got else dim[i] for i in range(6)])
                self.sleep(0.15)
                self.show(dim)
            self.sleep(0.35)

    def game_over(self, score):
        best, new = self.best("simon", score)
        self.core.emit({"t": "toast", "msg": f"Simon: you reached level {score}" + (". New best!" if new else f". Best is {best}.")})
        self.banner([("game over", 0, 0.34), (f"{score} best {best}", 1, 0.3)], 2.8)


class Reaction(Game):
    name = "reaction"

    def run(self):
        dark = [render.solid_glow((60, 60, 70), False) for _ in range(6)]
        go = render.solid_glow((34, 197, 94), True)
        self.countdown("react")
        times = []
        for _ in range(5):
            if not self.alive:
                return
            self.show(dark)
            self.drain()
            early = self.wait(random.uniform(1.0, 2.8))
            if early is None:
                return
            if early != "timeout":
                self.show([render.overlay_tile("msg", 0, text="TOO\nSOON") if i == early else dark[i] for i in range(6)])
                self.sleep(1.0)
                continue
            target = random.randrange(6)
            self.show([go if i == target else dark[i] for i in range(6)])
            t0 = time.time()
            got = self.wait(2.0)
            if got is None:
                return
            ms = int((time.time() - t0) * 1000)
            if got == target:
                times.append(ms)
                txt = f"{ms}\nms"
            else:
                txt = "MISS"
            where = target if got == "timeout" else got
            self.show([render.overlay_tile("msg", 0, text=txt) if i == where else dark[i] for i in range(6)])
            self.sleep(0.9)
        if not times:
            return self.banner([("no hits", 0, 0.36), ("try again", 1, 0.3)], 2.2)
        avg = int(sum(times) / len(times))
        best, new = self.best("reaction", avg, lower_is_better=True)
        self.core.emit({"t": "toast", "msg": f"Reaction: {avg} ms average" + (". New best!" if new else f". Best is {best} ms.")})
        self.banner([(f"{avg} ms", 0, 0.4), (f"best {best}", 1, 0.3)], 2.8)


GAMES = {"simon": Simon, "reaction": Reaction}
