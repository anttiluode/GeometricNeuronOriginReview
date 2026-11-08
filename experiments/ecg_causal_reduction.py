"""ECG causal reduction: which parts of the ecg.json loop are needed for its rhythm?

Run from the repository root:  python experiments/ecg_causal_reduction.py
Writes results/ecg_causal_reduction.json and results/ecg_causal_reduction.png.

R1  Faithful reference: the saved graph loaded the way the host loads it, stepped with the host's
    scheduler (harness.py). Exact recurrence of the full causal state gives the true period.
R2  The image branch as one scalar function r = F_D(q) of the integer square size q, tabulated by
    running the archived nodes themselves. Blindness thresholds.
R3  Strict equivalence: the loop with the image branch replaced by the table, keeping the 4-tick
    pipeline and its initial buffers, compared bit for bit with the full loop.
R4  Interventions on the reduced loop: clamp the feedback, change only the delay, change only the
    variance window, perturb the dead integral state, change the vector dimension with the original
    sensor and with a fixed physical sensor footprint.
R5  Split test: permute the controller's 50-sample window (same multiset, same current input, so the
    same mean and variance) and see whether the future changes.
"""
import argparse
import json
import sys
from collections import deque
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

ROOT = harness.ROOT
DIMS = (256, 1024, 2048)
Q_RANGE = range(-60, 140)


# ---------------------------------------------------------------- R2: the scalar response function
def image_for_q(g, q):
    """Drive the archived CheckerboardNode with a size_in that yields exactly q."""
    v = q + 0.5 if q > 0 else (q - 0.5 if q < 0 else 0.5)    # int() truncates toward zero
    size_in = (v - 5)/50.0
    assert int(5 + size_in*50) == q
    g.board.pre_step()
    g.board.set_input("square_size", size_in, "signal", 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        g.board.step()
    return g.board.get_output("image")


def response_table(dim, coupling=1.0, sensor="original"):
    """F_D(q): the summed feedback the coupler would receive, computed with the archived nodes."""
    g = harness.Graph(overrides={3: {"output_dim": dim, "vector": np.zeros(dim, dtype=np.float32)}})
    table = {}
    for q in Q_RANGE:
        img = image_for_q(g, q)
        g.i2v.pre_step()
        g.i2v.set_input("image_in", img, "image")
        g.i2v.step()
        vec = g.i2v.get_output("vector_out")
        if sensor == "original":
            g.split.pre_step()
            g.split.set_input("spectrum_in", vec, "spectrum")
            g.split.step()
            four = [float(g.split.get_output(f"out_{i}")) for i in range(4)]
        else:                                    # fixed footprint: the four 16x16 blocks D=256 sees
            gray = np.mean(img, axis=2)
            blocks = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)[0, :4]
            side = int(np.ceil(np.sqrt(dim)))      # the same normalizer the D-dim vector used
            raw = cv2.resize(gray, (side, side), interpolation=cv2.INTER_AREA).flatten()[:dim]
            m = np.max(np.abs(raw))
            four = [float(np.float32(b)/np.float32(m)) if m > 0 else float(b) for b in blocks]
        table[q] = np.sum([v*coupling for v in four])
    return table


def blindness_threshold(table):
    """Smallest positive q from which F_D is zero for every larger q in range."""
    qs = [q for q in Q_RANGE if q > 0]
    thr = None
    for q in reversed(qs):
        if table[q] == 0.0:
            thr = q
        else:
            break
    return thr


