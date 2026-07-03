# gpu_sbox_tools.py
import numpy as np
import numba as nb
from numba import cuda, types
from numba import int32, uint8, float32
from math import fabs

# ========== Device (GPU) yordamchi funksiyalar ==========
# Eslatma: bu device funksiyalar faqat @cuda.jit yoki boshqa device/funksiyalarda ishlatiladi.

@cuda.jit(device=True)
def _binaryInnerProduct_device(a, b):
    ip = 0
    ab = a & b
    while ab > 0:
        ip = ip ^ (ab & 1)
        ab = ab >> 1
    return ip

# walshTransform uchun mahalliy massivlardan foydalanamiz (S-box kattaligi 256 deb olinadi)
@cuda.jit(device=True)
def _walshTransform_device(t, wt_out):
    # t: array of 0/1 ints length 256
    # wt_out: preallocated length 256 array to fill
    # Assumes length 256
    for w in range(256):
        s = 0
        # sum over x
        for x in range(256):
            bit = t[x] ^ _binaryInnerProduct_device(w, x)
            # (-1)**bit : if bit==0 => +1 else -1
            if bit == 0:
                s += 1
            else:
                s -= 1
        wt_out[w] = s
    return

@cuda.jit(device=True)
def _nonLinearity_device(t):
    # t: array length 256 of 0/1
    # compute walsh transform and then nl = len/2 - 0.5*max(abs(wt))
    wt_local = cuda.local.array(256, dtype=int32)
    _walshTransform_device(t, wt_local)
    max_abs = 0
    for i in range(256):
        v = wt_local[i]
        if v < 0:
            v = -v
        if v > max_abs:
            max_abs = v
    nl = 128.0 - 0.5 * max_abs  # len(t)/2 = 128 for 256
    return nl

# ========== sboxNonlinearity (host wrapper + kernel) ==========
# Kernel: har bir c (1..255) uchun t massivini tuzib, nonlinearity hisoblaydi.
@cuda.jit
def _compute_nlv_kernel(sbox_device, nlv_device):
    c = cuda.grid(1)  # thread index
    # we want c in 0..254 mapping to mask = c+1
    if c >= 255:
        return
    mask = c + 1
    # prepare local binary sequence t of length 256 (0/1)
    t_local = cuda.local.array(256, dtype=int32)
    for i in range(256):
        # binaryInnerProduct(mask, sbox[i])
        t_local[i] = _binaryInnerProduct_device(mask, int(sbox_device[i]))
    # compute nonlinearity
    nl = _nonLinearity_device(t_local)
    # store result
    nlv_device[c] = nl

def sboxNonlinearity(sbox):
    """
    Host function. Input: sbox as length-256 numpy array dtype=np.uint8 or int.
    Returns (minNonlinearity, maxNonlinearity) like original.
    """
    # ensure numpy array
    sbox = np.asarray(sbox, dtype=np.uint8)
    if sbox.size != 256:
        raise ValueError("This GPU implementation assumes 8-bit S-box (length 256).")
    # copy to device
    sbox_device = cuda.to_device(sbox)
    nlv_device = cuda.device_array(255, dtype=np.float32)
    threads_per_block = 64
    blocks = (255 + (threads_per_block - 1)) // threads_per_block
    _compute_nlv_kernel[blocks, threads_per_block](sbox_device, nlv_device)
    nlv = nlv_device.copy_to_host()
    # return min and max of absolute values to mimic original behavior
    abs_vals = np.abs(nlv)
    return float(np.min(abs_vals)), float(np.max(abs_vals))


# ========== walshTransform, binaryInnerProduct, nonLinearity, log2n ==========
# Original implementations were numba njit CPU. For compatibility we provide CPU versions as well,
# but the heavy walsh is done on GPU above. We keep names and CPU behavior for those who call them.

