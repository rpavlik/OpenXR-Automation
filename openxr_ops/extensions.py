# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from typing import Optional

import gitlab
import gitlab.v4.objects

from .ext_author_kind import CanonicalExtensionAuthorKind

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
_EXT_DECOMP_RE = re.compile(rf"XR_{TAG_DECOMP_RE.pattern}_.*", re.VERBOSE)


class VendorNames:
    """Data structure storing vendor/author codes to vendor names."""

    @classmethod
    def from_git(cls, gl_proj: gitlab.v4.objects.Project, ref="main"):
        pf = gl_proj.files.get("specification/registry/xr.xml", ref)
        return cls(pf.decode().decode("utf-8"))

    def __init__(self, registry_contents: str) -> None:
        self._contents = registry_contents

        self.root = ElementTree.fromstring(self._contents)
        self.known: dict[str, str] = {}
        """Vendor tag to name string"""

        for tag in self.root.findall("tags/tag"):
            tag_name = tag.get("name")
            tag_author = tag.get("author")
            assert tag_name
            assert tag_author
            if not tag_name or not tag_author:
                # should not happen
                continue
            self.known[tag_name] = tag_author

        # Keep this table up to date with any vendors that have more than one tag
        # so they are merged in other operations.
        self.known.update(
            {
                "FB": "Meta Platforms",
                "META": "Meta Platforms",
                "OCULUS": "Meta Platforms",
                # "QCOM": "Qualcomm",
                # "EPIC": "Epic Games",
                # "ML": "Magic Leap",
                # "VARJO": "Varjo",
                # "HTC": "HTC",
                CanonicalExtensionAuthorKind.EXT.value: "Multi-vendor",
                CanonicalExtensionAuthorKind.KHR.value: "The Khronos Group",
            }
        )

        # Preferred tag for vendors with multiple.
        self.name_to_tag = {"Meta Platforms": "META"}
        """Name string to preferred/most recent vendor tag"""

        # Add any from self.known that do not conflict to self.name_to_tag
        for tag_name, tag_author in self.known.items():
            if not tag_name.endswith("X") and tag_author not in self.name_to_tag:
                self.name_to_tag[tag_author] = tag_name

        # Author/vendor tags that are not runtime vendors
        self.not_runtime_vendors = {
            "ALMALENCE",
            "ARM",
            "EPIC",
            CanonicalExtensionAuthorKind.EXT.value,
            "EXTX",
            "FREDEMMOTT",
            "INTEL",
            CanonicalExtensionAuthorKind.KHR.value,
            "PLUTO",
            "UNITY",
        }

    def is_runtime_vendor(self, vendor_tag: str) -> bool:
        """Guess if a vendor/author is a runtime vendor."""
        # Just a guess/heuristic
        canonical_vendor = self.canonicalize_vendor_tag(vendor_tag)
        return (
            canonical_vendor in self.known
            and canonical_vendor not in self.not_runtime_vendors
        )

    def get_vendor_name(self, vendor_tag: str) -> str | None:
        """Get the vendor's name from their author tag, if possible."""
        _, name = self._clean_and_lookup_tag_and_name(vendor_tag)
        return name

    def _clean_and_lookup_tag_and_name(self, vendor_tag: str) -> tuple[str, str | None]:
        # try tag to name
        name = self.known.get(vendor_tag)
        if not name:
            # try stripping experimental suffix and doing tag to name
            vendor_tag, _ = split_experimental_suffix(vendor_tag)
            name = self.known.get(vendor_tag)
        # vendor_tag is possibly cleaned
        # name is possibly None
        return vendor_tag, name

    def canonicalize_vendor_tag(self, vendor_tag: str) -> str:
        """Get the canonical vendor tag from their author tag, if possible."""
        # try tag to name
        vendor_tag, name = self._clean_and_lookup_tag_and_name(vendor_tag)
        if name:
            # Look that name up to see what the preferred tag is,
            # otherwise use the (maybe cleaned) provided tag
            return self.name_to_tag.get(name, vendor_tag)

        # return the (maybe cleaned) provided tag
        return vendor_tag

    def vendor_name_to_canonical_tag(self, name: str) -> str | None:
        return self.name_to_tag.get(name)

    def canonicalize_and_categorize(
        self, vendor_tag: str
    ) -> CanonicalExtensionAuthorKind:
        tag = self.canonicalize_vendor_tag(vendor_tag)
        if tag == CanonicalExtensionAuthorKind.KHR.value:
            return CanonicalExtensionAuthorKind.KHR
        if tag == CanonicalExtensionAuthorKind.EXT.value:
            return CanonicalExtensionAuthorKind.EXT
        return CanonicalExtensionAuthorKind.SINGLE_VENDOR


def compute_vendor_name_and_tag(
    title: str, vendors: VendorNames
) -> tuple[str | None, str | None]:
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

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.extensions: list[ExtensionData] = []

    def handle_path(self, path_modified: str) -> ExtensionData | None:
        data = ExtensionData.try_from_adoc_path(path_modified)
        if not data:
            return None

        if data.full_name not in self.names:
            self.names.add(data.full_name)
            self.extensions.append(data)
            return data

        return None
