#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import enum
import xml.etree.ElementTree as ElementTree
from typing import Optional

import gitlab
import gitlab.v4.objects

from openxr_ops.extensions import split_experimental_suffix


class CanonicalExtensionAuthorKind(enum.Enum):
    KHR = "KHR"
    EXT = "EXT"
    SINGLE_VENDOR = "SINGLE_VENDOR"


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

    def get_vendor_name(self, vendor_tag: str) -> Optional[str]:
        """Get the vendor's name from their author tag, if possible."""
        _, name = self._clean_and_lookup_tag_and_name(vendor_tag)
        return name

    def _clean_and_lookup_tag_and_name(
        self, vendor_tag: str
    ) -> tuple[str, Optional[str]]:
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

    def vendor_name_to_canonical_tag(self, name: str) -> Optional[str]:
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
