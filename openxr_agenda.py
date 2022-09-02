#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

from dataclasses import dataclass, field
import json
import os
import re
from typing import Dict, List, Optional, Union, cast
from work_item_and_collection import WorkUnit, WorkUnitCollection
from nullboard_gitlab import make_empty_board, parse_board, update_board

import gitlab
import gitlab.v4.objects

from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest
from dotenv import load_dotenv
from openxr_release_checklist_update import ListName


load_dotenv()


def _format_user_dict(userdict: Dict[str, str]) -> Optional[str]:
    if userdict["username"] == "khrbot":
        return None
    ret = "[{} (@{})]({})".format(
        userdict["name"], userdict["username"], userdict["web_url"]
    )
    if userdict["state"] != "active":
        ret += " - inactive"
    return ret


def _format_issue_or_mr(
    issue_or_mr: Union[ProjectIssue, ProjectMergeRequest], include_author: bool = True
):
    elements = [
        "[{}]({})".format(issue_or_mr.references["short"], issue_or_mr.web_url),
        "-",
        issue_or_mr.title,
    ]

    # Indicate the author/assignee as applicable and requested
    author = None
    if include_author:
        author = _format_user_dict(issue_or_mr.author)
    assignee = None
    if issue_or_mr.assignee:
        assignee = _format_user_dict(issue_or_mr.assignee)

    if author and assignee and author == assignee:
        elements.append("(Author/assignee: {})".format(author))
    else:
        if author:

            elements.append("(Author: {})".format(author))
        if assignee:
            elements.append("(Assignee: {}".format(assignee))

    # Thumbs
    if issue_or_mr.upvotes or issue_or_mr.downvotes:
        elements.append(
            "({}{})".format(
                ":+1:" * issue_or_mr.upvotes, ":-1:" * issue_or_mr.downvotes
            )
        )
    else:
        elements.append("(no thumbs yet)")

    # Labels
    if issue_or_mr.labels:
        elements.append("(Labels: {})".format(", ".join(issue_or_mr.labels)))
    return " ".join(elements)


@dataclass
class Agenda:
    khr_release_checklists_composing: List[WorkUnit] = field(default_factory=list)
    khr_release_checklists_reviews: List[WorkUnit] = field(default_factory=list)

    other_mrs: List[WorkUnit] = field(default_factory=list)
    other_issues: List[WorkUnit] = field(default_factory=list)

    ext_and_vendor_release_checklists_composing: List[WorkUnit] = field(
        default_factory=list
    )
    ext_and_vendor_release_checklists_reviews: List[WorkUnit] = field(
        default_factory=list
    )
    ext_and_vendor_other: List[WorkUnit] = field(default_factory=list)

    def __str__(self) -> str:
        sections = [
            self._release_checklist_section(
                "KHR Initial Composition", self.khr_release_checklists_composing
            ),
            self._release_checklist_section(
                "KHR Review/Waiting", self.khr_release_checklists_reviews
            ),
            self._normal_section("Other MRs", self.other_mrs),
            self._normal_section("Other Issues", self.other_issues),
            self._release_checklist_section(
                "Vendor/EXT Initial Composition",
                self.ext_and_vendor_release_checklists_composing,
            ),
            self._release_checklist_section(
                "Vendor/EXT Review/Waiting",
                self.ext_and_vendor_release_checklists_reviews,
            ),
            self._normal_section(
                "Vendor/EXT Other Issues and MRs", self.ext_and_vendor_other
            ),
        ]
        return "\n\n".join(sections)

    def _normal_section(self, name: str, work: List[WorkUnit]) -> str:
        if not work:
            return ""

        lines = [
            "## {}".format(name),
            "",
        ]

        for item in work:

            lines.append("* {}".format(_format_issue_or_mr(item.key_item)))
            for issue_or_mr in item.non_key_issues_and_mrs():
                lines.append("  * {}".format(_format_issue_or_mr(issue_or_mr)))
        lines.append("")
        return "\n".join(lines)

    def _release_checklist_section(self, name: str, work: List[WorkUnit]) -> str:
        if not work:
            return ""

        lines = [
            "## Release checklists: {}".format(name),
            "",
        ]

        for item in work:

            lines.append(
                "* {}".format(_format_issue_or_mr(item.key_item, include_author=False))
            )
            for issue_or_mr in item.non_key_issues_and_mrs():
                lines.append("  * {}".format(_format_issue_or_mr(issue_or_mr)))
        lines.append("")
        return "\n".join(lines)


_SKIP_DISCUSSING_LABELS = (
    "Device Plugin Extension",
    "Conformance-Next",
    "For Contractor",
    "Stale",
    "Phoenix-F2F",  # next f2f
)

_SKIP_DISCUSSING_MR_LABELS = ("Objection Window", "Needs Action")
_SKIP_DISCUSSING_ISSUE_LABELS = ["Needs Merge Request"]
_SKIP_DISCUSSING_MILESTONES = ["OpenXR-Next Preliminary"]


