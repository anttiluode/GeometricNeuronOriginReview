"""The forgetting clock: follow-up to the ECG causal reduction (10 November 2026).

Run from the repository root:  python experiments/forgetting_clock.py      (about 5 minutes)
Writes results/forgetting_clock.json.

Everything here runs on the REDUCED loop that ecg_causal_reduction.py proved bit-exact:
    r_t   = F(q(o_{t-d}))                      the image branch as one table, d = 4 ticks of pipeline
    var_t = variance of the last W readings    W = 50
    o_t   = damp(r_t) if var_t > 0.1 else amplify(r_t, var_t)
The table F is produced by the archived nodes themselves (response_table), on a wider q range so
that kicked trajectories stay inside it.

F1  Mechanism and period law: where in the cycle each thing happens, and P = W + 2d + c on a grid.
F2  Attractors: random initial states (pipeline and window), how many distinct cycles.
F3  Phase response: one-tick kicks of the output at every phase, asymptotic phase shift.
F4  How sharp must forgetting be: boxcar window replaced by a soft-edged one of width k.
F5  Critical edge width k* against the loop delay d.
F6  Smoothing the staircase and the switch: is there a graded phase response anywhere?
"""
import copy
import json
import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ecg_causal_reduction as E  # noqa: E402

ROOT = E.ROOT
S, TARGET = 0.6, 0.1                  # effective setpoint (0.5 + 0.1 * constant 1), target variance
QMIN, QMAX = -200, 399


def wide_table(dim=256):
    old = E.Q_RANGE
    E.Q_RANGE = range(QMIN, QMAX + 1)
    try:
        return {q: float(v) for q, v in E.response_table(dim).items()}
    finally:
        E.Q_RANGE = old


def q_of(o):
    return int(5 + 50*(o or 0.1))


def damp(r):
    return S + (2/(1 + math.exp(-3*(r - S))) - 1)/3


def amplify(r, var):
    return S + math.tanh(2*(r - S)*(1 + 10*abs(var - TARGET)))


class Loop:
    """Exact reduced loop (same arithmetic as the archived coupler in edge_of_chaos mode)."""

    def __init__(self, T, d=4, W=50, o0=0.8739509815096245, pipe=None, hist=None):
        self.T, self.d, self.W = T, d, W
        self.hist = list(hist) if hist else []
        self.pipe = list(pipe) if pipe else [None]*(d - 1) + [o0]
        self.t = 0

    def step(self, kick=0.0):
        src = self.pipe[0]
        r = 0.0 if src is None else self.T[max(QMIN, min(QMAX, q_of(src)))]
        self.hist = (self.hist + [r])[-200:]
        var = float(np.var(self.hist[-self.W:])) if len(self.hist) > 10 else 0.0
        o, mode = (damp(r), -1) if var > TARGET else (amplify(r, var), 1)
        o += kick
        self.pipe = self.pipe[1:] + [o]
        self.t += 1
        return r, o, mode, var

    def state(self):
        return tuple(self.hist[-self.W:]), tuple(self.pipe)


def find_cycle(sim, max_ticks=20000):
    seen, trace = {}, []
    while sim.t < max_ticks:
        st = sim.state()
        if st in seen:
            p = sim.t - seen[st]
            return p, seen[st], trace[-p:]
        seen[st] = sim.t
        trace.append(sim.step())
    return None, None, trace