# ---------------------------------------------------------------- reduced loop
class Reduced:
    """The archived coupler fed through a scalar table and an explicit pipeline delay."""

    def __init__(self, table, delay=4, window=None, integral_state=None, coupling=1.0, dim=256):
        g = harness.Graph(overrides={3: {"output_dim": dim}})
        self.c, self.const, self.coupling = g.coupler, g.const, coupling
        if window is not None:
            self.c.variance_window = window
        if integral_state is not None:
            self.c.integral_state = integral_state
        self.table, self.delay = table, delay
        self.outs = [float(self.c.output_value)]          # o_0 = restored output_value
        self.clamp = None
        self.tick = 0

    clip_size_in = False

    def q_of(self, o):
        size_in = o*self.coupling or 0.1
        if self.clip_size_in:                    # what the node's comment says, not what it does
            size_in = min(max(size_in, 0.0), 1.0)
        return int(5 + size_in*50)

    def step(self):
        self.tick += 1
        t = self.tick
        c = self.c
        c.pre_step()
        c.set_input("setpoint_mod", self.const.get_output("signal"), "signal", self.coupling)
        if self.clamp is not None and t >= self.clamp[0]:
            r = self.clamp[1]
        elif t - self.delay >= 0:
            r = self.table[self.q_of(self.outs[t - self.delay])]
        else:
            r = 0.0
        c.input_data["signal_in"].append(r)               # already the coupled four-way sum
        c.step()
        self.outs.append(float(c.output_value))
        return float(c.current_value), float(c.output_value), float(c.regime_value)

    def clone(self):
        """Copy the dynamic state (the coupler and the pipeline), sharing the constant source."""
        import copy
        new = copy.copy(self)
        new.c = copy.deepcopy(self.c)
        new.outs = list(self.outs)
        return new

    def state(self):
        w = self.c.variance_window
        return (tuple(list(self.c.history)[-w:]), tuple(self.outs[-self.delay:]))


def find_cycle(sim, max_ticks=20000):
    """Exact recurrence of (last W inputs, outputs in flight). Returns transient, period, trace."""
    seen, trace = {}, []
    for _ in range(max_ticks):
        trace.append(sim.step())
        if sim.tick > sim.c.variance_window + sim.delay:
            s = sim.state()
            if s in seen:
                return seen[s], sim.tick - seen[s], trace
            seen[s] = sim.tick
    return None, None, trace


def summarize_cycle(trace, transient, period):
    if period is None:
        return {"period": None}
    cyc = np.array(trace[transient:transient + period])
    return {"transient_ticks": int(transient), "period": int(period),
            "input_values_on_cycle": sorted({round(float(v), 6) for v in cyc[:, 0]}),
            "output_min_max": [float(cyc[:, 1].min()), float(cyc[:, 1].max())],
            "ticks_damping": int(np.sum(cyc[:, 2] < 0)), "ticks_amplifying": int(np.sum(cyc[:, 2] > 0))}


# ---------------------------------------------------------------- experiments
def r1_reference(ticks=3000):
    g = harness.Graph()
    rec = []
    for _ in range(ticks):
        g.step()
        rec.append(g.record())
    r = np.array([x["r"] for x in rec])
    q = np.array([x["q"] for x in rec])
    visual = None
    tail = r[-1000:]
    for p in range(1, 500):
        if np.array_equal(tail[p:], tail[:-p]):
            visual = p
            break
    return rec, {"loaded_state": {"coupling_strength": g.coupling, "mode": g.coupler.mode,
                                  "variance_window": g.coupler.variance_window,
                                  "effective_setpoint": 0.5 + 0.1*1.0*g.coupling,
                                  "restored_output_value": rec and 0.8739509815096245,
                                  "history_restored": False, "splitter_outputs_restored": False},
                 "first_ticks_r": [round(float(v), 6) for v in r[:12]],
                 "first_ticks_q": [int(v) for v in q[:12]],
                 "square_size_range_after_tick_500": [int(q[500:].min()), int(q[500:].max())],
                 "distinct_square_sizes_after_tick_500": sorted({int(v) for v in q[500:]}),
                 "visual_period_of_r_last_1000": visual}


def r3_equivalence(table, ticks=3000, dim=256):
    g = harness.Graph(overrides={3: {"output_dim": dim, "vector": np.zeros(dim, dtype=np.float32)}})
    red = Reduced(table, dim=dim)
    first, max_diff = None, 0.0
    for t in range(1, ticks + 1):
        g.step()
        full = (float(g.coupler.current_value), float(g.coupler.output_value), float(g.coupler.regime_value))
        mine = red.step()
        d = max(abs(a - b) for a, b in zip(full, mine))
        max_diff = max(max_diff, d)
        if d != 0.0 and first is None:
            first = t
    return {"ticks": ticks, "first_mismatch_tick": first, "max_abs_difference": max_diff}


