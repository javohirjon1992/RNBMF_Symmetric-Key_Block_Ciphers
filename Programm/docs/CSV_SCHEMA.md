# CSV Output Schema

The application supports two export modes.

## Compatible CSV

The compatible format preserves the legacy 25-column schema:

1. `A1_Binary_Matrix`
2. `A1_Matrix_Rotation_Offset`
3. `b1_Binary_Constant`
4. `A2_Binary_Matrix`
5. `A2_Matrix_Rotation_Offset`
6. `b2_Binary_Constant`
7. `GF_2_8_Irreducible_Polynomial`
8. `Calculated_S_Box`
9. `Nonlinearity_Max`
10. `Nonlinearity_Min`
11. `Nonlinearity_N_S`
12. `Linear_Probability`
13. `LAT_Max`
14. `SAC_Min`
15. `SAC_Max`
16. `SAC_Average`
17. `SAC_Square_Deviation`
18. `Differential_Uniformity_Max`
19. `Fixed_Points_Hex`
20. `Opposite_Fixed_Points_Hex`
21. `Fixed_Point_Count`
22. `Cycle_Count`
23. `Cycle_Lengths`
24. `Generation_Date`
25. `Generation_Time`

For compatibility with the supplied legacy implementation, `SAC_Square_Deviation` stores the standard deviation used by the original code even though the historical column name contains the phrase `Square_Deviation`.

## Extended CSV

The extended format appends:

- `Algebraic_Degree_Min`
- `Algebraic_Degree_Max`
- `Boomerang_Uniformity`
- `Is_Bijective`
- `Minimum_Cycle_Length`

The exported CSV is standards-compliant and can be loaded with Excel, pandas, LibreOffice, or the application itself.