@nb.njit(nopython=True, cache=True)
def walshTransform(t):
    n = log2n(len(t))
    wt = [0]*len(t)
    for w in range(len(t)):
        s = 0
        for x in range(len(t)):
            s = s + (-1)**(t[x] ^ binaryInnerProduct(w, x))
        wt[w] = s
    return wt

@nb.njit(nopython=True, cache=True)
def binaryInnerProduct(a, b):
    ip = 0
    ab = a & b
    while ab > 0:
        ip = ip ^ (ab & 1)
        ab = ab >> 1
    return ip

@nb.njit(nopython=True, cache=True)
def nonLinearity(t):
    wt = walshTransform(t)
    # compute max abs
    max_abs = 0
    for i in range(len(wt)):
        v = wt[i]
        if v < 0:
            v = -v
        if v > max_abs:
            max_abs = v
    nl = len(t)/2 - 0.5 * max_abs
    return nl

@nb.njit(nopython=True, cache=True)
def log2n(l):
    x = l
    n = 0
    while x > 0:
        x = x >> 1
        n = n + 1
    n = n - 1
    assert 2**n == l
    return n

# ========== calculate_LP (GPU kernel) ==========
# Kernel where each thread handles one (x_mask, y_mask) pair (256*256 = 65536 threads)
# and writes imbalance into an array. Host reduces to max.

@cuda.jit(device=True)
def _parity_of_integer_device(n):
    parity = 0
    while n:
        parity = 1 - parity
        n = n & (n - 1)
    return parity

@cuda.jit
def _lp_kernel(sbox_device, imbalance_device):
    idx = cuda.grid(1)
    total_pairs = 256 * 256
    if idx >= total_pairs:
        return
    x_mask = idx // 256
    y_mask = idx % 256
    if x_mask == y_mask:
        imbalance_device[idx] = 0.0
        return

    input_count = 0
    # loop x from 0..255
    for x in range(256):
        in_par = _parity_of_integer_device(x & x_mask)
        out_par = _parity_of_integer_device(int(sbox_device[x]) & y_mask)
        if in_par == out_par:
            input_count += 1
    imbalance = abs(input_count - (256 - input_count)) / 256.0
    imbalance_device[idx] = imbalance

def calculate_LP(sbox):
    """
    GPU-accelerated calculate_LP.
    Returns max_imbalance (float).
    """
    sbox = np.asarray(sbox, dtype=np.uint8)
    if sbox.size != 256:
        raise ValueError("This GPU implementation assumes length 256.")
    sdev = cuda.to_device(sbox)
    total = 256 * 256
    imbalance_dev = cuda.device_array(total, dtype=np.float32)
    threads = 256
    blocks = (total + (threads - 1)) // threads
    _lp_kernel[blocks, threads](sdev, imbalance_dev)
    im = imbalance_dev.copy_to_host()
    # exclude positions where x_mask==y_mask (they are zero)
    return float(np.max(im))


# ========== SAC_matrix (GPU) ==========
# We'll compute 8x8 matrix; each thread handles a pair (in_bit, out_bit) (64 threads)

@cuda.jit
def _sac_kernel(sbox_device, sac_device):
    idx = cuda.grid(1)
    if idx >= 64:
        return
    in_bit = idx // 8
    out_bit = idx % 8
    cnt = 0
    for i in range(256):
        out1 = int(sbox_device[i])
        out2 = int(sbox_device[i ^ (1 << in_bit)])
        diff = out1 ^ out2
        cnt += (diff >> out_bit) & 1
    # proportion
    sac_device[in_bit, out_bit] = cnt / 256.0

def SAC_matrix(sbox):
    sbox = np.asarray(sbox, dtype=np.uint8)
    if sbox.size != 256:
        raise ValueError("SAC_matrix expects length-256 S-box.")
    sdev = cuda.to_device(sbox)
    sac_dev = cuda.device_array((8,8), dtype=np.float32)
    threads = 64
    blocks = 1
    _sac_kernel[blocks, threads](sdev, sac_dev)
    return sac_dev.copy_to_host()


