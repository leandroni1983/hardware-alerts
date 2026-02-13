import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from normalizers.cpu import build_product_key as cpu_key
from normalizers.gpu import build_product_key as gpu_key
from normalizers import normalize_product


def test_cpu_keys():
    assert cpu_key("Intel i5 12400 boxed") == "intel i5 12400"
    assert cpu_key("Intel i5-12400F") == "intel i5 12400f"
    assert cpu_key("AMD Ryzen 5 5600X") == "amd ryzen 5 5600x"


def test_gpu_keys():
    assert gpu_key("ASUS ROG STRIX RTX 3060 12GB") .startswith("asus rtx 3060")
    assert "rtx 3060" in gpu_key("Gigabyte RTX 3060 12GB Gaming OC")


def test_normalize_product_includes_key():
    n = normalize_product.normalize({"title": "Intel i5 12400 boxed"})
    assert n.get("product_key") == "intel i5 12400"
