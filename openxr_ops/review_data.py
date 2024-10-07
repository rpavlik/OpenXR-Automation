#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, cast

from gitlab.v4.objects import ProjectIssue, ProjectIssueResourceLabelEvent

from .checklists import ReleaseChecklistCollection
from .gitlab import OpenXRGitlab
from .priority_results import ReleaseChecklistIssue
from .vendors import VendorNames

_NEEDSREVIEW_LABEL = "status:NeedsReview"


def load_needs_review(
    collection: ReleaseChecklistCollection,
) -> List[ReleaseChecklistIssue]:
    log.info("Loading items that need review")
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


# 📓 📑 📝🔬

_NEW = "New"
_SHIPPED = "Shipped"
STATES = {
    # These are not labels
    _NEW: "🆕",
    _SHIPPED: "🚢",
    # These are status labels
    "status:Inactive": "💤",
    "status:InitialComposition": "📓",
    "status:NeedsReview": "🔬",
    "status:NeedsRevision": "📑",
    "status:NeedsChampionApprovalOrRatification": "☑️",
    "status:NeedsOther": "🗳️",
    "status:FrozenNeedsImplOrCTS": "💻",
    "status:ReleasePending": "⏰",
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

    # parser.add_argument("--html", type=str, help="Output HTML to filename")
    # parser.add_argument("--extra", type=str, help="Extra text to add to HTML footer")
    # parser.add_argument(
    #     "--config",
    #     type=str,
    #     help="TOML file to read config from, including latency offsets and custom sorts",
    # )
    # parser.add_argument(
    #     "--offsets",
    #     type=str,
    #     help="TOML file to read latency offsets from",
    # )
    # parser.add_argument(
    #     "--extra-safe",
    #     type=str,
    #     help="Extra text to add to HTML footer without escaping special characters",
    # )

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

        # for evt in IssueEvent.yield_events_from_issue(issue_obj):
        #     events.append(evt)

        # mr_num = collection.issue_to_mr[issue]
        # mr = collection.proj.mergerequests.get(mr_num)

        # items.append(
        #     ReleaseChecklistIssue.create(issue_obj, mr, collection.vendor_names)
        # )
        # items = load_needs_review(collection)

        # if args.offsets:
        #     with open(args.offsets, "rb") as fp:
        #         offsets = tomllib.load(fp)
        #     apply_offsets(offsets, items)

        # config: Optional[dict] = None
        # if args.config:
        #     log.info("Opening config %s", args.config)
        #     with open(args.config, "rb") as fp:
        #         config = tomllib.load(fp)
        #     if "offsets" in config:
        #         log.info("Applying offsets from config")
        #         apply_offsets(config["offsets"], items)

        # items[0].mr.pprint()
        # mr = items[0].mr
        # for note in mr.notes.list(iterator=True):
        #     note.pprint()

        # print("-----")
        # from pprint import pprint

        # for evt in IssueEvent.yield_events_from_issue(items[0].issue_obj):
        #     # for evt in items[0].issue_obj.resourcelabelevents.list(iterator=True):
        #     pprint(evt)
