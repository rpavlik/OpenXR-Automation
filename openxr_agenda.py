#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

import json
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set, Union, cast

import gitlab
import gitlab.v4.objects
import requests_cache
from dotenv import load_dotenv
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from nullboard_gitlab import parse_board
from openxr_release_checklist_update import ListName
from work_item_and_collection import WorkUnit, WorkUnitCollection, get_short_ref

load_dotenv()

_SKIP_DISCUSSING_MR_LABELS = ("Objection Window", "Needs Action")
_SKIP_DISCUSSING_ISSUE_LABELS = ["Needs Merge Request"]
_SKIP_DISCUSSING_MILESTONES = ["OpenXR-Next Preliminary"]
_SKIP_DRAFTS_WITHOUT_THESE_LABELS = ["Needs Discussion"]


class Labels:
    KHR_EXTENSIONS = "KHR Extensions"
    VENDOR_EXTENSION = "Vendor_Extension"


_VENDOR_MILESTONE = "Vendor Extensions (outside timeline)"

_SKIP_DISCUSSING_LABELS = (
    "Device Plugin Extension",
    "Conformance-Next",
    "For Contractor",
    "Stale",
    "Phoenix-F2F",  # next f2f
)


def _format_user_dict(userdict: Optional[Dict[str, str]]) -> Optional[str]:
    if not userdict:
        return None
    if userdict["username"] == "khrbot":
        return None
    ret = "[{} (@{})]({})".format(
        userdict["name"], userdict["username"], userdict["web_url"]
    )
    if userdict["state"] != "active":
        ret += " - inactive"
    return ret


class Column(Enum):
    INDENT = 0
    REF = 1
    TITLE = 2
    AUTHOR = 3
    ASSIGNEE = 4
    COMBINED_AUTHOR_ASSIGNEE = 5
    THUMBS = 6
    LABELS = 7
    TASK_COMPLETION_STATUS = 8
    # NUM_COMMENTS = 8

    @classmethod
    def columns_for_mr(cls):
        return (
            cls.INDENT,
            cls.REF,
            cls.TITLE,
            cls.AUTHOR,
            cls.ASSIGNEE,
            cls.THUMBS,
            cls.LABELS,
        )

    @classmethod
    def columns_for_issue(cls):
        return (
            cls.INDENT,
            cls.REF,
            cls.TITLE,
            cls.COMBINED_AUTHOR_ASSIGNEE,
            cls.LABELS,
        )

    @classmethod
    def columns_for_release_checklists(cls):
        return (
            cls.INDENT,
            cls.REF,
            cls.TITLE,
            cls.TASK_COMPLETION_STATUS,
            cls.COMBINED_AUTHOR_ASSIGNEE,
            cls.THUMBS,
            cls.LABELS,
        )

    @classmethod
    def get_title(cls, col) -> str:
        if col == cls.INDENT:
            return ""
        if col == cls.REF:
            return "Ref"
        if col == cls.TITLE:
            return "Title"
        if col == cls.AUTHOR:
            return "Author"
        if col == cls.ASSIGNEE:
            return "Assignee"
        if col == cls.COMBINED_AUTHOR_ASSIGNEE:
            return "Author/Assignee"
        if col == cls.THUMBS:
            return "Thumbs"
        if col == cls.LABELS:
            return "Labels"
        if col == cls.TASK_COMPLETION_STATUS:
            return "Tasks"
        raise RuntimeError("Unrecognized column " + str(col))


def _get_col_for_issue_or_mr(
    indent: bool, issue_or_mr: Union[ProjectIssue, ProjectMergeRequest], col: Column
) -> str:
    if col == Column.INDENT:
        return ":heavy_plus_sign:" if indent else ":star:"

    elif col == Column.REF:
        return "[{}]({})".format(issue_or_mr.references["short"], issue_or_mr.web_url)

    if col == Column.TITLE:
        return issue_or_mr.title

    if col == Column.AUTHOR:
        return _format_user_dict(issue_or_mr.author) or ""

    if col == Column.ASSIGNEE:
        return _format_user_dict(issue_or_mr.author) or ""

    if col == Column.COMBINED_AUTHOR_ASSIGNEE:
        author = _format_user_dict(issue_or_mr.author)
        assignee = _format_user_dict(issue_or_mr.assignee)
        elements = []
        if author and assignee and author == assignee:
            elements.append("(Author/assignee: {})".format(author))
        else:
            if author:

                elements.append("(Author: {})".format(author))
            if assignee:
                elements.append("(Assignee: {}".format(assignee))

        return " ".join(elements)
    if col == Column.THUMBS:
        if issue_or_mr.upvotes or issue_or_mr.downvotes:
            return "{}{}".format(
                ":+1:" * issue_or_mr.upvotes, ":-1:" * issue_or_mr.downvotes
            )

        return "no thumbs yet"
    if col == Column.LABELS:
        return "{}".format(", ".join(issue_or_mr.labels))

    if col == Column.TASK_COMPLETION_STATUS:
        if not issue_or_mr.has_tasks:
            return ""
        return issue_or_mr.task_status
    # if col == Columns.NUM_COMMENTS:
    #     return
    raise RuntimeError("Not handled!")


