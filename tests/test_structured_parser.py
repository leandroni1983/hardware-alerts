import pytest
from normalizers.structured import parse_title, build_product_key_from_fields


@pytest.mark.parametrize("title,expected_key,expected_fields", [
    ("MSI RTX 4060 Ti Ventus", "nvidia_rtx_4060_ti", {"brand":"nvidia","line":"rtx","model":"4060","variant":"ti","series":"4000"}),
    ("Gigabyte GeForce RTX 3060", "nvidia_rtx_3060", {"brand":"nvidia","line":"rtx","model":"3060","variant":None,"series":"3000"}),
    ("Intel Arc A580 8GB", "intel_arc_a580", {"brand":"intel","line":"arc","model":"a580","variant":None,"series":None}),
    ("Intel Arc B580", "intel_arc_b580", {"brand":"intel","line":"arc","model":"b580","variant":None,"series":None}),
    ("Radeon RX 7600 XT", "amd_rx_7600_xt", {"brand":"amd","line":"rx","model":"7600","variant":"xt","series":"7000"}),
])
def test_parse_and_build_key(title, expected_key, expected_fields):
    parsed = parse_title(title)
    key = build_product_key_from_fields(parsed)
    assert key == expected_key
    for k, v in expected_fields.items():
        assert parsed.get(k) == v


def test_prevent_false_positives():
    p1 = parse_title("GeForce RTX 3060")
    p2 = parse_title("GeForce RTX 4060")
    assert p1.get('model') != p2.get('model')
    assert p1.get('series') != p2.get('series')

    p3 = parse_title("RTX 3050")
    p4 = parse_title("RTX 3050 Ti")
    assert p3.get('variant') != p4.get('variant')

    p5 = parse_title("A580")
    p6 = parse_title("580")
    # Ensure letter-prefixed models are distinct from numeric-only codes
    assert p5.get('model') != p6.get('model')
