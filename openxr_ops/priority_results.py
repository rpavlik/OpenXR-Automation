#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import datetime
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import Iterable, Optional, cast

import gitlab
import gitlab.v4.objects

from .labels import GroupLabels, MainProjectLabels, OpsProjectLabels
from .vendors import VendorNames

NOW = datetime.datetime.now(datetime.UTC)
log = logging.getLogger(__name__)

_EXT_DECOMP_RE = re.compile(r"XR_(?P<tag>[A-Z]+)(?P<experiment>X[0-9]*)?_.*")


_IGNORE_PUSH_USERS = ("rpavlik", "safarimonkey", "haagch", "khrbot")
"""Do not consider pushes from these users when determining latency"""


_PUSH_NOTE_RE = re.compile(r"added \d+ commit(s?)\n\n.*")


def _is_note_a_push(note: gitlab.v4.objects.ProjectMergeRequestNote):
    if not note.system:
        return False

    body = note.attributes.get("body")
    if not body:
        log.warning("No body?")
        note.pprint()
        return False

    if not _PUSH_NOTE_RE.match(body):
        return False

    return True


def _is_note_an_author_push(note: gitlab.v4.objects.ProjectMergeRequestNote):
    return _is_note_a_push(note) and note.author["username"] not in _IGNORE_PUSH_USERS


def _created_date(n):
    return datetime.datetime.fromisoformat(n.attributes["created_at"])


@dataclass
class ReleaseChecklistIssue:
    issue_obj: gitlab.v4.objects.ProjectIssue

    status: str

    latest_status_label_event: gitlab.v4.objects.ProjectIssueResourceLabelEvent

    mr: gitlab.v4.objects.ProjectMergeRequest

    vendor_name: Optional[str] = None
    vendor_tag: Optional[str] = None

    offset: int = 0
    """Corrective latency offset"""

    @property
    def initial_design_review_complete(self) -> bool:
        return (
            OpsProjectLabels.INITIAL_DESIGN_REVIEW_COMPLETE
            in self.issue_obj.attributes["labels"]
        )

    @property
    def initial_spec_review_complete(self) -> bool:
        return (
            OpsProjectLabels.INITIAL_SPEC_REVIEW_COMPLETE
            in self.issue_obj.attributes["labels"]
        )

    @property
    def is_khr(self) -> bool:
        return GroupLabels.KHR_EXT in self.issue_obj.attributes["labels"]

    @property
    def is_vendor(self) -> bool:
        return GroupLabels.VENDOR_EXT in self.issue_obj.attributes["labels"]

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
        age = NOW - pending_since
        return age.days + self.offset

    @cached_property
    def ops_issue_age(self):
        """Time since ops issue creation in days"""
        created_at = datetime.datetime.fromisoformat(
            self.issue_obj.attributes["created_at"]
        )
        age = NOW - created_at
        return age.days

    @cached_property
    def mr_age(self):
        """Time since merge request creation in days"""
        created_at = datetime.datetime.fromisoformat(self.mr.attributes["created_at"])
        age = NOW - created_at
        return age.days

    @cached_property
    def has_conflicts(self):
        """If the MR has merge conflicts."""
        return self.mr.attributes.get("has_conflicts", False)

    @property
    def needs_author_action(self):
        return MainProjectLabels.NEEDS_AUTHOR_ACTION in self.mr.attributes["labels"]

    @property
    def unchangeable(self):
        # TODO should not see this on the MR but...
        return (
            OpsProjectLabels.UNCHANGEABLE in self.mr.attributes["labels"]
            or OpsProjectLabels.UNCHANGEABLE in self.issue_obj.attributes["labels"]
        )

    @cached_property
    def _last_author_revision_push_with_date(
        self,
    ) -> tuple[
        Optional[gitlab.v4.objects.ProjectMergeRequestNote], Optional[datetime.datetime]
    ]:
        """The system note and date for the last non-bot, non-spec-editor/contractor push to the MR."""

        # def format_user(n):
        #     return f'  ({n.attributes["author"]["username"]})'
        pushes_by_create_date = {
            _created_date(n): cast(gitlab.v4.objects.ProjectMergeRequestNote, n)
            for n in self.mr_notes
            if _is_note_an_author_push(
                cast(gitlab.v4.objects.ProjectMergeRequestNote, n)
            )
        }
        latest_date = max(pushes_by_create_date.keys(), default=None)
        if not latest_date:
            return None, None
        return (
            pushes_by_create_date[latest_date],
            latest_date,
        )

    @cached_property
    def last_push(
        self,
    ) -> Optional[gitlab.v4.objects.ProjectMergeRequestNote]:
        """The system note for the last push to the MR."""
        pushes = [
            cast(gitlab.v4.objects.ProjectMergeRequestNote, n)
            for n in self.mr_notes
            if _is_note_a_push(cast(gitlab.v4.objects.ProjectMergeRequestNote, n))
        ]
        if not pushes:
            return None
        return pushes[-1]

    @cached_property
    def last_author_revision_push_age(
        self,
    ) -> int:
        """Days since the last non-bot, non-spec-editor/contractor push to the MR."""
        _, last_push_date = self._last_author_revision_push_with_date
        if not last_push_date:
            log.info("No last push date for %s, using MR create date", self.title)
            last_push_date = datetime.datetime.fromisoformat(
                self.mr.attributes["created_at"]
            )
        return (NOW - last_push_date).days

    @cached_property
    def mr_notes(self):
        return list(self.mr.notes.list(iterator=True))

    @property
    def author_category_priority(self):
        author_category = 0
        if self.is_khr:
            author_category = -5
        elif self.is_multivendor:
            author_category = -3
        elif self.is_vendor:
            author_category = -1
        else:
            log.warning("Could not guess vendor category for %s", self.issue_obj.title)
        return author_category

    @property
    def checklist_completed_count(self) -> int:
        return self.issue_obj.task_completion_status["completed_count"]

    @property
    def checklist_total_count(self) -> int:
        return self.issue_obj.task_completion_status["count"]

    @property
    def title(self) -> str:
        return self.issue_obj.title

    @property
    def url(self) -> str:
        return self.issue_obj.web_url

    @property
    def mr_ref(self) -> str:
        return self.mr.references["short"]

    @property
    def mr_url(self) -> str:
        return self.mr.web_url

    def to_markdown(self, slot: int):
        # Think this does nothing because we do not block merges on
        # resolving discussions inside GitLab.
        disc_resolved = (
            ""
            if self.mr.blocking_discussions_resolved
            else " blocking discussions not resolved"
        )

        return f"""
* {slot} - [{self.title}]({self.url}) -  [MR {self.mr_ref}]({self.mr_url}) {disc_resolved}
    * Latency: {self.latency} days since last status change
    * Ops issue age: {self.ops_issue_age} days
    * MR age: {self.mr_age} days
    * Checklist: {self.checklist_completed_count} of {self.checklist_total_count} checked
    * Labels: {', '.join(self.issue_obj.labels)}
    """.strip()

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
            # handle deleted label
            and e.attributes["label"] is not None
            and e.attributes["label"]["name"] == status
        ]
        assert status_events
        latest_event = status_events[-1]

        m = _EXT_DECOMP_RE.match(issue.title)
        vendor: Optional[str] = None
        tag: Optional[str] = None
        if m is not None:
            tag = m.group("tag")
            assert tag is not None
            vendor = vendors.get_vendor_name(tag)

        return cls(
            issue_obj=issue,
            status=status,
            latest_status_label_event=cast(
                gitlab.v4.objects.ProjectIssueResourceLabelEvent, latest_event
            ),
            mr=main_mr,
            vendor_name=vendor,
            vendor_tag=tag,
        )


