import unittest

from core import (
    DEFAULT_A1_SEED,
    DEFAULT_A2_SEED,
    DEFAULT_POLYNOMIAL,
    algebraic_degrees,
    analyze_sbox,
    boomerang_uniformity,
    generate_sbox,
    is_irreducible_degree8,
)


class CoreCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.sbox = generate_sbox(
            DEFAULT_A1_SEED,
            "00101111",
            DEFAULT_A2_SEED,
            "00111000",
            DEFAULT_POLYNOMIAL,
        )

    def test_first_legacy_row_sbox_prefix(self):
        self.assertEqual(
            self.sbox[:16].tolist(),
            [129, 231, 247, 237, 185, 24, 252, 0, 80, 159, 111, 183, 157, 186, 201, 205],
        )

    def test_standard_metrics_match_supplied_dataset(self):
        m = analyze_sbox(self.sbox)
        self.assertEqual(m["Nonlinearity_Min"], 112.0)
        self.assertEqual(m["Nonlinearity_Max"], 112.0)
        self.assertAlmostEqual(m["Linear_Probability"], 0.0625)
        self.assertAlmostEqual(m["LAT_Max"], 144.0)
        self.assertAlmostEqual(m["SAC_Min"], 0.453125)
        self.assertAlmostEqual(m["SAC_Max"], 0.546875)
        self.assertAlmostEqual(m["SAC_Average"], 0.5)
        self.assertAlmostEqual(m["SAC_Square_Deviation"], 0.02485922277608956)
        self.assertEqual(m["Differential_Uniformity_Max"], 4)
        self.assertEqual(m["Cycle_Count"], 9)
        self.assertEqual(m["Cycle_Lengths"], [120, 28, 73, 24, 2, 6, 1, 1, 1])

    def test_advanced_metrics(self):
        dmin, dmax, _ = algebraic_degrees(self.sbox)
        self.assertEqual((dmin, dmax), (7, 7))
        self.assertEqual(boomerang_uniformity(self.sbox), 6)

    def test_polynomial(self):
        self.assertTrue(is_irreducible_degree8(DEFAULT_POLYNOMIAL))


if __name__ == "__main__":
    unittest.main()
