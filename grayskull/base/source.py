from grayskull.base.section import Section


class Source:
    ALL_SUBSECTIONS = (
        "fn",
        "url",
        "md5",
        "sha1",
        "sha256",
        "path",
        "path_via_symlink",
        "git_url",
        "git_tag",
        "git_branch",
        "git_rev",
        "git_depth",
        "hg_url",
        "hg_tag",
        "svn_url",
        "svn_rev",
        "svn_ignore_externals",
        "folder",
        "no_hoist",
        "patches",
    )

    def __init__(self, **kwargs):
        self._validate_subsection(kwargs)
        self._section = Section("packages")
        self.populate(kwargs)

    def populate(self, subsections):
        for key, value in subsections.items():
            self._section.add_subsection(key, value)

    def _validate_subsection(self, subsections: dict):
        for k in subsections.keys():
            if k not in self.ALL_SUBSECTIONS:
                raise ValueError(f"Subsection {k} does not exist")