@dataclass
class PriorityResults:
    """Result of prioritizing extension review requests."""

    list_markdown: str
    """The main list of priorities."""

    sorted_items: list[ReleaseChecklistIssue]
    """The release checklist items sorted in priority order."""

    vendor_name_to_slots: dict[str, list[int]]
    """Maps vendor name to a list of slot numbers their extensions occupy."""

    unknown_slots: list[int]
    """Slots occupied by extensions for which we could not guess the vendor."""

    @classmethod
    def from_sorted_items(
        cls, sorted_items: list[ReleaseChecklistIssue]
    ) -> "PriorityResults":
        """Populate the object from an already-sorted list."""

        vendor_name_to_slots: dict[str, list[int]] = defaultdict(list)
        unknown_slots: list[int] = []

        body_text: list[str] = []

        for slot, item in enumerate(sorted_items, 1):
            body_text.append(item.to_markdown(slot))

            if item.vendor_name is not None:
                vendor_name_to_slots[item.vendor_name].append(slot)
            else:
                unknown_slots.append(slot)

        return cls(
            "\n".join(body_text),
            sorted_items=sorted_items,
            vendor_name_to_slots=vendor_name_to_slots,
            unknown_slots=unknown_slots,
        )


def apply_offsets(offsets: dict[str, int], items: Iterable[ReleaseChecklistIssue]):
    for item in items:
        offset = offsets.get(item.title)
        if offset:
            item.offset = offset
            log.info("%s: Applying offset of %d", item.title, offset)
