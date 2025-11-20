#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .priority_results import ReleaseChecklistIssue
from .vendors import VendorNames

log = logging.getLogger(__name__)


class SorterBase:
    def get_sort_description(self) -> list[str]:
        raise NotImplementedError

    def get_sorted(
        self, items: list[ReleaseChecklistIssue]
    ) -> list[ReleaseChecklistIssue]:
        raise NotImplementedError


class BasicSpecReviewSort(SorterBase):
    """A standard basic sort, primarily for spec review queue."""

    def __init__(self, _: VendorNames, vendor_config: dict[str, Any]) -> None:
        pass

    def get_sort_description(self):
        return [
            "whether initial spec review is complete (higher priority) or not complete (lower priority)",
            "author category (KHR highest priority, then EXT, then single vendor)",
            "latency (time since put in review), older is higher priority",
        ]

    def get_sorted(self, items: list[ReleaseChecklistIssue]):
        """Sort review requests and return output."""
        log.info("Sorting %d items that need review, using basic sorter", len(items))

        def get_sort_key(issue: ReleaseChecklistIssue):
            return (
                not issue.initial_spec_review_complete,  # negate so "review complete" comes first
                issue.author_category_priority,
                -issue.latency,  # negate so largest comes first
            )

        sorted_items = list(
            sorted(
                items,
                key=get_sort_key,
            )
        )
        return sorted_items


class BasicDesignReviewSort(SorterBase):
    """A basic sort for the design review queue."""

    def __init__(self, _: VendorNames, vendor_config: dict[str, Any]) -> None:
        pass

    def get_sort_description(self):
        return [
            "whether initial design review is complete (higher priority) or not complete (lower priority)",
            "author category (KHR highest priority, then EXT, then single vendor)",
            "latency (time since put in review), older is higher priority",
        ]

    def get_sorted(self, items: list[ReleaseChecklistIssue]):
        """Sort review requests and return output."""
        log.info("Sorting %d items that need review, using basic sorter", len(items))

        def get_sort_key(issue: ReleaseChecklistIssue):
            return (
                not issue.initial_design_review_complete,  # negate so "review complete" comes first
                issue.author_category_priority,
                -issue.latency,  # negate so largest comes first
            )

        sorted_items = list(
            sorted(
                items,
                key=get_sort_key,
            )
        )
        return sorted_items


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
            not issue.initial_spec_review_complete,  # negate so "review complete" comes first
            self.get_custom_priority(issue.title),
            issue.latency if self.newest_first else -issue.latency,
        )

    def describe(self):
        """Describe for the sort description."""
        parts = ["extensions with initial review complete first"]
        if self.priority:
            prio_exts = f"[{', '.join(self.priority)}]"
            parts.append(
                f"then prioritizing the following in the specified order: {prio_exts}"
            )
        if self.newest_first:
            parts.append("then newest (lowest latency) first")
        return ", ".join(parts)

    @classmethod
    def from_dict(cls, vendor_policy):
        newest_first = vendor_policy.get("newest_first", False)
        priority = vendor_policy.get("priority", [])
        return cls(newest_first=newest_first, priority=priority)


class CustomizedSort(SorterBase):
    def __init__(self, vendors: VendorNames, vendor_config: dict[str, Any]) -> None:
        self.vendors: VendorNames = vendors
        self.vendor_config: dict[str, Any] = vendor_config
        self.initial_sort = BasicSpecReviewSort(vendors, vendor_config)

        self.vendor_policies: dict[str, VendorSortPolicy] = defaultdict(
            VendorSortPolicy
        )
        for vendor_tag, config in self.vendor_config.items():
            self.vendor_policies[vendor_tag] = VendorSortPolicy.from_dict(config)

    def get_sort_description(self):
        parts = list(self.initial_sort.get_sort_description()) + [
            "Preserving the association between review slots and vendors, re-sort those vendor's extensions where the"
            " vendor has provided an alternate policy:",
        ]
        parts.extend(
            f"{tag}: {policy.describe()}"
            for tag, policy in self.vendor_policies.items()
        )

        return parts

    def get_sorted(self, items: list[ReleaseChecklistIssue]):
        # Initial sort to assign slots to vendors
        issues = self.initial_sort.get_sorted(items)
        log.info(
            "Re-sorting %d items that need review, using %d custom vendor policies",
            len(items),
            len(self.vendor_policies),
        )

        # Split up
        vendor_slots: list[str | None] = []

        by_vendor: dict[str | None, list[ReleaseChecklistIssue]] = defaultdict(list)

        for issue in issues:
            tag: str | None = None
            if issue.vendor_name:
                tag = self.vendors.vendor_name_to_canonical_tag(issue.vendor_name)
            vendor_slots.append(tag)
            by_vendor[tag].append(issue)

        # Sort per-vendor lists as required
        for tag, vendor_issues in by_vendor.items():
            if tag and tag in self.vendor_policies:
                policy = self.vendor_policies[tag]
                vendor_issues.sort(key=policy.get_sort_key)

        # Rebuild list
        result: list[ReleaseChecklistIssue] = []
        for slot in vendor_slots:
            issue = by_vendor[slot].pop(0)
            result.append(issue)
        return result


SORTERS = {
    "custom": CustomizedSort,
    "basic": BasicSpecReviewSort,
    "basic_design": BasicDesignReviewSort,
}
