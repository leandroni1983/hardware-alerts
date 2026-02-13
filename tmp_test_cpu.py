import sys
sys.path.insert(0, '.')
from normalizers.cpu import build_product_key
samples = [
"MICRO INTEL CORE ULTRA 5 245KF S/VIDEO S/COOLER S1851",
"MICRO INTEL CORE I5 14400F S/VIDEO C/COOLER S1700",
"MICRO INTEL PENTIUM G7400 S1700",
"MICRO INTEL CORE ULTRA 5 225 C/VIDEO C/COOLER S1851",
"MICRO INTEL CELERON G6900 S1700",
"MICRO INTEL CORE ULTRA 5 225F S/VIDEO C/COOLER S1851",
]
for s in samples:
    print(s)
    print('->', build_product_key(s))
