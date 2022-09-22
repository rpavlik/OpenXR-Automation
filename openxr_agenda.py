#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set, Union, cast

import dateutil.parser
import gitlab
import gitlab.v4.objects
import requests_cache
from dotenv import load_dotenv
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from nullboard_gitlab import parse_board
from openxr_release_checklist_update import ListName
from work_item_and_collection import WorkUnit, WorkUnitCollection, get_short_ref, is_mr

load_dotenv()

EXPIRE_AFTER_SECONDS = 60 * 10  # 10 minute cache for GitLab API


class Labels:
    """Just a namespace for some label name constants."""

    NEEDS_DISCUSSION = "Needs Discussion"
    NEEDS_APPROVAL = "Needs Approval"

    NEEDS_ACTION = "Needs Action"

    PHOENIX_F2F = "Phoenix-F2F"

    OPENXR_1_1 = "OpenXR 1.1"
    CONTRACTOR_APPROVED_BACKLOG = "Contractor Approved Backlog"
    STALE = "Stale"
    FOR_CONTRACTOR = "For Contractor"
    NEEDS_MERGE_REQUEST = "Needs Merge Request"
    KHR_EXTENSIONS = "KHR Extensions"
    VENDOR_EXTENSION = "Vendor_Extension"
    OBJECTION_WINDOW = "Objection Window"
    DEVICE_PLUGIN_EXTENSION = "Device Plugin Extension"
    CONFORMANCE_NEXT = "Conformance-Next"


_SKIP_DISCUSSING_MR_LABELS = {
    Labels.OBJECTION_WINDOW,
    Labels.NEEDS_ACTION,
    Labels.STALE,
}
_SKIP_DISCUSSING_ISSUE_LABELS = {
    Labels.NEEDS_MERGE_REQUEST,
    Labels.CONTRACTOR_APPROVED_BACKLOG,
    Labels.STALE,
}
_SKIP_DRAFTS_WITHOUT_THESE_LABELS = {Labels.NEEDS_DISCUSSION, Labels.NEEDS_APPROVAL}
_SKIP_STALE_GITHUB_UNLESS_LABELED = {Labels.NEEDS_DISCUSSION, Labels.NEEDS_APPROVAL}

_DISCUSSION_TAGS = {Labels.NEEDS_DISCUSSION, Labels.NEEDS_APPROVAL}

_SKIP_DISCUSSING_LABELS = {
    Labels.DEVICE_PLUGIN_EXTENSION,
    Labels.CONFORMANCE_NEXT,
    Labels.FOR_CONTRACTOR,
    Labels.STALE,
    Labels.OPENXR_1_1,
    Labels.PHOENIX_F2F,  # next f2f
}

_SKIP_REFS = {
    "#1363",  # vulkan sync, part of the vulkan 3 work
    "#1658",  # Adjust reference space - LunarG work on hold
}

_SKIP_DISCUSSING_MILESTONES = {"OpenXR-Next Preliminary"}
_VENDOR_MILESTONE = "Vendor Extensions (outside timeline)"

_REVIEW_LISTS = {ListName.REVIEWING, ListName.WAITING_REVIEW}

_GITHUB_STALE_THRESHOLD_DELTA = timedelta(days=14)
_GITLAB_STALE_THRESHOLD_DELTA = timedelta(days=9 * 30)  # 9 months


def parse_gitlab_timestamp(timestamp: str) -> datetime:
    # Replaces the timezone info with nothing because
    # datetime.now is not timezone aware...
    return dateutil.parser.isoparse(timestamp).replace(tzinfo=None)


