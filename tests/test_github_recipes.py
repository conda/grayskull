import pytest
from souschef.jinja_expression import get_global_jinja_var

from grayskull.__main__ import create_python_recipe
from grayskull.strategy.pypi import adjust_source_url_to_include_placeholders


@pytest.mark.github
def test_289_github_url_version_placeholder():
    recipe, _ = create_python_recipe(
        "https://github.com/spdx/spdx-license-matcher", version="2.1"
    )
    assert (
        recipe["source"]["url"]
        == "https://github.com/spdx/spdx-license-matcher/archive/v{{ version }}.tar.gz"
    )
    assert get_global_jinja_var(recipe, "version") == "2.1"


def test_adjust_source_url_to_include_placeholders():
    assert (
        adjust_source_url_to_include_placeholders(
            "https://github.com/spdx/spdx-license-matcher/archive/v2.1.tar.gz", "2.1"
        )
        == "https://github.com/spdx/spdx-license-matcher/archive/v{{ version }}.tar.gz"
    )
