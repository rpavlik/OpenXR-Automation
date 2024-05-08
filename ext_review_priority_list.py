#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import datetime
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import List, Optional, cast

import gitlab
import gitlab.v4.objects

from openxr import OpenXRGitlab
from openxr_ops.checklists import ReleaseChecklistCollection
from openxr_ops.gitlab import KHR_EXT_LABEL, VENDOR_EXT_LABEL
from openxr_ops.vendors import VendorNames

_NEEDSREVIEW_LABEL = "status:NeedsReview"
_INITIAL_COMPLETE = "initial-review-complete"

_NOW = datetime.datetime.now(datetime.UTC)

_EXT_DECOMP_RE = re.compile(r"XR_(?P<tag>[A-Z]+)_.*")


@dataclass
class ReleaseChecklistIssue:
    issue_obj: gitlab.v4.objects.ProjectIssue

    status: str

    latest_status_label_event: gitlab.v4.objects.ProjectIssueResourceLabelEvent

    mr: gitlab.v4.objects.ProjectMergeRequest

    vendor_name: Optional[str] = None

    @property
    def initial_review_complete(self) -> bool:
        return _INITIAL_COMPLETE in self.issue_obj.attributes["labels"]

    @property
    def is_khr(self) -> bool:
        return KHR_EXT_LABEL in self.issue_obj.attributes["labels"]

    @property
    def is_vendor(self) -> bool:
        return VENDOR_EXT_LABEL in self.issue_obj.attributes["labels"]

    @property
    def is_multivendor(self) -> bool:
        return "_EXT_" in self.issue_obj.title

    @cached_property
    def latency(self):
        """Time since last status change in days"""
        # TODO choose the more recent of this date or the MR update date?
        # or latest push to MR?
        pending_since = datetime.datetime.fromisoformat(
            self.latest_status_label_event.attributes["created_at"]
        )
        age = _NOW - pending_since
        return age.days

    @cached_property
    def ops_issue_age(self):
        """Time since ops issue creation in days"""
        created_at = datetime.datetime.fromisoformat(
            self.issue_obj.attributes["created_at"]
        )
        age = _NOW - created_at
        return age.days

    @cached_property
    def mr_age(self):
        """Time since merge request creation in days"""
        created_at = datetime.datetime.fromisoformat(self.mr.attributes["created_at"])
        age = _NOW - created_at
        return age.days

    def get_sort_key(self):
        author_category = 0
        if self.is_khr:
            author_category = -5
        elif self.is_multivendor:
            author_category = -3
        elif self.is_vendor:
            author_category = -1
        else:
            print(f"Could not guess vendor category for {self.issue_obj.title}")

        return (
            author_category,
            not self.initial_review_complete,  # negate so "review complete" comes first
            -self.latency,  # negate so largerst comes first
        )

    @classmethod
    def create(
        cls,
        issue: gitlab.v4.objects.ProjectIssue,
        main_mr: gitlab.v4.objects.ProjectMergeRequest,
        vendors: VendorNames,
    ):
        statuses = [
            label for label in issue.attributes["labels"] if label.startswith("status:")
        ]
        assert len(statuses) == 1
        status = statuses[0]

        status_events = [
            e
            for e in issue.resourcelabelevents.list(iterator=True)
            if e.attributes["action"] == "add"
            and e.attributes["label"]["name"] == status
        ]
        assert status_events
        latest_event = status_events[-1]

        m = _EXT_DECOMP_RE.match(issue.title)
        vendor = None
        if m is not None:
            tag = m.group("tag")
            vendor = vendors.get_vendor_name(tag)
        return cls(
            issue_obj=issue,
            status=status,
            latest_status_label_event=cast(
                gitlab.v4.objects.ProjectIssueResourceLabelEvent, latest_event
            ),
            mr=main_mr,
            vendor_name=vendor,
        )


def load_needs_review(
    collection: ReleaseChecklistCollection,
) -> List[ReleaseChecklistIssue]:
    items = []
    for issue in collection.issue_to_mr.keys():
        issue_obj = collection.issue_str_to_cached_issue_object(issue)
        if not issue_obj:
            continue

        if _NEEDSREVIEW_LABEL not in issue_obj.labels:
            continue

        # print(issue_obj.attributes["title"])

        mr_num = collection.issue_to_mr[issue]
        mr = collection.proj.mergerequests.get(mr_num)

        items.append(
            ReleaseChecklistIssue.create(issue_obj, mr, collection.vendor_names)
        )
    return items


@dataclass
class PrioritizationResults:
    """Result of prioritizing extension review requests."""

    list_markdown: str
    """The main list of priorities."""

    vendor_name_to_slots: dict[str, list[int]]
    """Maps vendor name to a list of slot numbers their extensions occupy"""

    unknown_slots: list[int]
    """Slots occupied by extensions for which we could not guess the vendor."""

    @classmethod
    def from_items(cls, items: list[ReleaseChecklistIssue]) -> "PrioritizationResults":

        sorted_items = list(
            sorted(
                items,
                key=lambda x: x.get_sort_key(),
            )
        )

        vendor_name_to_slots: dict[str, list[int]] = defaultdict(list)
        unknown_slots: list[int] = []

        body_text: list[str] = []

        for slot, item in enumerate(sorted_items, 1):
            completed_count = item.issue_obj.task_completion_status["completed_count"]
            total_count = item.issue_obj.task_completion_status["count"]
            mr_ref = item.mr.references["short"]
            mr_url = item.mr.web_url
            title = item.issue_obj.title
            url = item.issue_obj.web_url

            # Think this does nothing because we do not block merges on
            # resolving discussions inside GitLab.
            disc_resolved = (
                ""
                if item.mr.blocking_discussions_resolved
                else " blocking discussions not resolved"
            )

            body_text.append(
                f"""
* {slot} - [{title}]({url}) -  [MR {mr_ref}]({mr_url}) {disc_resolved}
    * Latency: {item.latency} days since last status change
    * Ops issue age: {item.ops_issue_age} days
    * MR age: {item.mr_age} days
    * Checklist: {completed_count} of {total_count} checked
    * Labels: {', '.join(item.issue_obj.labels)}
    """.strip()
            )
            # * Sort key: {item.get_sort_key()}

            if item.vendor_name is not None:
                vendor_name_to_slots[item.vendor_name].append(slot)
            else:
                unknown_slots.append(slot)

        return cls(
            "\n".join(body_text),
            vendor_name_to_slots=vendor_name_to_slots,
            unknown_slots=unknown_slots,
        )


if __name__ == "__main__":
    oxr_gitlab = OpenXRGitlab.create()

    print("Performing startup queries", file=sys.stderr)
    collection = ReleaseChecklistCollection(
        oxr_gitlab.main_proj,
        oxr_gitlab.operations_proj,
        checklist_factory=None,
        vendor_names=VendorNames(oxr_gitlab.main_proj),
    )

    items = load_needs_review(collection)

    results = PrioritizationResults.from_items(items)

    print(results.list_markdown)
    print("\n")

    for vendor, slots in results.vendor_name_to_slots.items():
        print(f"* {vendor} - slots {slots}")
    print(f"* Unknown: {results.unknown_slots}")
