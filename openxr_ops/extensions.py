# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


import re
from dataclasses import dataclass
from typing import Optional

EXT_ADOC_DECOMP = re.compile(
    r"""specification/sources/chapters/extensions/
    (?P<vendor>[a-z]+)/ # vendor directory
    (?P=vendor)_(?P<undecorated>[^.]+)[.]adoc""",  # filename in two parts
    re.VERBOSE,
)


@dataclass
class ExtensionData:
    """The decomposed parts of an OpenXR extension name"""

    vendor: str
    undecorated: str

    @property
    def full_name(self):
        return f"XR_{self.vendor}_{self.undecorated}"

    @classmethod
    def try_from_adoc_path(cls, path: str) -> "Optional[ExtensionData]":
        path_match = EXT_ADOC_DECOMP.match(path)
        if not path_match:
            return None

        vendor = path_match.group("vendor").upper()
        undecorated = path_match.group("undecorated")
        return ExtensionData(vendor, undecorated)


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
