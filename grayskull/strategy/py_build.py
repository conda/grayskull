"""
Use pypa/build to get project metadata from a checkout. Create a recipe suitable
for inlinining into the first-party project source tree.
"""

import logging
import tempfile
from importlib.metadata import PathDistribution
from pathlib import Path

import build
from conda.exceptions import InvalidMatchSpec
from conda.models.match_spec import MatchSpec
from packaging.requirements import Requirement
from souschef.recipe import Recipe

from grayskull.config import Configuration
from grayskull.strategy.abstract_strategy import AbstractStrategy
from grayskull.strategy.pypi import compose_test_section

log = logging.getLogger(__name__)


class PyBuild(AbstractStrategy):
    @staticmethod
    def fetch_data(recipe: Recipe, config: Configuration, sections=None):
        project = build.ProjectBuilder(config.name)

        recipe["source"]["path"] = "../"
        # XXX relative to output. "git_url: ../" is also a good choice.

        with tempfile.TemporaryDirectory(prefix="grayskull") as output:
            build_system_requires = project.build_system_requires
            requires_for_build = project.get_requires_for_build("wheel")
            # If those are already installed, we can get the extras requirements
            # without invoking pip e.g. setuptools_scm[toml]
            print("Requires for build:", build_system_requires, requires_for_build)

            # build the project's metadata "dist-info" directory
            metadata_path = Path(project.metadata_path(output_directory=output))

            distribution = PathDistribution(metadata_path)

            # real distribution name not pathname
            config.name = distribution.name  # see also _normalized_name
            config.version = distribution.version

            # grayskull thought the name was the path. correct that.
            if recipe[0] == '#% set name = "." %}':  # XXX fragile
                # recipe[0] = x does not work
                recipe._yaml._yaml_get_pre_comment()[0].value = (
                    f'#% set name = "{config.name}" %}}\n'
                    f'#% set version = "{config.version}" %}}\n'
                )

                recipe["package"]["version"] = "{{ version }}"
            elif config.name not in str(recipe[0]):
                log.warning("Package name not found in first line of recipe")

            metadata = distribution.metadata

            requires_python = metadata["requires-python"]
            if requires_python:
                requires_python = f"python { requires_python }"
            else:
                requires_python = "python"

            recipe["requirements"]["host"] = [requires_python] + sorted(
                (*build_system_requires, *requires_for_build)
            )

            requirements = [Requirement(r) for r in distribution.requires or []]
            active_requirements = [
                str(r).rsplit(";", 1)[0]
                for r in requirements
                if not r.marker or r.marker.evaluate()
            ]
            # XXX to normalize space between name and version, MatchSpec(r).spec
            normalized_requirements = []
            for requirement in active_requirements:
                try:
                    normalized_requirements.append(
                        # MatchSpec uses a metaclass hiding its constructor from
                        # the type checker
                        MatchSpec(requirement).spec  # type: ignore
                    )
                except InvalidMatchSpec:
                    log.warning("%s is not a valid MatchSpec", requirement)
                    normalized_requirements.append(requirement)

            # conda does support ~=3.0.0 "compatibility release" matches
            recipe["requirements"]["run"] = [requires_python] + normalized_requirements
            # includes extras as markers e.g. ; extra == 'testing'. Evaluate
            # using Marker().

            recipe["build"]["entry_points"] = [
                f"{ep.name} = {ep.value}"
                for ep in distribution.entry_points
                if ep.group == "console_scripts"
            ]

            recipe["build"]["noarch"] = "python"
            recipe["build"]["script"] = (
                "{{ PYTHON }} -m pip install . -vv --no-deps --no-build-isolation"
            )
            # XXX also --no-index?

            # distribution.metadata.keys() for grayskull is
            # Metadata-Version
            # Name
            # Version
            # Summary
            # Author-email
            # License
            # Project-URL
            # Keywords
            # Requires-Python
            # Description-Content-Type
            # License-File
            # License-File
            # Requires-Dist (many times)
            # Provides-Extra (several times)
            # Description or distribution.metadata.get_payload()

            about = {
                "summary": metadata["summary"],
                "license": metadata["license"],
                # there are two license-file in grayskull e.g.
                "license_file": metadata["license-file"],
            }
            recipe["about"] = about

            metadata_dict = dict(
                metadata
            )  # XXX not what compose_test_section expects at all
            metadata_dict["name"] = config.name
            metadata_dict["entry_points"] = [
                f"{ep.name} = {ep.value}"
                for ep in distribution.entry_points
                if ep.group == "console_scripts"
            ]
            recipe["test"] = compose_test_section(metadata_dict, [])

        # raise NotImplementedError()
