"""
Use pypa/build to get project metadata from a checkout. Create a recipe suitable
for inlinining into the first-party project source tree.
"""

import tempfile
from importlib.metadata import PathDistribution
from pathlib import Path

from packaging.markers import Marker
from packaging.metadata import Metadata
from souschef.recipe import Recipe

import build
from grayskull.config import Configuration
from grayskull.strategy.abstract_strategy import AbstractStrategy
import logging

log = logging.getLogger(__name__)


class PyBuild(AbstractStrategy):
    @staticmethod
    def fetch_data(recipe: Recipe, config: Configuration, sections=None):
        project = build.ProjectBuilder(config.name)

        with tempfile.TemporaryDirectory(prefix="grayskull") as output:
            build_system_requires = project.build_system_requires
            requires_for_build = project.get_requires_for_build("wheel")
            # If those are already installed, we can get the extras requirements
            # without invoking pip e.g. setuptools_scm[toml]
            print("Requires for build:", build_system_requires, requires_for_build)

            recipe["requirements"]["host"] = sorted(
                (*build_system_requires, *requires_for_build)
            )

            # build the project's metadata "dist-info" directory
            metadata_path = Path(project.metadata_path(output_directory=output))

            distribution = PathDistribution(metadata_path)

            # real distribution name not pathname
            config.name = distribution.name  # see also _normalized_name

            # grayskull thought the name was the path. correct that.
            if recipe[0] == '#% set name = "." %}':  # XXX fragile
                # recipe[0] = x does not work
                recipe._yaml._yaml_get_pre_comment()[
                    0
                ].value = f'#% set name = "{config.name}" %}}'
            elif config.name not in recipe[0]:
                log.warning("Package name not found in first line of recipe")

            config.version = distribution.version
            requires_dist = distribution.requires  # includes extras as markers e.g. ; extra == 'testing'. Evaluate using Marker().
            entry_points = (
                distribution.entry_points
            )  # list(EntryPoint(name, value, group)

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

        # raise NotImplementedError()
