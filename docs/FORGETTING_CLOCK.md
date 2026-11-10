# The forgetting clock

*10 November 2026. Built by Claude (Fable 5.2) at Antti's request, as a follow-up to the [causal reduction](CAUSAL_REDUCTION.md). Everything runs on the reduced loop that document proved bit-exact. Code: [`experiments/forgetting_clock.py`](../experiments/forgetting_clock.py). Numbers: [`results/forgetting_clock.json`](../results/forgetting_clock.json). The archived node files are unchanged.*

**Question:** the reduction showed *which parts* the rhythm needs. What is the rhythm, as a mechanism, and what kind of object is the loop?

**Answer:** the loop beats when it forgets its last beat. It is an excitable unit with a threshold, a refractory period and a reset. The beat exists only because the memory forgets abruptly: let the memory fade gradually and the same controller regulates quietly, with no pulse at all.

## 1. The beat, tick by tick

The README already had the clue: the pulse comes when old high-variance samples leave the window. Here is the full accounting on the 59-tick cycle.

| Ticks of the cycle | What happens |
|---|---|
| 49–50 | **The beat.** Two huge readings, 3.47 and 3.88, enter the 50-sample memory. |
| 51–40 (next cycle) | Variance sits near 0.39, far above the target 0.1. The controller damps. The loop idles, hopping between square sizes 43 and 48. |
| 40–41 | The two huge readings fall out of the window. Variance drops to 0.04. |
| 41–44 | Too calm, so the controller amplifies. The square size jumps to 78–84, into the blind zone. |
| 45–48 | Four ticks later the sensor reads **zero**. Zero is far below the setpoint 0.6, so the amplified output swings negative: square sizes −11 and −9. |
| 49–50 | Four ticks later the negative square sizes come back as the next two huge readings. |

So the period is **W + 1 + d + d** = 50 (memory) + 1 (noticing) + 4 (kick reaches the blind zone) + 4 (zero returns as a spike) = **59**.

**Check on a grid.** Over 204 settings (window 20–100, delay 1–12), the period equals W + 2d + c with c between −1 and +4 in **186**. In the other 18 the period is much longer (often about double). The small offset c drifts from 0 at short windows to 4 at long ones, because a longer window needs more samples to leave before the variance crosses the target.

Two readings of this:

- **The window is a refractory period.** While the last beat is remembered, no new beat can start.
- **Blindness is part of the stroke.** The earlier note said the rhythm *survives* blindness. More than that: every beat passes through the blind zone, and the zero reading is what fires the spike. Silence measured against a setpoint is a signal.

## 2. One attractor

From **3000** random initial states (random outputs in flight, random or empty window), every run ended on the **same** 59-tick cycle. The loop keeps no trace of where it started. After a transient, the only thing it remembers is where it is in the cycle.

## 3. Response to a kick: all or none

One extra push was added to the output for a single tick, at each of the 59 phases, and the lasting phase shift was measured after the loop returned to its cycle.

| Kick | Lasting effect |
|---|---|
| 0.000001 | None at any phase. Gone within 4 ticks: the staircase absorbs it. |
| ±0.001 to ±0.03 | None at any phase. Forgotten within about 110 ticks (two windows). |
| ±0.1 | None at 56 of 59 phases. |
| +0.3, +1.0 | Shift of one tick at 45 and 48 of 59 phases. |
| −1.0 | **Reset.** Over most of the cycle the clock restarts from the kick (43 of 58 neighbouring phase pairs show the full-reset slope). |

A strong negative kick produces a negative square size, hence a huge reading, hence a beat: a premature beat that resets the pacemaker. Small pushes are erased completely.

As a computational resource: **phase yes**, as a resettable timer with 59 positions (about six bits). **History no**: it is gone within three windows.

## 4. The beat needs abrupt forgetting

The archived controller uses a boxcar window: a reading counts fully for 50 ticks and then not at all. That hard edge was replaced by a soft one, weight = 1/(1 + exp((age − 50)/k)), where k is the width of the edge in ticks.

| Edge width k | Result |
|---|---|
| 0 to 8 | Beat survives. Period lengthens from 59 to 65. |
| 9 and above | **No beat.** Variance hovers between 0.09 and 0.17, right at the target. The largest reading is 1.44. |

With gradual forgetting the controller does what its docstring says: it holds the variance near the target with small corrections. With abrupt forgetting the variance collapses faster than the loop can respond, and the correction overshoots into a full beat.

**Prediction tested:** the critical width should scale with the loop's reaction time. It does.

| Loop delay d | 1 | 2 | 3 | 4 | 6 | 8 |
|---|---|---|---|---|---|---|
| Largest k that still beats | 1.5 | 4.0 | 5.5 | 8.0 | 13.5 | 19.5 |

The critical edge width is about **twice the loop delay**. The ECG pulse is what a slow feedback loop does when its memory drops something faster than the loop can react.

## 5. Looking for a graded response (not found)

The question behind this section: can a rhythm carry a learning signal? For that, a small nudge must leave a small, proportional phase shift. The original loop gives exactly zero (section 3). So the three hard elements were softened: the staircase (interpolated table), the switch (logistic blend of width ε), and the window edge (k = 4).

| Variant | Beat interval | Shift after small kicks |
|---|---|---|
| Original | 59, exact | 0 |
| Interpolated F | 59.5 ± 0.5 | 0 or 0.5: lumps, not proportional |
| Soft edge + interpolated F | 63.7 ± 0.5 | 0, ±0.33, 0.67: lumps |
| Interpolated F + soft switch (ε = 0.01) | 60, exact | 0, once −1 |
| All three soft, ε = 0.002 | 63.9 ± 0.5 | scattered; a kick of 10⁻⁹ changes the beat times after 836 ticks |
| All three soft, ε = 0.01 | 56 ± 20 | irregular beats; a kick of 10⁻⁹ diverges after 604 ticks |

In the variants tried, the loop is either **rigid** (it erases small pushes, or answers in fixed lumps) or **irregular** (it amplifies them without bound). No setting gave a smooth, proportional phase response. Six variants is a small search, so this is "not found", not "impossible".

## 6. What this does and does not show

**It shows:**

- the ECG look has a cause. Threshold, refractory period and reset are the defining features of an excitable cell, and this loop has all three.
- the mode name `edge_of_chaos` is accidentally apt: quiet regulation, a rigid beat, and irregular beating sit next to each other, separated by how sharply the memory forgets and how hard the switch is.
- "zero gradient" and "causally dead" are different things. The staircase has zero slope almost everywhere, so no infinitesimal sensitivity passes through this loop, yet a finite kick resets it.

**It does not show:**

- a neuron. There is no membrane, no cable, no geometry doing work: the picture is one lookup table.
- a synapse. A synapse sits *between* two units and its strength changes with their history. This is one closed unit, and nothing in it changes slowly with experience. The window resembles short-term recovery (readiness to respond again), not a learned weight.
- that rhythm can or cannot carry credit for learning. Section 5 only says this particular loop offers no graded handle.

## Reproduce

```bash
python experiments/forgetting_clock.py            # ~5 min, writes results/forgetting_clock.json
python -m unittest discover -s tests -v
```
