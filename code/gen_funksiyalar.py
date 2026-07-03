import numpy as np
import random

# A1 va A2 uchun Genetik algoritm


# **A1 va A2 uchun 8x8 matritsa qurish Genetik algoritmi**
# Genetic Algorithm Functions
def create_initial_population(pop_size, n):
    return [np.random.randint(2, size=(n, n)) for _ in range(pop_size)]
def fitness(matrix):
    det = np.linalg.det(matrix)
    return abs(det) if det != 0 else 0.0001
def roulette_wheel_selection(population, fitness_scores):
    total_fitness = sum(fitness_scores)
    selection_probs = [f / total_fitness for f in fitness_scores]
    return list(np.random.choice(population, size=len(population), replace=True, p=selection_probs))
def single_point_crossover(a, b):
    n = a.shape[0]
    p = random.randint(1, n-1)
    new_a = np.vstack((a[:p], b[p:]))
    new_b = np.vstack((b[:p], a[p:]))
    return new_a, new_b
def mutate(matrix, mutation_rate):
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            if random.random() < mutation_rate:
                matrix[i, j] = 1 - matrix[i, j]
    return matrix
def calculate_determinant(matrix):
    determinant = np.linalg.det(matrix)
    return round(determinant, 2)  # Round to 0.01 accuracy
def display_matrices(matrix, generation, found):
    def print_matrix(matrix, title):
        print(title)
        for row in matrix:
            print(' '.join(str(int(e)) for e in row))
        print(f"Determinant: {calculate_determinant(matrix)}\n")
    if found:
        print(f"Original Matrix (Generation {generation}):")
        print_matrix(matrix, "Original Matrix")         
    else:
        print("Maximum generations reached without finding a nonsingular matrix.")
def genetic_algorithm_for_matrix(n, pop_size, max_generations, mutation_rate):
    population = create_initial_population(pop_size, n)
    
    for generation in range(max_generations):
        fitness_scores = [fitness(matrix) for matrix in population]

        best_fitness = max(fitness_scores)
        if best_fitness > 0.01:
            best_matrix = population[fitness_scores.index(best_fitness)]
            # display_matrices(best_matrix, generation, True)
            return best_matrix

        selected = roulette_wheel_selection(population, fitness_scores)
        population = []

        for i in range(0, len(selected), 2):
            parent1, parent2 = selected[i], selected[i + 1]
            child1, child2 = single_point_crossover(parent1, parent2)
            population.append(mutate(child1, mutation_rate))
            population.append(mutate(child2, mutation_rate))

    display_matrices(None, None, False)
    return None


     



















""" 
 Bu yerdan S blokni generatsiya qilish boshlanadi

"""






















def multiply_ints_as_polynomials(x, y):
    z = 0
    while x != 0:
        if x & 1 == 1:
            z ^= y
        y <<= 1
        x >>= 1
    return z

def number_bits(x):
    nb = 0
    while x != 0:
        nb += 1
        x >>= 1
    return nb

def mod_int_as_polynomial(x, m):
    nbm = number_bits(m)
    while True:
        nbx = number_bits(x)
        if nbx < nbm:
            return x
        mshift = m << (nbx - nbm)
        x ^= mshift

def rijndael_multiplication(x, y, m):
    z = multiply_ints_as_polynomials(x, y)
    m = int(m, 2)  # Convert string binary to integer
    return mod_int_as_polynomial(z, m)

def rijndael_inverse(x, m):
    if x == 0:
        return 0
    for y in range(1, 256):
        if rijndael_multiplication(x, y, m) == 1:
            return y

def dot_product(x, y):
    z = x & y
    dot = 0
    while z != 0:
        dot ^= z & 1
        z >>= 1
    return dot

def affine_transformation(A1, x, b1):
    y = 0
    for i in reversed(range(8)):
        row = (A1 >> (8 * i)) & 0xff
        bit = dot_product(row, x)
        y ^= (bit << i)
    return y ^ b1

def rijndael_sbox(x, adjacency_matrix_result, b_constant):
    A1 = int(adjacency_matrix_result, 2)
    b1 = int(b_constant, 2)
    return affine_transformation(A1, x, b1)

def generate_rijndael_sbox2(adjacency_matrix_result_1, b_constant_01, adjacency_matrix_result_02, b_constant_02, m):
    sbox = []
    for x in range(256):
        C1 = rijndael_sbox(x, adjacency_matrix_result_1, b_constant_01)
        xinv1 = rijndael_inverse(C1, m)
        A2 = int(adjacency_matrix_result_02, 2)
        b2 = int(b_constant_02, 2)
        sbox.append(affine_transformation(A2, xinv1, b2))
    return sbox


    """
    S blokni generatsiya qilish tugadi   
    
    """
    
    
    """ 
    Parametrlarni tasodifiy tanlash va aylantirish
    funksiyalari boshlandi   
    
    """
 
#   b1 va b2 ni tasodifiy tanlash funksiyasi
def generate_8bit_string():
    bit_string = ""
    for _ in range(8):
        bit = random.choice(['0', '1'])
        bit_string += bit
    return bit_string


# Bu funksiya string holda matritsani oladi va berilgan 90, 180, 270, 360 ga qarab aylantirib  string qaytaradi 

def rotate_matrix(adjacency_matrix_result, rotation):
    # Matritsani 8x8 formatga aylantirish
    matrix = np.array([list(adjacency_matrix_result[i:i + 8]) for i in range(0, len(adjacency_matrix_result), 8)])

    # Matritsani tanlangan burchakda aylantirish
    rotated_matrix = np.rot90(matrix, k=rotation // 90, axes=(0, 1))

    # Aylantirilgan matritsani stringga aylantirish
    rotated_string = ''.join(''.join(row) for row in rotated_matrix)

    # Tasodifiy burchak va aylantirilgan stringni qaytarish
    return rotated_string


# Bu yerga  matritsa d^1 va d^-1 keladi 1 bulsa matritsa uzi -1 bulsa 2 mod buyicha inversi string qiymatda qaytadi 

def matritsa_2mod_teskarisi(adjacency_matrix_result, d):
    # Matritsani 8x8 formatga o'zgartirish
    matrix = np.array([list(map(int, adjacency_matrix_result[i:i + 8])) for i in range(0, len(adjacency_matrix_result), 8)])

    if d == 1:
        # Agar d = 1 bo'lsa, matritsani to'g'ridan-to'g'ri qaytarish
        result_matrix = matrix
    elif d == -1:
        # Agar d = -1 bo'lsa, matritsaning mod 2 inversiyasini hisoblash
        try:
            inverse_matrix = np.linalg.inv(matrix) % 2
            result_matrix = inverse_matrix.astype(int)  # Integer ko'rinishga o'tkazish
        except np.linalg.LinAlgError:
            return "Matritsaning mod 2 buyicha teskarisi yuq."

    # Matritsani string ko'rinishida qaytarish
    result_string = ''.join(''.join(map(str, row)) for row in result_matrix)

    return result_string