def _make_table_row(col_contents: Iterable[str]) -> str:
    return "|{}|".format("|".join(col_contents))


def _make_table_headers(columns: Iterable[Column]) -> str:
    column_titles = [Column.get_title(col) for col in columns]
    separator = [":----" for _ in column_titles]
    return "\n".join((_make_table_row(column_titles), _make_table_row(separator)))


def _format_issue_or_mr_for_table(
    indent: bool,
    issue_or_mr: Union[ProjectIssue, ProjectMergeRequest],
    columns: Iterable[Column] = Column.columns_for_issue(),
):
    col_contents = []
    for col in columns:
        col_contents.append(_get_col_for_issue_or_mr(indent, issue_or_mr, col))
    return _make_table_row(col_contents)


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

    _listed_key_refs: Set[str] = field(default_factory=set)

    def is_on_agenda(self, item: WorkUnit) -> bool:
        return item.ref in self._listed_key_refs

    def record_on_agenda(self, item: WorkUnit):
        self._listed_key_refs.add(item.ref)

    # def add_release_checklist_composing(self, item: WorkUnit):

    def __str__(self) -> str:
        sections = [
            self._release_checklist_section(
                "KHR Initial Composition", self.khr_release_checklists_composing
            ),
            self._release_checklist_section(
                "KHR Review/Waiting", self.khr_release_checklists_reviews
            ),
            self._normal_section("Other MRs", self.other_mrs, Column.columns_for_mr()),
            self._normal_section(
                "Other Issues", self.other_issues, Column.columns_for_issue()
            ),
            self._release_checklist_section(
                "Vendor/EXT Initial Composition",
                self.ext_and_vendor_release_checklists_composing,
            ),
            self._release_checklist_section(
                "Vendor/EXT Review/Waiting",
                self.ext_and_vendor_release_checklists_reviews,
            ),
            self._normal_section(
                "Vendor/EXT Other Issues and MRs",
                self.ext_and_vendor_other,
                Column.columns_for_mr(),
            ),
        ]
        return "\n\n".join(sections)

    def _normal_section(
        self, name: str, work: List[WorkUnit], columns: Iterable[Column]
    ) -> str:
        if not work:
            return ""
        col_list = list(columns)
        lines = [
            "## {}".format(name),
            "",
            _make_table_headers(col_list),
        ]

        for item in work:
            lines.append(_format_issue_or_mr_for_table(False, item.key_item, col_list))
            for issue_or_mr in item.non_key_issues_and_mrs():
                lines.append(_format_issue_or_mr_for_table(True, issue_or_mr, col_list))
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


def should_skip_discussion_of_issue_or_mr(
    issue_or_mr: Union[ProjectIssue, ProjectMergeRequest]
):
    labels = set(issue_or_mr.labels)
    if not labels.isdisjoint(_SKIP_DISCUSSING_LABELS):
        return True

    milestone = issue_or_mr.attributes["milestone"]
    if milestone in _SKIP_DISCUSSING_MILESTONES:
        return True

    if "merge_status" in issue_or_mr.attributes:
        # We have an MR
        mr = cast(ProjectMergeRequest, issue_or_mr)
        if not labels.isdisjoint(_SKIP_DISCUSSING_MR_LABELS):
            return True

        # Don't skip all drafts, but skip those that aren't specially marked.
        if mr.draft or mr.work_in_progress:
            if not labels.isdisjoint(_SKIP_DRAFTS_WITHOUT_THESE_LABELS):
                return True
    else:
        # We have an issue
        # issue = cast(ProjectIssue, issue_or_mr)
        if not labels.isdisjoint(_SKIP_DISCUSSING_ISSUE_LABELS):
            return True

    return False


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


def maybe_create_item_for_issue(
    proj: gitlab.v4.objects.Project, work: WorkUnitCollection, issue: ProjectIssue
) -> Optional[WorkUnit]:
    ref = get_short_ref(issue)
    if ref in work.items_by_ref:
        # Can stop here without going further
        return None
    refs = [ref]
    refs.extend(
        "!{}".format(mr_dict.iid) for mr_dict in issue.related_merge_requests().values()
    )

    return work.add_refs(proj, refs, {ref: issue})


def maybe_create_item_for_mr(
    proj: gitlab.v4.objects.Project, work: WorkUnitCollection, mr: ProjectMergeRequest
) -> Optional[WorkUnit]:
    ref = get_short_ref(mr)
    if ref in work.items_by_ref:
        # Can stop here without going further
        return None
    refs = [ref]
    closes_issues = list(mr.closes_issues())

    # data = {get_short_ref(issue): issue for issue in closes_issues}
    refs.extend("#{}".format(issue_dict.iid) for issue_dict in closes_issues)
    # refs.extend(data.keys())
    # data[ref] = mr
    return work.add_refs(proj, refs, {ref: mr})


