#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from gitlab.v4.objects import ProjectIssue, ProjectIssueResourceLabelEvent

from .checklists import ColumnName, ReleaseChecklistCollection
from .gitlab import OpenXRGitlab
from .vendors import VendorNames

# 📓 📑 📝🔬

_NEW = "New"
_SHIPPED = "Shipped"
STATES = {
    # These are not labels
    _NEW: "🆕",
    _SHIPPED: "🚢",
    # These are status labels
    ColumnName.INACTIVE: "💤",
    ColumnName.INITIAL_DESIGN.value: "📓",
    ColumnName.AWAITING_DESIGN_REVIEW.value: "🥼",
    ColumnName.NEEDS_DESIGN_REVISION.value: "💬",
    ColumnName.COMPOSITION_OR_ELABORATION: "📝",
    ColumnName.AWAITING_SPEC_REVIEW.value: "🔍",
    ColumnName.NEEDS_SPEC_REVISION.value: "📑",
    ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION.value: "☑️",
    ColumnName.NEEDS_OTHER.value: "🗳️",
    ColumnName.FROZEN_NEEDS_IMPL_OR_CTS.value: "💻",
    ColumnName.RELEASE_PENDING.value: "💯",
}


@dataclass
class IssueEvent:
    issue_title: str
    timestamp: datetime
    label: str

    @classmethod
    def from_resource_label_event(
        cls, issue_title: str, evt: ProjectIssueResourceLabelEvent
    ) -> "IssueEvent":
        timestamp = datetime.fromisoformat(evt.attributes["created_at"])
        return cls(
            timestamp=timestamp,
            issue_title=issue_title,
            label=evt.attributes["label"]["name"],
        )

    @classmethod
    def yield_events_from_issue(cls, issue: ProjectIssue):
        title = issue.attributes["title"]
        yield cls(
            timestamp=datetime.fromisoformat(issue.attributes["created_at"]),
            issue_title=title,
            label=_NEW,
        )
        for evt in issue.resourcelabelevents.list(iterator=True):
            if evt.attributes["action"] != "add":
                continue
            label_dict = evt.attributes.get("label")
            if not label_dict:
                continue

            label = label_dict.get("name")
            if not label or label not in STATES:
                continue
            yield cls.from_resource_label_event(
                issue_title=title, evt=cast(ProjectIssueResourceLabelEvent, evt)
            )
        if issue.attributes["closed_at"]:
            yield cls(
                timestamp=datetime.fromisoformat(issue.attributes["closed_at"]),
                issue_title=title,
                label=_SHIPPED,
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()

    log.info("Performing startup queries")
    vendor_names = VendorNames.from_git(oxr_gitlab.main_proj)
    collection = ReleaseChecklistCollection(
        oxr_gitlab.main_proj,
        oxr_gitlab.operations_proj,
        checklist_factory=None,
        vendor_names=vendor_names,
    )

    try:
        collection.load_config("ops_issues.toml")
    except IOError:
        print("Could not load config")

    collection.load_initial_data()

    events: list[IssueEvent] = []

    with open("events.csv", "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["Timestamp", "URL", "Title", "Label"])
        for issue in collection.issue_to_mr.keys():
            issue_obj = collection.issue_str_to_cached_issue_object(issue)
            if not issue_obj:
                continue

            these_evts = list(IssueEvent.yield_events_from_issue(issue_obj))
            # print(issue_obj.attributes["title"], len(these_evts))
            emoji = [STATES[evt.label] for evt in these_evts]
            print(issue_obj.attributes["title"], "".join(emoji))
            events.extend(these_evts)

            for evt in these_evts:
                writer.writerow(
                    [
                        evt.timestamp.isoformat(),
                        issue_obj.attributes["web_url"],
                        evt.issue_title,
                        evt.label,
                    ]
                )