def should_skip_discussion_of_issue_or_mr(
    issue_or_mr: Union[ProjectIssue, ProjectMergeRequest]
):
    if any((x in issue_or_mr.labels) for x in _SKIP_DISCUSSING_LABELS):
        return True
    if any(
        x == issue_or_mr.attributes["milestone"] for x in _SKIP_DISCUSSING_MILESTONES
    ):
        return True

    if "merge_status" in issue_or_mr.attributes:
        # We have an MR
        mr = cast(ProjectMergeRequest, issue_or_mr)
        if any((x in mr.labels) for x in _SKIP_DISCUSSING_MR_LABELS):
            return True
    else:
        # We have an issue
        issue = cast(ProjectIssue, issue_or_mr)
        if any((x in issue.labels) for x in _SKIP_DISCUSSING_ISSUE_LABELS):
            return True

    return False


class Labels:
    KHR_EXTENSIONS = "KHR Extensions"
    VENDOR_EXTENSION = "Vendor_Extension"


_VENDOR_MILESTONE = "Vendor Extensions (outside timeline)"


def is_khr(item: WorkUnit) -> bool:
    for issue_or_mr in item.all_issues_and_mrs():
        if Labels.KHR_EXTENSIONS in issue_or_mr.labels:
            return True
        if Labels.VENDOR_EXTENSION in issue_or_mr.labels:
            return False
        if issue_or_mr.attributes["milestone"] == _VENDOR_MILESTONE:
            return False
    return True


_REVIEW_LISTS = {ListName.REVIEWING, ListName.WAITING_REVIEW}

_DISCUSSION_TAGS = ("Needs Discussion", "Needs Approval")


def main(in_nbx_filename, out_md_filename):
    work = WorkUnitCollection()

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )

    proj = gl.projects.get("openxr/openxr")

    print("Reading", in_nbx_filename)
    with open(in_nbx_filename, "r") as fp:
        existing_board = json.load(fp)

    parse_board(proj, work, existing_board)
    agenda = Agenda()

    print(work.items[0].key_item.pformat())
    for item in work.items:
        if all(
            should_skip_discussion_of_issue_or_mr(issue_or_mr)
            for issue_or_mr in item.all_issues_and_mrs()
        ):
            print("Skipping", item.ref, item.title)
            continue
        if item.list_name == ListName.INITIAL_COMPOSITION:
            if is_khr(item):
                agenda.khr_release_checklists_composing.append(item)
            else:
                agenda.ext_and_vendor_release_checklists_composing.append(item)
            continue

        if item.list_name in _REVIEW_LISTS:
            if is_khr(item):
                agenda.khr_release_checklists_reviews.append(item)
            else:
                agenda.ext_and_vendor_release_checklists_reviews.append(item)
            continue

    # Grab qualified github issues
    for gh_issue in proj.issues.list(
        state="opened", label="From GitHub", iterator=True
    ):
        item = work.add_issue(proj, cast(ProjectIssue, gh_issue), False)
        if not item:
            continue
        try:
            work.add_related_mrs_to_issue_workunit(proj, item)
        except:
            # Ignore errors in related MRs
            pass
        if any(
            should_skip_discussion_of_issue_or_mr(issue_or_mr)
            for issue_or_mr in item.all_issues_and_mrs()
        ):
            print("Skipping github issue", item.ref, item.title)
            continue
        if is_khr(item):
            agenda.other_issues.append(item)
        else:
            agenda.ext_and_vendor_other.append(item)

    # Grab issues to discuss
    for label in _DISCUSSION_TAGS:
        for issue in proj.issues.list(state="opened", label=label, iterator=True):
            try:
                item = work.add_issue(proj, cast(ProjectIssue, issue), False)
            except:
                continue
            if not item:
                # we already handled it
                continue
            try:
                work.add_related_mrs_to_issue_workunit(proj, item)
            except:
                # Ignore errors in related MRs
                pass
            if any(
                should_skip_discussion_of_issue_or_mr(issue_or_mr)
                for issue_or_mr in item.all_issues_and_mrs()
            ):
                print("Skipping 'other' issue", item.ref, item.title)
                continue
            if is_khr(item):
                agenda.other_issues.append(item)
            else:
                agenda.ext_and_vendor_other.append(item)

    for label in _DISCUSSION_TAGS:
        for mr in proj.mergerequests.list(state="opened", label=label, iterator=True):
            try:
                item = work.add_mr(proj, cast(ProjectMergeRequest, mr))
            except:
                continue
            if not item:
                # we already handled it
                continue
            if any(
                should_skip_discussion_of_issue_or_mr(issue_or_mr)
                for issue_or_mr in item.all_issues_and_mrs()
            ):
                print("Skipping 'other' MR", item.ref, item.title)
                continue
            if is_khr(item):
                agenda.other_mrs.append(item)
            else:
                agenda.ext_and_vendor_other.append(item)

    with open(out_md_filename, "w", encoding="utf-8") as fp:
        fp.write(str(agenda))


if __name__ == "__main__":
    main(
        "Nullboard-1661545038-OpenXR-Release-Checklists.nbx",
        "agenda.md",
    )