class SoftLoop:
    """Variants: soft-edged memory (width k), interpolated F, logistic switch (width eps)."""

    def __init__(self, T, k=0.0, smooth_f=False, eps=0.0, d=4, W=50, o0=0.8739509815096245):
        self.T, self.smooth_f, self.eps, self.d = T, smooth_f, eps, d
        L = int(W + 12*max(k, 0.01)) + 2
        ages = np.arange(L)
        self.w = 1/(1 + np.exp(np.clip((ages - (W - 0.5))/max(k, 1e-9), -60, 60)))
        self.L, self.buf, self.pipe, self.t = L, [], [None]*(d - 1) + [o0], 0

    def F(self, o):
        if not self.smooth_f:
            return self.T[max(QMIN, min(QMAX, q_of(o)))]
        x = max(QMIN, min(QMAX - 1, 5 + 50*(o if o != 0 else 0.1)))
        a = math.floor(x)
        return self.T[a]*(1 - (x - a)) + self.T[a + 1]*(x - a)

    def step(self, kick=0.0):
        src = self.pipe[0]
        r = 0.0 if src is None else self.F(src)
        self.buf = (self.buf + [r])[-self.L:]
        x = np.array(self.buf[::-1])
        w = self.w[:len(x)]
        mu = (w*x).sum()/w.sum()
        var = float((w*(x - mu)**2).sum()/w.sum()) if self.t >= 10 else 0.0
        g = (1.0 if var <= TARGET else 0.0) if self.eps == 0 else 1/(1 + math.exp(-(TARGET - var)/self.eps))
        o = (1 - g)*damp(r) + g*amplify(r, var) + kick
        self.pipe = self.pipe[1:] + [o]
        self.t += 1
        return r, o, var


def beat_times(rs, start=0):
    rs = np.asarray(rs)
    return np.where((rs[1:] > 2.5) & (rs[:-1] <= 2.5))[0] + 1 + start


# ---------------------------------------------------------------- F1
def f1_mechanism(T):
    p, transient, cyc = find_cycle(Loop(T))
    r = [c[0] for c in cyc]
    spikes = [i for i, v in enumerate(r) if v > 2.5]
    amp_ticks = [i for i, c in enumerate(cyc) if c[2] == 1]
    blind = [i for i, c in enumerate(cyc) if c[0] == 0.0]
    grid, exact, near, doubled = [], 0, 0, 0
    for W in range(20, 101, 5):
        for d in range(1, 13):
            pp, _, _ = find_cycle(Loop(T, d=d, W=W))
            c = pp - (W + 2*d)
            grid.append({"W": W, "d": d, "period": pp, "c": c})
            exact += (c == 1)
            near += (-1 <= c <= 4)
            doubled += (c > 4)
    return {"period": p, "transient": transient, "spike_ticks": spikes, "amplify_ticks": amp_ticks,
            "zero_reading_ticks": blind, "idle_square_sizes": sorted({q_of(c[1]) for c in cyc[5:35]}),
            "spike_readings": [r[i] for i in spikes],
            "grid_settings": len(grid), "grid_exact_W+2d+1": exact, "grid_c_in_[-1,4]": near,
            "grid_longer": doubled, "grid": grid}


# ---------------------------------------------------------------- F2
def f2_attractors(T, trials=3000, seed=0):
    rng = random.Random(seed)
    vals = list(T.values())
    found = {}
    for _ in range(trials):
        pipe = [rng.uniform(-0.5, 1.6) for _ in range(4)]
        hist = [rng.choice(vals) for _ in range(rng.choice([0, 50]))]
        p, _, cyc = find_cycle(Loop(T, pipe=pipe, hist=hist), max_ticks=6000)
        if p is None:
            key = "none"
        else:
            rs = [round(c[0], 6) for c in cyc]
            key = min(tuple(rs[i:] + rs[:i]) for i in range(len(rs)))
        found[key] = found.get(key, 0) + 1
    return {"trials": trials, "distinct_attractors": len(found),
            "periods": sorted({len(k) if k != "none" else 0 for k in found})}


# ---------------------------------------------------------------- F3
def f3_phase_response(T, amps=(1e-6, 1e-3, 0.01, 0.03, 0.1, 0.3, 1.0, -1e-3, -0.01, -0.03, -0.1, -0.3, -1.0)):
    ref = Loop(T)
    for _ in range(590):
        ref.step()
    base, idx = copy.deepcopy(ref), {}
    for i in range(59):
        idx[base.state()] = i
        base.step()
    out = {}
    for a in amps:
        shifts, relax = [], []
        for ph in range(59):
            s = copy.deepcopy(ref)
            for _ in range(ph):
                s.step()
            s.step(kick=a)
            for k in range(3000):
                st = s.state()
                if st in idx:
                    d = (idx[st] - (ph + 1 + k)) % 59
                    shifts.append(d if d <= 29 else d - 59)
                    relax.append(k)
                    break
                s.step()
        # full reset = shift falls by one tick per tick of phase (the kick restarts the clock)
        resets = sum(1 for i in range(1, 59) if (shifts[i] - shifts[i - 1]) % 59 == 58)
        out[repr(a)] = {"shift_by_phase": shifts, "phases_with_zero_shift": shifts.count(0),
                        "max_relax_ticks": max(relax), "consecutive_phase_pairs_with_slope_-1": resets}
    return out


