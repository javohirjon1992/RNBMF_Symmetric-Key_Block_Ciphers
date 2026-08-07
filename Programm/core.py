"""Core RNBMF dynamic 8x8 S-box generation and cryptographic analysis.

This module is intentionally UI-independent so it can be reused from scripts,
notebooks, tests, or the desktop interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import ast
import csv
import json
import random
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np


CSV_COLUMNS = [
    "A1_Binary_Matrix",
    "A1_Matrix_Rotation_Offset",
    "b1_Binary_Constant",
    "A2_Binary_Matrix",
    "A2_Matrix_Rotation_Offset",
    "b2_Binary_Constant",
    "GF_2_8_Irreducible_Polynomial",
    "Calculated_S_Box",
    "Nonlinearity_Max",
    "Nonlinearity_Min",
    "Nonlinearity_N_S",
    "Linear_Probability",
    "LAT_Max",
    "SAC_Min",
    "SAC_Max",
    "SAC_Average",
    "SAC_Square_Deviation",
    "Differential_Uniformity_Max",
    "Fixed_Points_Hex",
    "Opposite_Fixed_Points_Hex",
    "Fixed_Point_Count",
    "Cycle_Count",
    "Cycle_Lengths",
    "Generation_Date",
    "Generation_Time",
]

EXTENDED_COLUMNS = CSV_COLUMNS + [
    "Algebraic_Degree_Min",
    "Algebraic_Degree_Max",
    "Boomerang_Uniformity",
    "Is_Bijective",
    "Minimum_Cycle_Length",
]

DEFAULT_A1_SEED = "1101011101011001011001001100000111010000110101101111011100000101"
DEFAULT_A2_SEED = "1100011010011011101011110010100001110011000011101000110110101010"
DEFAULT_POLYNOMIAL = "111100111"
AES_POLYNOMIAL = "100011011"

PARITY_TABLE = np.array([i.bit_count() & 1 for i in range(256)], dtype=np.uint8)
HAMMING_WEIGHT = np.array([i.bit_count() for i in range(256)], dtype=np.uint8)


@dataclass
class GenerationConfig:
    a1_seed: str = DEFAULT_A1_SEED
    a2_seed: str = DEFAULT_A2_SEED
    polynomial: str = DEFAULT_POLYNOMIAL
    iterations: int = 100
    offset_mode: str = "Random"  # Random, Fixed, Sequential
    fixed_k1: int = 0
    fixed_k2: int = 0
    b1_mode: str = "Random"  # Random, Fixed
    b2_mode: str = "Random"
    fixed_b1: str = "00000000"
    fixed_b2: str = "00000000"
    random_seed: Optional[int] = None
    compute_advanced: bool = False
    only_matching: bool = False
    min_nonlinearity: float = 0.0
    max_du: int = 256
    sac_min_lower: float = 0.0
    sac_max_upper: float = 1.0
    max_sac_deviation: float = 1.0
    min_cycle_length: int = 1
    require_bijective: bool = True
    require_nonsingular_matrices: bool = True


def validate_binary_string(value: str, length: int, name: str) -> str:
    value = value.strip().replace(" ", "")
    if len(value) != length or any(ch not in "01" for ch in value):
        raise ValueError(f"{name} must contain exactly {length} binary digits.")
    return value


def shift_left(bits: str, k: int) -> str:
    bits = str(bits)
    if not bits:
        return bits
    k %= len(bits)
    return bits[k:] + bits[:k]


def bits_to_matrix(bits: str) -> np.ndarray:
    bits = validate_binary_string(bits, 64, "Matrix")
    return np.array([int(c) for c in bits], dtype=np.uint8).reshape(8, 8)


def gf2_rank(matrix: np.ndarray) -> int:
    a = np.asarray(matrix, dtype=np.uint8).copy() & 1
    rows, cols = a.shape
    rank = 0
    for col in range(cols):
        pivot = None
        for row in range(rank, rows):
            if a[row, col]:
                pivot = row
                break
        if pivot is None:
            continue
        if pivot != rank:
            a[[rank, pivot]] = a[[pivot, rank]]
        for row in range(rows):
            if row != rank and a[row, col]:
                a[row] ^= a[rank]
        rank += 1
        if rank == rows:
            break
    return rank


def matrix_is_nonsingular(bits: str) -> bool:
    return gf2_rank(bits_to_matrix(bits)) == 8


def validate_rnbmf_seed(seed: str) -> dict:
    seed = validate_binary_string(seed, 64, "RNBMF seed")
    bad_offsets = []
    ranks = []
    for k in range(64):
        rank = gf2_rank(bits_to_matrix(shift_left(seed, k)))
        ranks.append(rank)
        if rank != 8:
            bad_offsets.append(k)
    return {
        "valid": not bad_offsets,
        "bad_offsets": bad_offsets,
        "ranks": ranks,
        "nonsingular_count": 64 - len(bad_offsets),
    }


def poly_degree(p: int) -> int:
    return p.bit_length() - 1


def poly_mod(dividend: int, divisor: int) -> int:
    dd = poly_degree(divisor)
    value = dividend
    while value and poly_degree(value) >= dd:
        value ^= divisor << (poly_degree(value) - dd)
    return value


def is_irreducible_degree8(poly_bits: str) -> bool:
    """Brute-force irreducibility test for a monic degree-8 GF(2) polynomial."""
    poly_bits = validate_binary_string(poly_bits, 9, "Irreducible polynomial")
    p = int(poly_bits, 2)
    if not (p & (1 << 8)) or not (p & 1):
        return False
    # A degree-8 reducible polynomial must have a factor of degree <= 4.
    for deg in range(1, 5):
        start = (1 << deg) | 1  # monic and nonzero constant term
        end = 1 << (deg + 1)
        for q in range(start, end, 2):
            if poly_degree(q) == deg and poly_mod(p, q) == 0:
                return False
    return True


def gf_mul(a: int, b: int, modulus: int) -> int:
    a &= 0xFF
    b &= 0xFF
    result = 0
    reduction = modulus & 0xFF
    for _ in range(8):
        if b & 1:
            result ^= a
        b >>= 1
        high = a & 0x80
        a = (a << 1) & 0xFF
        if high:
            a ^= reduction
    return result


def gf_pow(a: int, exponent: int, modulus: int) -> int:
    result = 1
    base = a & 0xFF
    while exponent:
        if exponent & 1:
            result = gf_mul(result, base, modulus)
        base = gf_mul(base, base, modulus)
        exponent >>= 1
    return result


@lru_cache(maxsize=64)
def inverse_table(polynomial: str) -> np.ndarray:
    polynomial = validate_binary_string(polynomial, 9, "Irreducible polynomial")
    if not is_irreducible_degree8(polynomial):
        raise ValueError(f"Polynomial {polynomial} is not irreducible of degree 8 over GF(2).")
    modulus = int(polynomial, 2)
    table = np.zeros(256, dtype=np.uint8)
    for x in range(1, 256):
        table[x] = gf_pow(x, 254, modulus)
    return table


def affine_transform(matrix_bits: str, x: int, constant_bits: str) -> int:
    matrix_bits = validate_binary_string(matrix_bits, 64, "Affine matrix")
    constant_bits = validate_binary_string(constant_bits, 8, "Affine constant")
    matrix_int = int(matrix_bits, 2)
    constant = int(constant_bits, 2)
    y = 0
    for i in reversed(range(8)):
        row = (matrix_int >> (8 * i)) & 0xFF
        bit = (row & int(x)).bit_count() & 1
        y ^= bit << i
    return y ^ constant


def generate_sbox(a1_bits: str, b1_bits: str, a2_bits: str, b2_bits: str, polynomial: str) -> np.ndarray:
    a1_bits = validate_binary_string(a1_bits, 64, "A1 matrix")
    a2_bits = validate_binary_string(a2_bits, 64, "A2 matrix")
    b1_bits = validate_binary_string(b1_bits, 8, "b1")
    b2_bits = validate_binary_string(b2_bits, 8, "b2")
    inv = inverse_table(polynomial)
    a1_int = int(a1_bits, 2)
    a2_int = int(a2_bits, 2)
    b1 = int(b1_bits, 2)
    b2 = int(b2_bits, 2)
    out = np.empty(256, dtype=np.uint8)
    for x in range(256):
        y = 0
        for i in reversed(range(8)):
            row = (a1_int >> (8 * i)) & 0xFF
            y ^= (((row & x).bit_count() & 1) << i)
        y ^= b1
        y = int(inv[y])
        z = 0
        for i in reversed(range(8)):
            row = (a2_int >> (8 * i)) & 0xFF
            z ^= (((row & y).bit_count() & 1) << i)
        out[x] = z ^ b2
    return out


def _fwht_rows(array: np.ndarray) -> np.ndarray:
    a = np.asarray(array, dtype=np.int16).copy()
    n = a.shape[1]
    h = 1
    while h < n:
        for start in range(0, n, h * 2):
            left = a[:, start:start + h].copy()
            right = a[:, start + h:start + 2 * h].copy()
            a[:, start:start + h] = left + right
            a[:, start + h:start + 2 * h] = left - right
        h *= 2
    return a


def component_nonlinearities(sbox: Iterable[int]) -> np.ndarray:
    s = np.asarray(list(sbox), dtype=np.uint8)
    if s.size != 256:
        raise ValueError("An 8-bit S-box must contain 256 values.")
    masks = np.arange(1, 256, dtype=np.uint16)[:, None]
    values = s.astype(np.uint16)[None, :]
    bits = PARITY_TABLE[(values & masks).astype(np.uint8)]
    signs = 1 - 2 * bits.astype(np.int16)
    walsh = _fwht_rows(signs)
    return 128.0 - np.max(np.abs(walsh), axis=1) / 2.0


def nonlinearity_metrics(sbox: Iterable[int]) -> tuple[float, float, float]:
    nl = component_nonlinearities(sbox)
    # The legacy dataset's Nonlinearity_N_S equals the minimum vectorial component NL.
    return float(nl.max()), float(nl.min()), float(nl.min())


def linear_probability_metrics(sbox: Iterable[int]) -> tuple[float, float, int]:
    s = np.asarray(list(sbox), dtype=np.uint8)
    masks = np.arange(0, 256, dtype=np.uint16)[:, None]
    values = s.astype(np.uint16)[None, :]
    bits = PARITY_TABLE[(values & masks).astype(np.uint8)]
    signs = 1 - 2 * bits.astype(np.int16)
    walsh = _fwht_rows(signs)
    walsh[0, 0] = 0
    max_abs = int(np.max(np.abs(walsh)))
    correlation = max_abs / 256.0
    linear_probability = correlation / 2.0
    lat_max = (linear_probability + 0.5) * 256.0
    return float(linear_probability), float(lat_max), max_abs


def sac_matrix(sbox: Iterable[int]) -> np.ndarray:
    s = np.asarray(list(sbox), dtype=np.uint8)
    x = np.arange(256, dtype=np.uint16)
    result = np.empty((8, 8), dtype=np.float64)
    for input_bit in range(8):
        diff = (s[x] ^ s[x ^ (1 << input_bit)]).astype(np.uint8)
        for output_bit in range(8):
            result[input_bit, output_bit] = np.mean((diff >> output_bit) & 1)
    return result


def differential_uniformity(sbox: Iterable[int]) -> int:
    s = np.asarray(list(sbox), dtype=np.uint8)
    x = np.arange(256, dtype=np.uint16)
    maximum = 0
    for a in range(1, 256):
        diff = (s[x] ^ s[x ^ a]).astype(np.uint8)
        maximum = max(maximum, int(np.bincount(diff, minlength=256).max()))
    return maximum


def fixed_points(sbox: Iterable[int]) -> list[int]:
    s = np.asarray(list(sbox), dtype=np.uint8)
    return np.nonzero(s == np.arange(256, dtype=np.uint8))[0].astype(int).tolist()


def opposite_fixed_points(sbox: Iterable[int]) -> list[int]:
    s = np.asarray(list(sbox), dtype=np.uint8)
    return np.nonzero(s == (255 - np.arange(256, dtype=np.uint16)))[0].astype(int).tolist()


def cycle_stats(sbox: Iterable[int]) -> tuple[int, list[int]]:
    s = np.asarray(list(sbox), dtype=np.uint16)
    if len(set(map(int, s.tolist()))) != 256:
        return 0, []
    visited = np.zeros(256, dtype=bool)
    lengths: list[int] = []
    for start in range(256):
        if visited[start]:
            continue
        current = start
        length = 0
        while not visited[current]:
            visited[current] = True
            length += 1
            current = int(s[current])
        lengths.append(length)
    return len(lengths), lengths


def algebraic_degrees(sbox: Iterable[int]) -> tuple[int, int, list[int]]:
    s = np.asarray(list(sbox), dtype=np.uint8)
    masks = np.arange(1, 256, dtype=np.uint16)[:, None]
    anf = PARITY_TABLE[(s.astype(np.uint16)[None, :] & masks).astype(np.uint8)].copy()
    for bit in range(8):
        step = 1 << bit
        for x in range(256):
            if x & step:
                anf[:, x] ^= anf[:, x ^ step]
    degrees: list[int] = []
    for row in anf:
        support = np.nonzero(row)[0]
        degrees.append(int(HAMMING_WEIGHT[support].max()) if support.size else 0)
    return min(degrees), max(degrees), degrees


def boomerang_uniformity(sbox: Iterable[int]) -> int:
    """Compute the maximum nontrivial BCT entry for a bijective 8-bit S-box."""
    s = np.asarray(list(sbox), dtype=np.uint8)
    if len(set(map(int, s.tolist()))) != 256:
        raise ValueError("Boomerang uniformity requires a bijective S-box.")
    inverse = np.empty(256, dtype=np.uint16)
    inverse[s.astype(np.int64)] = np.arange(256, dtype=np.uint16)
    x = np.arange(256, dtype=np.uint16)
    a_values = np.arange(1, 256, dtype=np.uint16)[:, None]
    x_matrix = x[None, :]
    maximum = 0
    for b in range(1, 256):
        transformed = inverse[s.astype(np.uint16) ^ b]
        values = transformed[x_matrix] ^ transformed[x_matrix ^ a_values]
        counts = np.sum(values == a_values, axis=1)
        maximum = max(maximum, int(counts.max()))
    return maximum


def parse_sbox(value) -> list[int]:
    if isinstance(value, np.ndarray):
        return value.astype(int).tolist()
    if isinstance(value, (list, tuple)):
        return [int(v) for v in value]
    text = str(value).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = ast.literal_eval(text)
    if not isinstance(parsed, (list, tuple)) or len(parsed) != 256:
        raise ValueError("Calculated_S_Box must contain exactly 256 integer values.")
    values = [int(v) for v in parsed]
    if any(v < 0 or v > 255 for v in values):
        raise ValueError("S-box values must be in the range 0..255.")
    return values


def analyze_sbox(sbox: Iterable[int], compute_advanced: bool = False) -> dict:
    s = np.asarray(list(sbox), dtype=np.uint8)
    nl_max, nl_min, nl_s = nonlinearity_metrics(s)
    lp, lat_max, walsh_max = linear_probability_metrics(s)
    sac = sac_matrix(s)
    du = differential_uniformity(s)
    fp = fixed_points(s)
    ofp = opposite_fixed_points(s)
    is_bijective = len(set(map(int, s.tolist()))) == 256
    cycle_count, cycle_lengths = cycle_stats(s) if is_bijective else (0, [])
    result = {
        "Nonlinearity_Max": nl_max,
        "Nonlinearity_Min": nl_min,
        "Nonlinearity_N_S": nl_s,
        "Linear_Probability": lp,
        "LAT_Max": lat_max,
        "Walsh_Max_Abs": walsh_max,
        "SAC_Min": float(np.min(sac)),
        "SAC_Max": float(np.max(sac)),
        "SAC_Average": float(np.mean(sac)),
        # Kept under the legacy CSV field name for compatibility. The original code used std().
        "SAC_Square_Deviation": float(np.std(sac, ddof=0)),
        "Differential_Uniformity_Max": du,
        "Fixed_Points_Hex": [f"{v:02x}" for v in fp],
        "Opposite_Fixed_Points_Hex": [f"{v:02x}" for v in ofp],
        "Fixed_Point_Count": len(fp) + len(ofp),
        "Cycle_Count": cycle_count,
        "Cycle_Lengths": cycle_lengths,
        "Minimum_Cycle_Length": min(cycle_lengths) if cycle_lengths else 0,
        "Is_Bijective": is_bijective,
        "SAC_Matrix": sac,
    }
    if compute_advanced and is_bijective:
        deg_min, deg_max, degrees = algebraic_degrees(s)
        result.update({
            "Algebraic_Degree_Min": deg_min,
            "Algebraic_Degree_Max": deg_max,
            "Component_Algebraic_Degrees": degrees,
            "Boomerang_Uniformity": boomerang_uniformity(s),
        })
    else:
        result.update({
            "Algebraic_Degree_Min": "",
            "Algebraic_Degree_Max": "",
            "Component_Algebraic_Degrees": [],
            "Boomerang_Uniformity": "",
        })
    return result


def _random_binary_byte(rng: random.Random) -> str:
    return f"{rng.randrange(256):08b}"


def _candidate_matches(metrics: dict, config: GenerationConfig) -> bool:
    if config.require_bijective and not metrics["Is_Bijective"]:
        return False
    if float(metrics["Nonlinearity_Min"]) < config.min_nonlinearity:
        return False
    if int(metrics["Differential_Uniformity_Max"]) > config.max_du:
        return False
    if float(metrics["SAC_Min"]) < config.sac_min_lower:
        return False
    if float(metrics["SAC_Max"]) > config.sac_max_upper:
        return False
    if float(metrics["SAC_Square_Deviation"]) > config.max_sac_deviation:
        return False
    if metrics["Minimum_Cycle_Length"] < config.min_cycle_length:
        return False
    return True


def validate_config(config: GenerationConfig) -> None:
    validate_binary_string(config.a1_seed, 64, "A1 seed")
    validate_binary_string(config.a2_seed, 64, "A2 seed")
    validate_binary_string(config.polynomial, 9, "Irreducible polynomial")
    if not is_irreducible_degree8(config.polynomial):
        raise ValueError("The selected polynomial is not irreducible over GF(2).")
    if config.b1_mode == "Fixed":
        validate_binary_string(config.fixed_b1, 8, "b1")
    if config.b2_mode == "Fixed":
        validate_binary_string(config.fixed_b2, 8, "b2")
    if config.iterations < 1:
        raise ValueError("Iterations must be at least 1.")


def generate_candidate(config: GenerationConfig, rng: random.Random, index: int = 0) -> tuple[dict, bool]:
    if config.offset_mode == "Fixed":
        k1, k2 = config.fixed_k1 % 64, config.fixed_k2 % 64
    elif config.offset_mode == "Sequential":
        k1, k2 = index % 64, (index // 64) % 64
    else:
        k1, k2 = rng.randrange(64), rng.randrange(64)

    a1 = shift_left(config.a1_seed, k1)
    a2 = shift_left(config.a2_seed, k2)

    if config.require_nonsingular_matrices:
        if not matrix_is_nonsingular(a1) or not matrix_is_nonsingular(a2):
            return {}, False

    b1 = config.fixed_b1 if config.b1_mode == "Fixed" else _random_binary_byte(rng)
    b2 = config.fixed_b2 if config.b2_mode == "Fixed" else _random_binary_byte(rng)

    sbox = generate_sbox(a1, b1, a2, b2, config.polynomial)
    metrics = analyze_sbox(sbox, compute_advanced=config.compute_advanced)
    now = datetime.now()
    row = {
        "A1_Binary_Matrix": a1,
        "A1_Matrix_Rotation_Offset": k1,
        "b1_Binary_Constant": b1,
        "A2_Binary_Matrix": a2,
        "A2_Matrix_Rotation_Offset": k2,
        "b2_Binary_Constant": b2,
        "GF_2_8_Irreducible_Polynomial": config.polynomial,
        "Calculated_S_Box": json.dumps(sbox.astype(int).tolist(), separators=(",", ":")),
        "Nonlinearity_Max": metrics["Nonlinearity_Max"],
        "Nonlinearity_Min": metrics["Nonlinearity_Min"],
        "Nonlinearity_N_S": metrics["Nonlinearity_N_S"],
        "Linear_Probability": metrics["Linear_Probability"],
        "LAT_Max": metrics["LAT_Max"],
        "SAC_Min": metrics["SAC_Min"],
        "SAC_Max": metrics["SAC_Max"],
        "SAC_Average": metrics["SAC_Average"],
        "SAC_Square_Deviation": metrics["SAC_Square_Deviation"],
        "Differential_Uniformity_Max": metrics["Differential_Uniformity_Max"],
        "Fixed_Points_Hex": json.dumps(metrics["Fixed_Points_Hex"]),
        "Opposite_Fixed_Points_Hex": json.dumps(metrics["Opposite_Fixed_Points_Hex"]),
        "Fixed_Point_Count": metrics["Fixed_Point_Count"],
        "Cycle_Count": metrics["Cycle_Count"],
        "Cycle_Lengths": json.dumps(metrics["Cycle_Lengths"]),
        "Generation_Date": now.strftime("%Y-%m-%d"),
        "Generation_Time": now.strftime("%H:%M:%S"),
        "Algebraic_Degree_Min": metrics["Algebraic_Degree_Min"],
        "Algebraic_Degree_Max": metrics["Algebraic_Degree_Max"],
        "Boomerang_Uniformity": metrics["Boomerang_Uniformity"],
        "Is_Bijective": metrics["Is_Bijective"],
        "Minimum_Cycle_Length": metrics["Minimum_Cycle_Length"],
        "_SAC_Matrix": metrics["SAC_Matrix"],
    }
    return row, _candidate_matches(metrics, config)


def generate_batch(
    config: GenerationConfig,
    on_result: Optional[Callable[[dict, bool, int, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> list[dict]:
    validate_config(config)
    rng = random.Random(config.random_seed)
    rows: list[dict] = []
    for i in range(config.iterations):
        if should_stop and should_stop():
            break
        row, matched = generate_candidate(config, rng, i)
        if not row:
            if on_result:
                on_result({}, False, i + 1, config.iterations)
            continue
        if matched or not config.only_matching:
            rows.append(row)
        if on_result:
            on_result(row, matched, i + 1, config.iterations)
    return rows


def row_for_csv(row: dict, extended: bool = False) -> dict:
    columns = EXTENDED_COLUMNS if extended else CSV_COLUMNS
    return {column: row.get(column, "") for column in columns}


def write_csv(path: str | Path, rows: Iterable[dict], extended: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = EXTENDED_COLUMNS if extended else CSV_COLUMNS
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row_for_csv(row, extended=extended))


def append_csv_row(handle, row: dict, extended: bool = False, write_header: bool = False) -> None:
    columns = EXTENDED_COLUMNS if extended else CSV_COLUMNS
    writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
    if write_header:
        writer.writeheader()
    writer.writerow(row_for_csv(row, extended=extended))


def load_clean_csv(path: str | Path) -> list[dict]:
    """Load a correctly quoted CSV produced by this application or a compatible tool."""
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("The CSV file has no header row.")
        rows = []
        for row in reader:
            if not any(str(v).strip() for v in row.values() if v is not None):
                continue
            rows.append(dict(row))
    return rows


def matrix_text(bits: str) -> str:
    m = bits_to_matrix(bits)
    return "\n".join(" ".join(str(int(v)) for v in row) for row in m)
