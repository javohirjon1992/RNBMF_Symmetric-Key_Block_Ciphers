# Methodology Notes

## RNBMF S-box construction

The implemented construction is

`S(x) = A2(Inv_m(A1*x XOR b1)) XOR b2`,

where `A1` and `A2` are nonsingular 8x8 binary matrices derived from cyclic shifts of 64-bit seeds, `b1` and `b2` are 8-bit affine constants, and `Inv_m` denotes multiplicative inversion in GF(2^8) defined by the selected irreducible polynomial, with zero mapped to zero.

## Matrix-family validation

For each seed, the software generates all 64 cyclic matrix realizations and checks nonsingularity over GF(2). A seed is accepted only when every required matrix is nonsingular.

## Reported cryptographic metrics

The software can evaluate:

- component and vectorial nonlinearity;
- maximum Walsh/LAT-related values and linear approximation probability;
- Strict Avalanche Criterion statistics;
- differential uniformity;
- permutation cycle structure;
- component algebraic degree;
- Boomerang Connectivity Table and boomerang uniformity.

## Interpretation

Metrics computed for an isolated S-box characterize the substitution layer. They do not by themselves establish the security of a complete block cipher. Full-cipher resistance depends additionally on the linear layer, round function, key schedule, number of rounds, and trail propagation across rounds.

## Reproducibility recommendation

For publication experiments, retain the exact seeds, rotation offsets, affine constants, irreducible polynomial, software version, and exported CSV files. For population-level experiments, report sample size and summary statistics instead of only selected best-performing instances.
