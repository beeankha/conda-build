# Copyright (C) 2014 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from conda_build.api import get_output_file_paths
from conda_build.render import (
    _simplify_to_exact_constraints,
    find_pkg_dir_or_file_in_pkgs_dirs,
    get_pin_from_build,
    open_recipe,
    render_recipe,
)
from conda_build.utils import CONDA_PACKAGE_EXTENSION_V1, on_linux

from .utils import metadata_path

if TYPE_CHECKING:
    from pathlib import Path

    from conda_build.config import Config
    from conda_build.metadata import MetaData


@pytest.mark.parametrize(
    "build",
    [
        pytest.param({"noarch": "python"}, id="noarch"),
        pytest.param({"noarch_python": True}, id="noarch_python"),
    ],
)
def test_noarch_output(build, testing_metadata):
    testing_metadata.meta["build"].update(build)
    output = get_output_file_paths(testing_metadata)
    assert os.path.sep + "noarch" + os.path.sep in output[0]


def test_reduce_duplicate_specs(testing_metadata):
    testing_metadata.meta["requirements"] = {
        "build": ["exact", "exact 1.2.3 1", "exact >1.0,<2"],
        "host": ["exact", "exact 1.2.3 1"],
    }
    _simplify_to_exact_constraints(testing_metadata)
    simplified = testing_metadata.meta["requirements"]

    assert simplified["build"] == simplified["host"]
    assert len(simplified["build"]) == 1
    assert "exact 1.2.3 1" in simplified["build"]


def test_pin_run_as_build_preserve_string(testing_metadata):
    m = testing_metadata
    m.config.variant["pin_run_as_build"]["pkg"] = {"max_pin": "x.x"}
    dep = get_pin_from_build(m, "pkg * somestring*", {"pkg": "1.2.3 somestring_h1234"})
    assert dep == "pkg >=1.2.3,<1.3.0a0 somestring*"


@pytest.mark.parametrize(
    "create_package,subdir,is_file,files_only",
    [
        pytest.param(False, None, None, None, id="not found"),
        pytest.param(True, None, False, False, id="directory"),
        pytest.param(True, None, False, True, id="on demand"),
        pytest.param(True, "magic", False, True, id="on demand, different subdir"),
        pytest.param(True, None, True, None, id="file"),
    ],
)
def test_find_package(
    testing_metadata: MetaData,
    tmp_path: Path,
    create_package: bool,
    subdir: str | None,
    is_file: bool,
    files_only: bool,
):
    """
    Testing our ability to find the package directory or archive.

    The find_pkg_dir_or_file_in_pkgs_dirs function will scan the various
    locations where packages may exist locally and returns the full package path
    if found.
    """
    # setup
    distribution = uuid4().hex[:20]
    testing_metadata.config.croot = tmp_path
    host_cache = tmp_path / testing_metadata.config.host_subdir
    host_cache.mkdir()
    subdir = subdir or testing_metadata.config.host_subdir
    other_cache = tmp_path / subdir
    other_cache.mkdir(exist_ok=True)

    # generate a dummy package as needed
    package = None
    if create_package:
        # generate dummy package
        if is_file:
            (host_cache / (distribution + CONDA_PACKAGE_EXTENSION_V1)).touch()
        else:
            info = host_cache / distribution / "info"
            info.mkdir(parents=True)
            (info / "index.json").write_text(json.dumps({"subdir": subdir}))

        # expected package path
        if is_file or files_only:
            package = other_cache / (distribution + CONDA_PACKAGE_EXTENSION_V1)
        else:
            package = other_cache / distribution

    # attempt to find the package and check we found the expected path
    found = find_pkg_dir_or_file_in_pkgs_dirs(
        distribution,
        testing_metadata,
        files_only=files_only,
    )
    assert package is found is None or package.samefile(found)


def test_open_recipe(tmp_path: Path):
    path = tmp_path / "missing"
    with pytest.raises(
        SystemExit,
        match=rf"Error: non-existent: {re.escape(str(path))}",
    ):
        with open_recipe(path):
            pass

    (path := tmp_path / "bad.ext").touch()
    with pytest.raises(
        SystemExit,
        match=rf"Error: non-recipe: {re.escape(str(path))}",
    ):
        with open_recipe(path):
            pass


@pytest.mark.benchmark
def test_render_recipe(testing_config: Config) -> None:
    recipes = render_recipe(metadata_path / "_render_recipe", config=testing_config)

    if on_linux:
        assert len(recipes) == 48
    else:
        assert len(recipes) == 16
