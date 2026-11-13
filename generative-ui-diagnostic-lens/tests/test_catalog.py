"""The component catalog is closed: six primitives, no additions (issue #37)."""

import catalog


EXPECTED = (
    "TimeSeriesChart",
    "DiffTable",
    "KPICard",
    "ZoneHighlight",
    "LogTail",
    "ParamInspector",
)


def test_catalog_has_exactly_six_primitives():
    assert tuple(catalog.PRIMITIVE_NAMES) == EXPECTED
    assert set(catalog.catalog()) == set(EXPECTED)
    assert len(catalog.catalog()) == 6


def test_every_primitive_declares_bindings_units_and_absent_rendering():
    for name in EXPECTED:
        primitive = catalog.get_primitive(name)
        assert primitive is not None
        assert primitive.summary.strip()
        assert primitive.absent_binding_rendering.strip()
        assert "no data" in primitive.absent_binding_rendering.lower()
        if name != "ParamInspector":
            assert primitive.required_bindings
        for binding in primitive.required_bindings + primitive.optional_bindings:
            assert primitive.binding_kind(binding) in (
                "field",
                "unit",
                "number",
                "string",
                "int",
            )


def test_series_primitives_accept_the_units_the_fixtures_use():
    assert catalog.get_primitive("TimeSeriesChart").accepts_unit("°C")
    assert catalog.get_primitive("TimeSeriesChart").accepts_unit("%RH")
    assert catalog.get_primitive("TimeSeriesChart").accepts_unit("W")
    assert catalog.get_primitive("DiffTable").accepts_unit("°C")
    assert catalog.get_primitive("KPICard").accepts_unit("kWh")
    assert catalog.get_primitive("ZoneHighlight").accepts_unit("°C")


def test_unknown_primitive_is_not_in_the_catalog():
    assert catalog.get_primitive("HeatMap") is None
    assert catalog.get_primitive("ScatterPlot") is None
    assert catalog.get_primitive("") is None


def test_unit_normalisation_is_canonical_and_rejects_nonsense():
    assert catalog.normalize_unit("degC") == "°C"
    assert catalog.normalize_unit("celsius") == "°C"
    assert catalog.normalize_unit("kW") == "kW"
    assert catalog.normalize_unit("kg/s") == "kg/s"
    assert catalog.normalize_unit("furlongs") is None
    assert catalog.normalize_unit(None) is None


def test_unit_dimensions():
    assert catalog.unit_dimension("°C") == "temperature"
    assert catalog.unit_dimension("%RH") == "percentage"
    assert catalog.unit_dimension("W") == "power"
    assert catalog.unit_dimension("kWh") == "energy"
    assert catalog.unit_dimension("nonsense") is None


def test_catalog_listing_is_stable():
    listing = catalog.catalog_listing()
    assert [row["primitive"] for row in listing] == list(EXPECTED)
    for row in listing:
        assert "absent_binding_rendering" in row
