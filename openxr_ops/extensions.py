# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


import re
from dataclasses import dataclass
from typing import Optional

EXT_ADOC_DECOMP = re.compile(
    r"""specification/sources/chapters/extensions/
    (?P<vendor>[a-z0-9]+)/ # vendor directory
    (?P=vendor)_(?P<undecorated>[^.]+)[.]adoc""",  # filename in two parts
    re.VERBOSE,
)

_EXPERIMENTAL_SUFFIX = re.compile(
    r"""
    (?P<id>[A-Z]+) # actual vendor tag
    (?P<suffix>X[0-9]+) # "x1" suffix or similar
    """,
    re.VERBOSE,
)


@dataclass
class ExtensionData:
    """The decomposed parts of an OpenXR extension name."""

    vendor: str
    """Vendor ID, including experimental suffix if any, all uppercase."""

    vendor_without_suffix: str
    """Vendor ID, without experimental suffix, all uppercase."""

    experimental_suffix: str
    """The experimental suffix or empty string."""

    undecorated: str
    """The final part of the extension name, after the vendor."""

    @property
    def full_name(self):
        """Get the full extension name."""
        return f"XR_{self.vendor}_{self.undecorated}"

    @property
    def non_experimental_name(self):
        """Get anticipated full name without the experimental suffix."""
        return f"XR_{self.vendor_without_suffix}_{self.undecorated}"

    @classmethod
    def try_from_adoc_path(cls, path: str) -> "Optional[ExtensionData]":
        path_match = EXT_ADOC_DECOMP.match(path)
        if not path_match:
            return None

        vendor = path_match.group("vendor").upper()
        undecorated = path_match.group("undecorated")
        vendor_without_suffix = vendor
        experimental_suffix = ""
        experiment = _EXPERIMENTAL_SUFFIX.match(vendor)
        if experiment:
            vendor_without_suffix = experiment.group("id")
            experimental_suffix = experiment.group("suffix")

        return ExtensionData(
            vendor=vendor,
            vendor_without_suffix=vendor_without_suffix,
            experimental_suffix=experimental_suffix,
            undecorated=undecorated,
        )


class ExtensionNameGuesser:
    """Process modified file paths to try to guess the extension related to an MR."""

    def __init__(self):
        self.names = set()
        self.extensions = []

    def handle_path(self, path_modified: str) -> Optional[ExtensionData]:
        data = ExtensionData.try_from_adoc_path(path_modified)
        if not data:
            return None

        if data.full_name not in self.names:
            self.names.add(data.full_name)
            self.extensions.append(data)
            return data

        return None
