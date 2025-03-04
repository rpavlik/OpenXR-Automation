#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import xml.etree.ElementTree as ElementTree
from typing import Optional

import gitlab
import gitlab.v4.objects


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
                "EXT": "Multi-vendor",
                "KHR": "The Khronos Group",
            }
        )

        # Preferred tag for vendors with multiple.
        self.name_to_tag = {"Meta Platforms": "META"}

        # Author tags that are not runtime vendors
        self.not_runtime_vendors = {
            "ALMALENCE",
            "ARM",
            "EPIC",
            "EXT",
            "EXTX",
            "FREDEMMOTT",
            "INTEL",
            "KHR",
            "NV",
            "PLUTO",
            "UNITY",
        }

        for tag_name, tag_author in self.known.items():
            if not tag_name.endswith("X") and tag_author not in self.name_to_tag:
                self.name_to_tag[tag_author] = tag_name

    def is_runtime_vendor(self, vendor_code: str) -> bool:
        """Guess if a vendor/author is a runtime vendor."""
        # Just a guess/heuristic
        return vendor_code in self.known and vendor_code not in self.not_runtime_vendors

    def get_vendor_name(self, vendor_code: str) -> Optional[str]:
        """Get the vendor's name from their author code, if possible."""
        name = self.known.get(vendor_code)
        if not name and vendor_code.endswith("X"):
            name = self.known.get(vendor_code[:-1])
        return name

    def canonicalize_vendor_tag(self, vendor_tag: str) -> Optional[str]:
        """Get the canonical vendor tag from their author tag, if possible."""
        name = self.known.get(vendor_tag)
        if not name and vendor_tag.endswith("X"):
            vendor_tag = vendor_tag[:-1]
            name = self.known.get(vendor_tag)
        if name:
            return self.name_to_tag.get(name, vendor_tag)
        return vendor_tag

    def vendor_name_to_canonical_tag(self, name: str) -> Optional[str]:
        return self.name_to_tag.get(name)