# ---------------------------------------------------------------- F4, F5
def n_beats(T, k, d=4, n=9000, **kw):
    sim = SoftLoop(T, k=k, d=d, **kw)
    rs = [sim.step() for _ in range(n)]
    late = rs[n//2:]
    b = beat_times([x[0] for x in late])
    v = [x[2] for x in late]
    return len(b), (float(np.diff(b).mean()) if len(b) > 2 else None), float(min(v)), float(max(v)), \
        float(max(x[0] for x in late))


def f4_edge_width(T):
    rows = []
    for k in (0, 0.5, 1, 2, 3, 4, 6, 8, 9, 10, 12, 16, 25):
        nb, iv, vmin, vmax, rmax = n_beats(T, k)
        rows.append({"k": k, "beats_in_4500_ticks": nb, "mean_interval": iv, "var_min": vmin,
                     "var_max": vmax, "max_reading": rmax})
    return rows


def f5_critical_width(T):
    rows = []
    for d in (1, 2, 3, 4, 6, 8):
        last = None
        for k in [0.5*i for i in range(0, 61)]:
            if n_beats(T, k, d=d)[0] > 3:
                last = k
        rows.append({"d": d, "largest_k_that_beats": last})
    return rows


# ---------------------------------------------------------------- F6
def f6_smooth_variants(T):
    def run(kw, kick_at=None, a=0.0, n=14000):
        sim = SoftLoop(T, **kw)
        return [sim.step(kick=a if i == kick_at else 0.0)[0] for i in range(n)]
    out = []
    for name, kw in (("boxcar, staircase, hard switch (original)", dict(k=0)),
                     ("boxcar, interpolated F, hard switch", dict(k=0, smooth_f=True)),
                     ("soft edge 4, interpolated F, hard switch", dict(k=4, smooth_f=True)),
                     ("boxcar, interpolated F, soft switch 0.01", dict(k=0, smooth_f=True, eps=0.01)),
                     ("soft edge 4, interpolated F, soft switch 0.002", dict(k=4, smooth_f=True, eps=0.002)),
                     ("soft edge 4, interpolated F, soft switch 0.01", dict(k=4, smooth_f=True, eps=0.01))):
        ref = run(kw)
        b = beat_times(ref[8000:], 8000)
        isi = np.diff(b)
        shifts = {}
        for a in (1e-3, 1e-2, 3e-2):
            row = []
            for ph in range(0, 60, 10):
                pb = beat_times(run(kw, kick_at=3000 + ph, a=a)[8000:], 8000)
                row.append(float(np.mean(pb - b)) if len(pb) == len(b) else None)
            shifts[repr(a)] = row
        tiny = run(kw, kick_at=3000, a=1e-9)
        div = next((i - 3000 for i in range(3000, len(ref)) if abs(ref[i] - tiny[i]) > 0.5), None)
        out.append({"variant": name, "beats": len(b), "interval_mean": float(isi.mean()),
                    "interval_sd": float(isi.std()), "mean_beat_shift_after_kick": shifts,
                    "ticks_until_1e-9_kick_diverges": div})
    return out


def main():
    T = wide_table(256)
    res = {}
    for name, fn in (("F1_mechanism", f1_mechanism), ("F2_attractors", f2_attractors),
                     ("F3_phase_response", f3_phase_response), ("F4_edge_width", f4_edge_width),
                     ("F5_critical_width", f5_critical_width), ("F6_smooth_variants", f6_smooth_variants)):
        res[name] = fn(T)
        print(name, "done", flush=True)
    out = ROOT/"results"/"forgetting_clock.json"
    out.write_text(json.dumps(res, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
