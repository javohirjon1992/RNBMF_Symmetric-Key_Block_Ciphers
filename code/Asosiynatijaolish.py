
from gen_funksiyalar import *
from kripto_parametrlar import *
import datetime
import random
import csv

# Nechta generatsiya qilish kerakligi kiritiladi
num_iterations = 30000
# open a CSV file for writing results
with open('all_rot_dinamik_sblok_genK0to_64.csv', mode='a', newline='') as file:
    # create a CSV writer object
    writer = csv.writer(file)
    # write the header row
    #writer.writerow(['adjaency_matrix_result','b_uzgarmas', 'sboxes', 'nonlinearity_max', 'nonlinearity_min', 'nonlinearity_all','LP','MAX_LP', 'MIN_SAC', 'MAX_SAC', 'AVG_SAC', 'Square_dev', 'MAX_DU', 'date', 'time'])
     # iterate through the specified number of iterations
    for i in range(num_iterations):
        # ============================================================
#  VECTOR -> MATRIX -> STRING
# ============================================================

        

        # ============================================================
        #  SHIFT + STRING
        # ============================================================

        def shift_left(v, k):
            k %= 64
            return v[k:] + v[:k]


        def to_vec(x):
            return [int(e) for e in x] if isinstance(x, str) else x[:]


        def to_string(v):
            return "".join(str(int(e)) for e in v)


        # ============================================================
        #  RANDOM SHIFT FUNCTION
        # ============================================================

        def get_random_A1_A2(A1_input, A2_input):
            v1 = to_vec(A1_input)
            v2 = to_vec(A2_input)

            # random k lar
            k1 = random.randint(0, 63)
            k2 = random.randint(0, 63)

            v1_shifted = shift_left(v1, k1)
            v2_shifted = shift_left(v2, k2)

            A1_matritsa_string = to_string(v1_shifted)
            A2_matritsa_string = to_string(v2_shifted)

            return A1_matritsa_string, A2_matritsa_string, k1, k2


        # ============================================================
        #  USAGE
        # ============================================================

        A1_input = "1101011101011001011001001100000111010000110101101111011100000101" #1101011101011001011001001100000111010000110101101111011100000101
        A2_input = "1100011010011011101011110010100001110011000011101000110110101010" #1100011010011011101011110010100001110011000011101000110110101010

        A1_matritsa_string, A2_matritsa_string, k1, k2 = get_random_A1_A2(A1_input, A2_input)

        adjacency_matrix_result_1 = A1_matritsa_string
        b_constant_01 = generate_8bit_string()
        adjacency_matrix_result_02 = A2_matritsa_string
        b_constant_02 = generate_8bit_string()
        # Keltirilmaydigan polinomlar
        p_k_polinomlar = ['111100111']
        p_k_ni_tas_tanlash = random.choice(p_k_polinomlar)
        # S blokni generatsiya qilish
        sboxes_2 = generate_rijndael_sbox2(adjacency_matrix_result_1, b_constant_01, adjacency_matrix_result_02, b_constant_02, p_k_ni_tas_tanlash)

        nonlinearity_min_max = sboxNonlinearity(sboxes_2)
        nonlinearity_all = nonLinearity(sboxes_2)
        nonlinearity_min = nonlinearity_min_max[0]
        nonlinearity_max = nonlinearity_min_max[1]

        LP = calculate_LP(sboxes_2)
        LP = LP/2
        MAX_LP  = (LP+0.5)*256
        sac = SAC_matrix(sboxes_2)
        MIN_SAC = np.min(sac)
        MAX_SAC = np.max(sac)
        AVG_SAC = np.mean(sac)
        Square_dev = np.std(sac, ddof=0)
        num_iterations_du = 1
        du_scores = []
        max_du = 0
        for i in range(num_iterations_du):
            sbox = sboxes_2
            du = differential_uniformity(sbox)
            du_scores.append(du)
            if du > max_du:
                max_du = du
        MAX_DU = max_du
        now = datetime.datetime.now()
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M:%S")
        fp1=find_fixed_points(sboxes_2)
        fp1_hex = [hex(value)[2:].lower() for value in fp1]
        fp2=find_opposite_fixed_points(sboxes_2)
        fp2_hex = [hex(value)[2:].lower() for value in fp2]
        FP=len(fp1)+len(fp2)
        count, lengths = sbox_cycle_stats(sboxes_2)

        mergelist=[adjacency_matrix_result_1, k1, b_constant_01, adjacency_matrix_result_02, k2, b_constant_02, p_k_ni_tas_tanlash, sboxes_2, nonlinearity_max, nonlinearity_min, nonlinearity_all, LP, MAX_LP, MIN_SAC, MAX_SAC, AVG_SAC, Square_dev, MAX_DU, fp1_hex, fp2_hex, FP,count, lengths,  date, time] 
        # if (nonlinearity_min >= 111 and nonlinearity_max >= 111) and (MIN_SAC>0.45 and MAX_SAC<0.56):
        
        # if ((nonlinearity_min >= 111 and nonlinearity_max >= 111) and (MIN_SAC > 0.45 and MAX_SAC < 0.56) and (count < 40 and all(l < 100 for l in lengths))):
        #if (AVG_SAC ==0.5) or  ((MIN_SAC > 0.45) and (MAX_SAC < 0.56)) or (Square_dev<0.027): # and all(l < 100 for l in lengths)
        writer.writerow(mergelist)  # Fixed indentation
        print(mergelist) 
file.close()