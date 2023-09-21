from grayskull.strategy.py_toml import add_flit_metadata


def test_add_flit_metadata():
    metadata = {"build": {"entry_points": []}}
    toml_metadata = {"tool": {"flit": {"scripts": {"key": "value"}}}}
    result = add_flit_metadata(metadata, toml_metadata)
    assert result == {"build": {"entry_points": ["key = value"]}}