def main(in_nbx_filename, out_md_filename):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)
    work = WorkUnitCollection()

    EXPIRE_AFTER_SECONDS = 180
    session = requests_cache.CachedSession(
        cache_name="gitlab_cache", expire_after=EXPIRE_AFTER_SECONDS
    )

    with session.cache_disabled():
        gl = gitlab.Gitlab(
            url=os.environ["GL_URL"],
            private_token=os.environ["GL_ACCESS_TOKEN"],
            session=session,
        )
        gl.auth()

    proj = gl.projects.get("openxr/openxr")

    print("Reading", in_nbx_filename)
    with open(in_nbx_filename, "r") as fp:
        existing_board = json.load(fp)

    parse_board(proj, work, existing_board)
    agenda = Agenda()

    do_filter_out = True
    # print(work.items[0].key_item.pformat())
    for item in work.items:
        if do_filter_out:
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
            agenda.record_on_agenda(item)
            continue

        if item.list_name in _REVIEW_LISTS:
            if is_khr(item):
                agenda.khr_release_checklists_reviews.append(item)
            else:
                agenda.ext_and_vendor_release_checklists_reviews.append(item)
            agenda.record_on_agenda(item)
            continue

    log.info("Looking for open issues from GitHub")
    # Grab qualified github issues
    for gh_issue in proj.issues.list(
        state="opened", label="From GitHub", iterator=True
    ):
        issue = cast(ProjectIssue, gh_issue)
        # ref = get_short_ref(issue)
        # if ref in work.items_by_ref:
        #     # Can stop here without going further
        #     continue
        # refs = [ref]
        # refs.extend(
        #     "!{}".format(mr_dict["iid"]) for mr_dict in issue.related_merge_requests()
        # )
        # item = work.add_or_get_item_for_refs(proj, refs, {ref: issue})

        # try:
        #     work.add_related_mrs_to_issue_workunit(proj, item)
        # except:
        #     # Ignore errors in related MRs
        #     pass
        item = maybe_create_item_for_issue(proj, work, issue)
        if not item:
            # We already had this in the work collection
            continue

        if agenda.is_on_agenda(item):
            log.info(
                "GitHub-imported issue %d is already on the agenda as %s",
                gh_issue.iid,
                item.ref,
            )
            continue

        if do_filter_out:
            if any(
                should_skip_discussion_of_issue_or_mr(issue_or_mr)
                for issue_or_mr in item.all_issues_and_mrs()
            ):
                log.info("Skipping github issue %s: %s", item.ref, item.title)
                continue
        if is_khr(item):
            agenda.other_issues.append(item)
        else:
            agenda.ext_and_vendor_other.append(item)
        agenda.record_on_agenda(item)

    # Grab issues to discuss
    for label in _DISCUSSION_TAGS:
        log.info("Looking for open issues labeled %s", label)
        for issue in proj.issues.list(state="opened", label=label, iterator=True):
            # try:
            #     item = work.add_issue(proj, cast(ProjectIssue, issue), False)
            # except:
            #     continue

            # if not item:
            #     # we already handled it
            #     continue

            # try:
            #     work.add_related_mrs_to_issue_workunit(proj, item)
            # except:
            #     # Ignore errors in related MRs
            #     pass

            # continue

            item = maybe_create_item_for_issue(proj, work, cast(ProjectIssue, issue))
            if not item:
                # We already had this in the work collection
                continue
            if agenda.is_on_agenda(item):
                log.info(
                    "Discussion-labeled issue %d is already on the agenda as %s",
                    issue.iid,
                    item.ref,
                )
            if do_filter_out:
                if any(
                    should_skip_discussion_of_issue_or_mr(issue_or_mr)
                    for issue_or_mr in item.all_issues_and_mrs()
                ):
                    log.info("Skipping 'other' issue %s: %s", item.ref, item.title)
                    continue

            if is_khr(item):
                agenda.other_issues.append(item)
            else:
                agenda.ext_and_vendor_other.append(item)
            agenda.record_on_agenda(item)

        log.info("Looking for open merge requests labeled %s", label)
        for mr in proj.mergerequests.list(state="opened", label=label, iterator=True):
            # try:
            #     item = work.add_mr(proj, cast(ProjectMergeRequest, mr))
            # except:
            #     continue
            # if not item:
            #     # we already handled it
            #     continue

            item = maybe_create_item_for_mr(proj, work, cast(ProjectMergeRequest, mr))
            if not item:
                # We already had this in the work collection
                continue
            if do_filter_out:
                if any(
                    should_skip_discussion_of_issue_or_mr(issue_or_mr)
                    for issue_or_mr in item.all_issues_and_mrs()
                ):
                    log.info("Skipping 'other' MR %s: %s", item.ref, item.title)
                    continue

            if is_khr(item):
                agenda.other_mrs.append(item)
            else:
                agenda.ext_and_vendor_other.append(item)
            agenda.record_on_agenda(item)

    with open(out_md_filename, "w", encoding="utf-8") as fp:
        fp.write(str(agenda))


if __name__ == "__main__":
    main(
        "Nullboard-1661545038-OpenXR-Release-Checklists.nbx",
        "agenda.md",
    )