def r4_interventions(tables, ref_period_inputs):
    out = {}
    t256 = tables[(256, "original")]
    tr, per, trace = find_cycle(Reduced(t256))
    out["baseline_D256"] = summarize_cycle(trace, tr, per)

    # integral state is never read in edge_of_chaos mode
    base = [Reduced(t256).step() for _ in range(0)]
    a, b, c0 = Reduced(t256, integral_state=-1e9), Reduced(t256, integral_state=1e9), Reduced(t256)
    same = all(a.step() == b.step() == c0.step() for _ in range(2000))
    out["integral_state_perturbed_to_pm_1e9_identical_trajectory"] = bool(same)
    del base

    # clamp the feedback
    clamps = {}
    for name, value in [("cycle_mean", float(np.mean(ref_period_inputs))), ("zero", 0.0),
                        ("max_input", float(np.max(ref_period_inputs)))]:
        sim = Reduced(t256)
        sim.clamp = (1000, value)
        tr_ = [sim.step() for _ in range(1400)]
        o = np.array([x[1] for x in tr_])
        settle = next((i + 1 for i in range(1000, 1400) if np.ptp(o[i:]) == 0.0), None)
        clamps[name] = {"clamp_value": value, "output_range_last_200": float(np.ptp(o[-200:])),
                        "ticks_after_clamp_until_constant": None if settle is None else settle - 1000,
                        "final_output": float(o[-1])}
    out["feedback_clamped_at_tick_1000"] = clamps

    # delay only
    out["delay_only"] = {}
    for d in [1, 2, 3, 4, 5, 6, 8, 12]:
        tr_, per_, trace_ = find_cycle(Reduced(t256, delay=d))
        s = summarize_cycle(trace_, tr_, per_)
        out["delay_only"][str(d)] = {k: s[k] for k in ("period", "transient_ticks") if k in s}

    # window only
    out["window_only"] = {}
    for w in [20, 30, 40, 50, 60, 70, 80]:
        tr_, per_, trace_ = find_cycle(Reduced(t256, window=w))
        s = summarize_cycle(trace_, tr_, per_)
        out["window_only"][str(w)] = {k: s[k] for k in ("period", "transient_ticks") if k in s}

    # the documented 0-1 range for the square-size input
    sim = Reduced(t256)
    sim.clip_size_in = True
    tr_, per_, trace_ = find_cycle(sim)
    s = summarize_cycle(trace_, tr_, per_)
    out["size_in_clipped_to_0_1"] = {k: s.get(k) for k in ("period", "transient_ticks", "ticks_damping",
                                                          "ticks_amplifying", "output_min_max")}

    # the September reconstruction used a one-tick loop
    out["one_tick_loop_reconstruction"] = {}
    for w in (50, 30):
        tr_, per_, trace_ = find_cycle(Reduced(t256, delay=1, window=w))
        out["one_tick_loop_reconstruction"][f"window_{w}"] = per_

    # dimension: original sensor vs fixed footprint
    out["dimension"] = {}
    for dim in DIMS:
        row = {}
        for sensor in ("original", "fixed_footprint"):
            tab = tables[(dim, sensor)]
            tr_, per_, trace_ = find_cycle(Reduced(tab, dim=dim))
            s = summarize_cycle(trace_, tr_, per_)
            cyc = trace_[tr_:tr_ + per_] if per_ else []
            sim = Reduced(tab, dim=dim)
            qs = []
            for _ in range(tr_ + per_ if per_ else 2000):
                qs.append(sim.q_of(sim.outs[-1]))
                sim.step()
            qcyc = qs[-per_:] if per_ else qs
            thr = blindness_threshold(tab)
            row[sensor] = {"period": s.get("period"), "transient_ticks": s.get("transient_ticks"),
                           "square_sizes_on_cycle": sorted(set(qcyc)),
                           "blindness_threshold": thr,
                           "fraction_of_cycle_in_blind_region": (float(np.mean([q >= thr for q in qcyc]))
                                                                 if thr else 0.0),
                           "ticks_damping": s.get("ticks_damping"), "ticks_amplifying": s.get("ticks_amplifying")}
            del cyc
        out["dimension"][str(dim)] = row
    return out


