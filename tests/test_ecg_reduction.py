"""Fast checks of the causal-reduction claims. Run from the repository root:
python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments"))
import ecg_causal_reduction as E  # noqa: E402
import harness  # noqa: E402


class ReductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t256 = E.response_table(256)

    def test_loading_matches_host_rules(self):
        g = harness.Graph()
        self.assertEqual(g.coupling, 1.0)                       # global_settings coupling = 100
        self.assertEqual(len(g.coupler.history), 0)             # history deque is not saved
        self.assertFalse(hasattr(g.split, "out_0_val"))         # splitter outputs are not restored
        self.assertAlmostEqual(g.coupler.output_value, 0.8739509815096245)

    def test_scalar_reduction_is_bit_exact(self):
        res = E.r3_equivalence(self.t256, ticks=400)
        self.assertIsNone(res["first_mismatch_tick"])
        self.assertEqual(res["max_abs_difference"], 0.0)

    def test_blindness_thresholds(self):
        self.assertEqual(E.blindness_threshold(self.t256), 64)
        self.assertEqual(E.blindness_threshold(E.response_table(1024)), 32)
        self.assertEqual(E.blindness_threshold(E.response_table(2048)), 23)

    def test_integral_state_is_dead_in_edge_of_chaos_mode(self):
        a = E.Reduced(self.t256, integral_state=-1e9)
        b = E.Reduced(self.t256, integral_state=1e9)
        for _ in range(300):
            self.assertEqual(a.step(), b.step())

    def test_clamped_feedback_stops_the_rhythm(self):
        sim = E.Reduced(self.t256)
        sim.clamp = (200, 1.0)
        out = [sim.step()[1] for _ in range(400)]
        self.assertEqual(np.ptp(out[-100:]), 0.0)

    def test_exact_cycle(self):
        tr, per, _ = E.find_cycle(E.Reduced(self.t256))
        self.assertEqual(per, 59)

    def test_september_receipt_is_the_one_tick_loop(self):
        self.assertEqual(E.find_cycle(E.Reduced(self.t256, delay=1, window=50))[1], 52)
        self.assertEqual(E.find_cycle(E.Reduced(self.t256, delay=1, window=30))[1], 32)

    def test_fixed_footprint_sensor_is_the_original_at_256(self):
        fp = E.response_table(256, sensor="fixed_footprint")
        self.assertTrue(all(fp[q] == self.t256[q] for q in E.Q_RANGE))


if __name__ == "__main__":
    unittest.main()
