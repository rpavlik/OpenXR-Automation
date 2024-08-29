#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

from collections import defaultdict
from review_priority import ReleaseChecklistIssue
from vendors import VendorNames

from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class VendorSortPolicy:

    newest_first: bool = False
    priority: list[str] = field(default_factory=list)

    def get_custom_priority(self, ext_name: str) -> int:
        try:
            return self.priority.index(ext_name)
        except ValueError:
            # larger than the max value
            return len(self.priority)

    def get_sort_key(self, issue: ReleaseChecklistIssue):
        return (
            not issue.initial_review_complete,  # negate so "review complete" comes first
            self.get_custom_priority(issue.title),
            issue.latency if self.newest_first else -issue.latency,
        )

    @classmethod
    def from_dict(cls, vendor_policy):
        newest_first = vendor_policy.get("newest_first", False)
        priority = vendor_policy.get("priority", [])
        return cls(newest_first=newest_first, priority=priority)


class CustomSort:

    def __init__(self, vendors: VendorNames) -> None:
        self.vendors = vendors
        self.vendor_policies: dict[str, VendorSortPolicy] = defaultdict(
            VendorSortPolicy
        )

    def load_vendor_config(self, vendor_dict: dict[str, Any]):
        """Load config from the 'vendor' table in the TOML file."""
        for vendor_tag, config in vendor_dict.items():
            self.vendor_policies[vendor_tag] = VendorSortPolicy.from_dict(config)

    def perform_custom_sort(self, issues: list[ReleaseChecklistIssue]):

        # Split up
        vendor_slots: list[Optional[str]] = []

        by_vendor: dict[Optional[str], list[ReleaseChecklistIssue]] = defaultdict(list)

        for issue in issues:
            tag: Optional[str] = None
            if issue.vendor_name:
                tag = self.vendors.vendor_name_to_canonical_tag(issue.vendor_name)
            vendor_slots.append(tag)
            by_vendor[tag].append(issue)

        # Sort per-vendor lists
        for tag, issues in by_vendor.items():
            if tag:
                policy = self.vendor_policies[tag]
            else:
                policy = VendorSortPolicy()
            issues.sort(key=policy.get_sort_key)

        # Rebuild list
        result: list[ReleaseChecklistIssue] = []
        for slot in vendor_slots:
            issue = by_vendor[slot].pop(0)
            result.append(issue)
        return result