def r5_split(table, n_perm=200, horizon=300, seed=0):
    """Permute the window (keep its last sample) on the attractor; does the future change?"""
    rng = np.random.default_rng(seed)
    tr, per, _ = find_cycle(Reduced(table))
    results = []
    for phase in range(0, per, max(1, per//6)):
        base = Reduced(table)
        for _ in range(tr + per + phase):
            base.step()
        w = base.c.variance_window
        window = list(base.c.history)[-w:]
        ref = base.clone()
        ref_future = [ref.step() for _ in range(horizon)]
        changed = distinct = 0
        first_div = []
        tried = set()
        for _ in range(n_perm):
            head = window[:-1]
            perm = [head[i] for i in rng.permutation(len(head))] + [window[-1]]
            key = tuple(perm)
            if key == tuple(window) or key in tried:
                continue
            tried.add(key)
            distinct += 1
            sim = base.clone()
            sim.c.history = deque(list(sim.c.history)[:-w] + perm, maxlen=200)
            fut = [sim.step() for _ in range(horizon)]
            div = next((i for i, (x, y) in enumerate(zip(fut, ref_future))
                        if x[2] != y[2] or max(abs(x[0] - y[0]), abs(x[1] - y[1])) > 1e-9), None)
            if div is not None:
                changed += 1
                first_div.append(div)
        results.append({"phase": phase, "distinct_permutations": distinct, "futures_changed": changed,
                        "median_ticks_to_divergence": float(np.median(first_div)) if first_div else None,
                        "window_mean": float(np.mean(window)), "window_var": float(np.var(window))})
    return {"note": ("same multiset and same last sample, so same current input, mean and variance; "
                     "divergence = a different regime or a difference above 1e-9"),
            "phases": results}


def plot(tables, rec, interventions, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(12, 8))
    qs = list(Q_RANGE)
    for dim, col in zip(DIMS, ["#1f77b4", "#d62728", "#2ca02c"]):
        ax[0, 0].step(qs, [tables[(dim, "original")][q] for q in qs], where="post", color=col, label=f"D={dim}")
    ax[0, 0].set(title="The whole image branch: r = F_D(q)", xlabel="square size q", ylabel="summed feedback r",
                 xlim=(-20, 100))
    ax[0, 0].legend()
    r = [x["r"] for x in rec][-180:]
    o = [x["o"] for x in rec][-180:]
    ax[0, 1].plot(r, label="feedback r (input)", lw=1)
    ax[0, 1].plot(o, label="coupler output", lw=1.5)
    ax[0, 1].set(title=f"Faithful reload of ecg.json (period {interventions['baseline_D256']['period']})",
                 xlabel="last 180 ticks")
    ax[0, 1].legend(fontsize=8)
    w = interventions["window_only"]
    ax[1, 0].plot([int(k) for k in w], [v["period"] for v in w.values()], "o-", label="window only (delay 4)")
    ax[1, 0].plot([int(k) for k in w], [int(k) + 9 for k in w], ":", color="gray", label="window + 9 (guide)")
    ax[1, 0].set(title="Period vs controller window", xlabel="variance window", ylabel="period (ticks)")
    ax[1, 0].legend(fontsize=8)
    d = interventions["delay_only"]
    ax[1, 1].plot([int(k) for k in d], [v["period"] for v in d.values()], "s-")
    ax[1, 1].set(title="Period vs pipeline delay (window 50)", xlabel="delay (ticks)", ylabel="period (ticks)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT/"results"/"ecg_causal_reduction.json")
    args = ap.parse_args()
    tables = {(d, s): response_table(d, sensor=s) for d in DIMS for s in ("original", "fixed_footprint")}
    rec, r1 = r1_reference()
    tr, per, trace = find_cycle(Reduced(tables[(256, "original")]))
    cyc_inputs = [x[0] for x in trace[tr:tr + per]]
    res = {"R1_reference": r1,
           "R2_response_function": {
               str(d): {"blindness_threshold_positive_q": blindness_threshold(tables[(d, "original")]),
                        "distinct_values": len({round(float(v), 9) for v in tables[(d, "original")].values()}),
                        "F_at_q": {str(q): float(tables[(d, "original")][q])
                                   for q in [-14, -5, 5, 10, 23, 32, 48, 64, 81, 84]}}
               for d in DIMS},
           "R2_fixed_footprint_equals_original_at_D256": all(
               tables[(256, "fixed_footprint")][q] == tables[(256, "original")][q] for q in Q_RANGE),
           "R3_equivalence": {str(d): r3_equivalence(tables[(d, "original")], dim=d) for d in DIMS},
           "R4_interventions": r4_interventions(tables, cyc_inputs),
           "R5_split_test": r5_split(tables[(256, "original")])}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(res, indent=2) + "\n")
    plot(tables, rec, res["R4_interventions"], args.out.with_suffix(".png"))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
