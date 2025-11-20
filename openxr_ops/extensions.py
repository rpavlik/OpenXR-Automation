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
    (?P<tag>[A-Z]+) # actual vendor tag
    (?P<suffix>X[0-9]+) # "x1" suffix or similar
    """,
    re.VERBOSE,
)

TAG_DECOMP_RE = re.compile(
    r"""
    (?P<tag>[A-Z]+) # actual vendor tag
    (?P<experiment>X[0-9]*)? # X or X1 suffix or similar
    """,
    re.VERBOSE,
)


def split_experimental_suffix(vendor_tag: str) -> tuple[str, str]:
    vendor_without_suffix = vendor_tag
    experimental_suffix = ""
    experiment = _EXPERIMENTAL_SUFFIX.match(vendor_tag)
    if experiment:
        vendor_without_suffix = experiment.group("tag")
        experimental_suffix = experiment.group("suffix")
    return vendor_without_suffix, experimental_suffix


_EXT_TITLE_DECOMP = re.compile(
    r"""XR_ # Prefix
    (?P<vendor>[A-Z0-9]+) # vendor tag
    _(?P<undecorated>[^.]+)""",  # rest of name
    re.VERBOSE,
)
_EXT_DECOMP_RE = re.compile(r"XR_" + TAG_DECOMP_RE.pattern + r"_.*")


def compute_vendor_name_and_tag(title, vendors) -> tuple[str | None, str | None]:
    m = _EXT_DECOMP_RE.match(title)
    vendor: str | None = None
    tag: str | None = None
    if m is not None:
        tag = m.group("tag")
        assert tag is not None
        vendor = vendors.get_vendor_name(tag)
    return vendor, tag


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
        vendor_without_suffix, experimental_suffix = split_experimental_suffix(vendor)

        return ExtensionData(
            vendor=vendor,
            vendor_without_suffix=vendor_without_suffix,
            experimental_suffix=experimental_suffix,
            undecorated=undecorated,
        )

    @classmethod
    def try_from_name(cls, ext_name: str) -> "Optional[ExtensionData]":
        title_match = _EXT_TITLE_DECOMP.match(ext_name)
        if not title_match:
            return None

        vendor = title_match.group("vendor")
        undecorated = title_match.group("undecorated")
        vendor_without_suffix, experimental_suffix = split_experimental_suffix(vendor)

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

    def handle_path(self, path_modified: str) -> ExtensionData | None:
        data = ExtensionData.try_from_adoc_path(path_modified)
        if not data:
            return None

        if data.full_name not in self.names:
            self.names.add(data.full_name)
            self.extensions.append(data)
            return data

        return None