# ========== differential_uniformity (GPU) ==========
# Each thread handles one 'a' in 1..255 and computes max count across diffs.

@cuda.jit
def _du_kernel(sbox_device, result_device):
    a_idx = cuda.grid(1)  # 0..254 mapping to a = a_idx+1
    if a_idx >= 255:
        return
    a = a_idx + 1
    # local histogram of length 256
    hist = cuda.local.array(256, dtype=int32)
    for i in range(256):
        hist[i] = 0
    for x in range(256):
        y = int(sbox_device[x])
        z = int(sbox_device[x ^ a])
        diff = y ^ z
        hist[diff] += 1
    # find max
    m = 0
    for i in range(256):
        if hist[i] > m:
            m = hist[i]
    result_device[a_idx] = m

def differential_uniformity(sbox):
    sbox = np.asarray(sbox, dtype=np.uint8)
    if sbox.size != 256:
        raise ValueError("differential_uniformity expects length-256 S-box.")
    sdev = cuda.to_device(sbox)
    res_dev = cuda.device_array(255, dtype=np.int32)
    threads = 64
    blocks = (255 + (threads - 1)) // threads
    _du_kernel[blocks, threads](sdev, res_dev)
    res = res_dev.copy_to_host()
    return int(np.max(res))


# ========== find_fixed_points & find_opposite_fixed_points (GPU-assisted) ==========
# We'll produce boolean flags on GPU then collect indices on host.

@cuda.jit
def _fixed_points_kernel(sbox_device, fixed_flags):
    i = cuda.grid(1)
    if i >= 256:
        return
    fixed_flags[i] = 1 if sbox_device[i] == i else 0

@cuda.jit
def _opposite_fixed_points_kernel(sbox_device, flags):
    i = cuda.grid(1)
    if i >= 256:
        return
    flags[i] = 1 if sbox_device[i] == (255 - i) else 0

def find_fixed_points(sbox):
    sbox = np.asarray(sbox, dtype=np.uint8)
    sdev = cuda.to_device(sbox)
    flags_dev = cuda.device_array(256, dtype=np.uint8)
    threads = 128
    blocks = (256 + (threads - 1)) // threads
    _fixed_points_kernel[blocks, threads](sdev, flags_dev)
    flags = flags_dev.copy_to_host()
    return [int(i) for i in np.nonzero(flags)[0].tolist()]

def find_opposite_fixed_points(sbox):
    sbox = np.asarray(sbox, dtype=np.uint8)
    sdev = cuda.to_device(sbox)
    flags_dev = cuda.device_array(256, dtype=np.uint8)
    threads = 128
    blocks = (256 + (threads - 1)) // threads
    _opposite_fixed_points_kernel[blocks, threads](sdev, flags_dev)
    flags = flags_dev.copy_to_host()
    return [int(i) for i in np.nonzero(flags)[0].tolist()]


# ========== sbox_cycle_stats ==========
# Cycle detection is inherently sequential (graph traversal). Parallel GPU
# algorithms exist but are complex. For clarity and reliability we keep a fast CPU
# implementation (numba njit accelerated). Name preserved.
@nb.njit(nopython=True, cache=True)
def sbox_cycle_stats(sbox):
    n = len(sbox)
    visited = [False] * n
    cycles_count = 0
    # we'll collect lengths in a Python list-like structure then convert
    lens = []
    for i in range(n):
        if not visited[i]:
            current = i
            length = 0
            while not visited[current]:
                visited[current] = True
                length += 1
                current = sbox[current]
            cycles_count += 1
            lens.append(length)
    # convert lens to normal Python list for return compatibility
    res_lens = [0]*len(lens)
    for i in range(len(lens)):
        res_lens[i] = lens[i]
    return cycles_count, res_lens

# End of file
