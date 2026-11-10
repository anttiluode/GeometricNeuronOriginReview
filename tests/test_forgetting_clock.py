"""Fast checks of the forgetting-clock claims. Run from the repository root:
python -m unittest discover -s tests -v
"""
import copy
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))
import forgetting_clock as F  # noqa: E402


class ForgettingClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.T = F.wide_table(256)

    def test_period_is_window_plus_two_delays_plus_one(self):
        for W, d in ((50, 4), (45, 3), (50, 6), (40, 5)):
            self.assertEqual(F.find_cycle(F.Loop(self.T, d=d, W=W))[0], W + 2*d + 1)

    def test_zero_reading_precedes_the_beat_by_the_delay(self):
        _, _, cyc = F.find_cycle(F.Loop(self.T))
        r = [c[0] for c in cyc]
        first_spike = next(i for i, v in enumerate(r) if v > 2.5)
        self.assertEqual(r[first_spike - 4], 0.0)

    def test_single_attractor_from_random_starts(self):
        rng, keys = random.Random(1), set()
        for _ in range(150):
            pipe = [rng.uniform(-0.5, 1.6) for _ in range(4)]
            p, _, cyc = F.find_cycle(F.Loop(self.T, pipe=pipe), max_ticks=6000)
            rs = [round(c[0], 6) for c in cyc]
            keys.add(min(tuple(rs[i:] + rs[:i]) for i in range(len(rs))))
        self.assertEqual(len(keys), 1)

    def test_small_kick_leaves_no_phase_shift(self):
        ref = F.Loop(self.T)
        for _ in range(590):
            ref.step()
        a, b = copy.deepcopy(ref), copy.deepcopy(ref)
        a.step()
        b.step(kick=0.01)
        for _ in range(400):
            a.step()
            b.step()
        self.assertEqual(a.state(), b.state())

    def test_beat_needs_abrupt_forgetting(self):
        self.assertGreater(F.n_beats(self.T, 4, n=4000)[0], 10)
        self.assertEqual(F.n_beats(self.T, 12, n=4000)[0], 0)


if __name__ == "__main__":
    unittest.main()