def get_updated_timestamp(issue_or_mr) -> datetime:
    return parse_gitlab_timestamp(issue_or_mr.updated_at)


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
    STATUS = 8
    OPENED = 9
    UPDATED = 10
    APPROVED = 11
    OBJECTION = 12
    REWORK = 13
    ASSIGNED = 14
    # NUM_COMMENTS = 8

    @classmethod
    def columns_for_mr(cls):
        return (
            cls.INDENT,
            cls.REF,
            cls.TITLE,
            cls.STATUS,
            cls.AUTHOR,
            cls.ASSIGNEE,
            cls.THUMBS,
            cls.LABELS,
            cls.OPENED,
            cls.UPDATED,
            cls.APPROVED,
            cls.OBJECTION,
            cls.REWORK,
            cls.ASSIGNED,
        )

    @classmethod
    def columns_for_issue(cls):
        return (
            cls.INDENT,
            cls.REF,
            cls.TITLE,
            cls.STATUS,
            cls.COMBINED_AUTHOR_ASSIGNEE,
            cls.LABELS,
            cls.OPENED,
            cls.UPDATED,
            cls.APPROVED,
            cls.OBJECTION,
            cls.REWORK,
            cls.ASSIGNED,
        )

    @classmethod
    def columns_for_release_checklists(cls):
        return (
            cls.INDENT,
            cls.REF,
            cls.TITLE,
            cls.STATUS,
            cls.COMBINED_AUTHOR_ASSIGNEE,
            cls.THUMBS,
            cls.LABELS,
            cls.OPENED,
            cls.UPDATED,
            cls.APPROVED,
            cls.OBJECTION,
            cls.REWORK,
            cls.ASSIGNED,
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
        if col == cls.STATUS:
            return "Status"
        if col == cls.OPENED:
            return "Opened At"
        if col == cls.UPDATED:
            return "Updated At"
        if col == cls.APPROVED:
            return "Approved"
        if col == cls.OBJECTION:
            return "Objection Window"
        if col == cls.REWORK:
            return "Rework"
        if col == cls.ASSIGNED:
            return "Assigned To"
        raise RuntimeError("Unrecognized column " + str(col))


def _maybe_italicize(s: str, italicize: bool) -> str:
    if italicize:
        return "*{}*".format(s)
    return s


def _get_col_for_issue_or_mr(
    indent: bool, issue_or_mr: Union[ProjectIssue, ProjectMergeRequest], col: Column
) -> str:
    if col == Column.INDENT:
        return "*see also*" if indent else ""

    elif col == Column.REF:
        ret = "[{}]({})".format(issue_or_mr.references["short"], issue_or_mr.web_url)
        return _maybe_italicize(ret, indent)

    if col == Column.TITLE:
        ret = issue_or_mr.title
        return _maybe_italicize(ret, indent)

    if col == Column.AUTHOR:
        ret = _format_user_dict(issue_or_mr.author) or ""
        return _maybe_italicize(ret, indent)

    if col == Column.ASSIGNEE:
        ret = _format_user_dict(issue_or_mr.author) or ""
        return _maybe_italicize(ret, indent)

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

        ret = " ".join(elements)
        return _maybe_italicize(ret, indent)
    if col == Column.THUMBS:
        if issue_or_mr.upvotes or issue_or_mr.downvotes:
            return "{}{}".format(
                ":+1: " * issue_or_mr.upvotes, ":-1: " * issue_or_mr.downvotes
            )

        ret = "No Thumbs Yet"
        return _maybe_italicize(ret, indent)
    if col == Column.LABELS:
        ret = "{}".format(", ".join(issue_or_mr.labels))
        return _maybe_italicize(ret, indent)

    if col == Column.STATUS:
        status = issue_or_mr.state
        if is_mr(issue_or_mr):
            ret = status
            return _maybe_italicize(ret, indent)
        if not issue_or_mr.has_tasks:
            ret = status
            return _maybe_italicize(ret, indent)
        ret = "{}, {}".format(status, issue_or_mr.task_status)
        return _maybe_italicize(ret, indent)
    if col == Column.OPENED:
        ret = str(parse_gitlab_timestamp(issue_or_mr.created_at).date())
        return _maybe_italicize(ret, indent)
    if col == Column.UPDATED:
        ret = str(parse_gitlab_timestamp(issue_or_mr.updated_at).date())
        return _maybe_italicize(ret, indent)
    # after the meeting, change the output .md to "&#9745;" for checked checkbox
    if col == Column.APPROVED:
        return "" if indent else "&#9744;"
    if col == Column.OBJECTION:
        return "" if indent else "&#9744;"
    if col == Column.REWORK:
        return "" if indent else "&#9744;"
    if col == Column.ASSIGNED:
        return "" if indent else "TBD"

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


@dataclass
class Agenda:
    khr_release_checklists_composing: List[WorkUnit] = field(default_factory=list)
    khr_release_checklists_reviews: List[WorkUnit] = field(default_factory=list)

    other_mrs: List[WorkUnit] = field(default_factory=list)
    other_issues: List[WorkUnit] = field(default_factory=list)

    ext_and_vendor_other: List[WorkUnit] = field(default_factory=list)
    ext_and_vendor_release_checklists_composing: List[WorkUnit] = field(
        default_factory=list
    )
    ext_and_vendor_release_checklists_reviews: List[WorkUnit] = field(
        default_factory=list
    )

    do_filter_out: bool = True

    _listed_key_refs: Set[str] = field(default_factory=set)

    def add_to_list(
        self, item: WorkUnit, item_list: List[WorkUnit], skip_if_any_skippable=False
    ) -> bool:
        log = logging.getLogger(__name__)
        if self.is_on_agenda(item):
            log.info(
                "Skipping because already on the agenda: %s: %s",
                item.ref,
                item.title,
            )
            return False
        if self.do_filter_out:
            skippable = tuple(
                should_skip_discussion_of_issue_or_mr(issue_or_mr)
                for issue_or_mr in item.all_issues_and_mrs()
            )
            if skip_if_any_skippable and any(skippable):
                log.info(
                    "Skipping because at least one issue/mr was skippable: %s: %s",
                    item.ref,
                    item.title,
                )
                return False
            if all(skippable):
                log.info(
                    "Skipping because all relevant issue/mr were skippable: %s: %s",
                    item.ref,
                    item.title,
                )
                return False
        item_list.append(item)
        self.record_on_agenda(item)
        return True

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
            self._normal_section(
                "Vendor/EXT Other Issues and MRs",
                self.ext_and_vendor_other,
                Column.columns_for_mr(),
            ),
            self._release_checklist_section(
                "Vendor/EXT Initial Composition",
                self.ext_and_vendor_release_checklists_composing,
            ),
            self._release_checklist_section(
                "Vendor/EXT Review/Waiting",
                self.ext_and_vendor_release_checklists_reviews,
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
        return self._normal_section(
            "Release checklists: {}".format(name),
            work,
            Column.columns_for_release_checklists(),
        )


def should_skip_discussion_of_issue_or_mr(
    issue_or_mr: Union[ProjectIssue, ProjectMergeRequest]
):
    labels = set(issue_or_mr.labels)
    if not labels.isdisjoint(_SKIP_DISCUSSING_LABELS):
        return True

    milestone = issue_or_mr.attributes["milestone"]
    if milestone and milestone["title"] in _SKIP_DISCUSSING_MILESTONES:
        return True

    if "merge_status" in issue_or_mr.attributes:
        # We have an MR
        mr = cast(ProjectMergeRequest, issue_or_mr)
        if not labels.isdisjoint(_SKIP_DISCUSSING_MR_LABELS):
            return True

        # Don't skip all drafts, but skip those that aren't specially marked.
        if mr.draft or mr.work_in_progress:
            if labels.isdisjoint(_SKIP_DRAFTS_WITHOUT_THESE_LABELS):
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


def maybe_create_item_for_issue(
    proj: gitlab.v4.objects.Project, work: WorkUnitCollection, issue: ProjectIssue
) -> Optional[WorkUnit]:
    ref = get_short_ref(issue)
    if ref in work.items_by_ref:
        # Can stop here without going further
        return None
    refs = [ref]
    refs.extend(
        # type data is wrong
        "!{}".format(mr_dict["iid"])  # type: ignore
        for mr_dict in issue.related_merge_requests()
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


def populate_from_checklists(agenda, proj, work: WorkUnitCollection, in_nbx_filename):

    print("Reading", in_nbx_filename)
    with open(in_nbx_filename, "r") as fp:
        existing_board = json.load(fp)

    parse_board(proj, work, existing_board)
    for item in work.items:
        if is_khr(item):
            # We take all KHR extensions on these two lists

            if item.list_name == ListName.INITIAL_COMPOSITION:
                agenda.add_to_list(item, agenda.khr_release_checklists_composing)

            if item.list_name in _REVIEW_LISTS:
                agenda.add_to_list(item, agenda.khr_release_checklists_reviews)

        else:
            # We only list vendor extensions if they're marked "Needs Discussion"
            if Labels.NEEDS_DISCUSSION not in item.key_item.labels:
                continue

            if item.list_name == ListName.INITIAL_COMPOSITION:
                agenda.add_to_list(
                    item, agenda.ext_and_vendor_release_checklists_composing
                )

            if item.list_name in _REVIEW_LISTS:
                agenda.add_to_list(
                    item, agenda.ext_and_vendor_release_checklists_reviews
                )


def populate_from_github_synced_issues(agenda, proj, work):

    log = logging.getLogger(f"{__name__}.populate_from_github_synced_issues")
    log.info("Looking for open issues from GitHub")

    now = datetime.now()
    github_stale_threshold = now - _GITHUB_STALE_THRESHOLD_DELTA

    # Grab qualified github issues
    for gh_issue in proj.issues.list(
        state="opened", labels="From GitHub", iterator=True
    ):
        issue = cast(ProjectIssue, gh_issue)
        updated = get_updated_timestamp(issue)
        if (
            _SKIP_STALE_GITHUB_UNLESS_LABELED.isdisjoint(issue.labels)
            and updated < github_stale_threshold
        ):
            log.info(
                "GitHub-imported issue %d is stale and lacking specific labels: "
                "%d days since last update",
                gh_issue.iid,
                (now - updated).days,
            )
            continue

        item = maybe_create_item_for_issue(proj, work, issue)
        if not item:
            # We already had this in the work collection
            continue

        if get_short_ref(issue) in _SKIP_REFS:
            # Intentionally skipped
            continue

        if agenda.is_on_agenda(item):
            log.info(
                "GitHub-imported issue %d is already on the agenda as %s",
                gh_issue.iid,
                item.ref,
            )
            continue

        if is_khr(item):
            agenda.add_to_list(item, agenda.other_issues, skip_if_any_skippable=True)
        else:
            agenda.add_to_list(
                item, agenda.ext_and_vendor_other, skip_if_any_skippable=True
            )


def populate_from_gitlab_label_search(agenda, proj, work):

    log = logging.getLogger(f"{__name__}.populate_from_gitlab_label_search")

    now = datetime.now()
    gitlab_stale_threshold = now - _GITLAB_STALE_THRESHOLD_DELTA

    # Grab issues to discuss
    for label in _DISCUSSION_TAGS:
        log.info("Looking for open issues labeled %s", label)
        for issue in proj.issues.list(state="opened", labels=label, iterator=True):

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
                continue

            last_updated = get_updated_timestamp(issue)
            if last_updated < gitlab_stale_threshold:
                log.info(
                    "Discussion-labeled issue %d is stale: %d days since last update",
                    issue.iid,
                    (now - last_updated).days,
                )
                continue

            if get_short_ref(issue) in _SKIP_REFS:
                # Intentionally skipped
                continue

            if is_khr(item):
                agenda.add_to_list(
                    item, agenda.other_issues, skip_if_any_skippable=True
                )
            else:
                agenda.add_to_list(
                    item, agenda.ext_and_vendor_other, skip_if_any_skippable=True
                )

        log.info("Looking for open merge requests labeled %s", label)
        for mr in proj.mergerequests.list(state="opened", labels=label, iterator=True):
            item = maybe_create_item_for_mr(proj, work, cast(ProjectMergeRequest, mr))

            if not item:
                # We already had this in the work collection
                continue

            if agenda.is_on_agenda(item):
                log.info(
                    "Discussion-labeled mr %d is already on the agenda as %s",
                    mr.iid,
                    item.ref,
                )
                continue

            last_updated = get_updated_timestamp(mr)
            if last_updated < gitlab_stale_threshold:
                log.info(
                    "Discussion-labeled mr %d is stale: %d days since last update",
                    mr.iid,
                    (now - last_updated).days,
                )
                continue

            if get_short_ref(mr) in _SKIP_REFS:
                # Intentionally skipped
                continue

            if is_khr(item):
                agenda.add_to_list(item, agenda.other_mrs, skip_if_any_skippable=True)
            else:
                agenda.add_to_list(
                    item, agenda.ext_and_vendor_other, skip_if_any_skippable=True
                )


def main(in_nbx_filename, out_md_filename):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)
    work = WorkUnitCollection()

    session = requests_cache.CachedSession(
        cache_name="gitlab_cache", expire_after=EXPIRE_AFTER_SECONDS
    )

    log.info("Connecting to GitLab")
    with session.cache_disabled():
        gl = gitlab.Gitlab(
            url=os.environ["GL_URL"],
            private_token=os.environ["GL_ACCESS_TOKEN"],
            session=session,
        )
        gl.auth()

    proj = gl.projects.get("openxr/openxr")

    agenda = Agenda()
    populate_from_checklists(agenda, proj, work, in_nbx_filename)
    populate_from_github_synced_issues(agenda, proj, work)
    populate_from_gitlab_label_search(agenda, proj, work)

    with open(out_md_filename, "w", encoding="utf-8") as fp:
        fp.write(str(agenda))


if __name__ == "__main__":
    main(
        "Nullboard-1661545038-OpenXR-Release-Checklists.nbx",
        "agenda.md",
    )
