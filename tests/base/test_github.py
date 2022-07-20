from grayskull.base.github import fetch_all_tags_gh


def test_fetch_all_tags_gh():
    assert len(fetch_all_tags_gh("https://github.com/conda-incubator/grayskull")) > 1
