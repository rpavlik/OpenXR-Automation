#!/usr/bin/env python3 -i
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import dataclasses
import logging
from collections.abc import Generator, Iterable, Sequence
from typing import Dict, List, Optional, Set, Tuple, Union, assert_never, cast

import gitlab
import gitlab.v4.objects
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from openxr_ops.gitlab import ReferenceType


def make_url_list_item(issue_or_mr: ProjectIssue | ProjectMergeRequest) -> str:
    return "• {}: {} {}".format(
        issue_or_mr.references["short"], issue_or_mr.title, issue_or_mr.web_url
    )


def is_mr(issue_or_mr: ProjectIssue | ProjectMergeRequest):
    return "merge_status" in issue_or_mr.attributes


@dataclasses.dataclass
class WorkUnit:
    key_item: ProjectIssue | ProjectMergeRequest

    mrs: list[ProjectMergeRequest] = dataclasses.field(default_factory=list)
    issues: list[ProjectIssue] = dataclasses.field(default_factory=list)

    list_name: str | None = None

    @property
    def ref(self):
        return self.key_item.references["short"]

    @property
    def title(self):
        return self.key_item.title

    @property
    def web_url(self):
        return self.key_item.web_url

    @property
    def is_mr(self):
        return is_mr(self.key_item)

    def refs(self):
        yield self.ref
        for issue in self.issues:
            yield issue.references["short"]
        for mr in self.mrs:
            yield mr.references["short"]

    def get_key_item_as_mr(self) -> ProjectMergeRequest | None:
        if not self.is_mr:
            return None
        return cast(ProjectMergeRequest, self.key_item)

    def get_key_item_as_issue(self) -> ProjectIssue | None:
        if self.is_mr:
            return None
        return cast(ProjectIssue, self.key_item)

    def make_url_list(self):
        yield make_url_list_item(self.key_item)

    def make_url_list_excluding_key_item(self):
        for issue in self.issues:
            yield make_url_list_item(issue)
        for mr in self.mrs:
            yield make_url_list_item(mr)

    def non_key_issues_and_mrs(
        self,
    ) -> Generator[ProjectIssue | ProjectMergeRequest, None, None]:
        yield from self.issues
        yield from self.mrs

    def all_issues_and_mrs(
        self,
    ) -> Generator[ProjectIssue | ProjectMergeRequest, None, None]:
        yield self.key_item
        yield from self.non_key_issues_and_mrs()


def get_short_ref(api_item: ProjectIssue | ProjectMergeRequest) -> str:
    return api_item.references["short"]


def get_issue_from_data_or_project(
    proj: gitlab.v4.objects.Project,
    ref: str,
    ref_num: int,
    data: dict[str, ProjectIssue | ProjectMergeRequest] | None = None,
) -> ProjectIssue:
    if data and ref in data:
        return cast(ProjectIssue, data[ref])
    return proj.issues.get(ref_num)


def get_mr_from_data_or_project(
    proj: gitlab.v4.objects.Project,
    ref: str,
    ref_num: int,
    data: dict[str, ProjectIssue | ProjectMergeRequest] | None = None,
) -> ProjectMergeRequest:
    if data and ref in data:
        return cast(ProjectMergeRequest, data[ref])
    return proj.mergerequests.get(ref_num)


@dataclasses.dataclass
class WorkUnitCollection:
    items_by_ref: dict[str, WorkUnit] = dataclasses.field(default_factory=dict)
    items: list[WorkUnit] = dataclasses.field(default_factory=list)

    do_not_merge: set[str] = dataclasses.field(default_factory=set)
    """Refs that should not be fully parsed/merged"""

    def _add_item(
        self,
        api_item: ProjectIssue | ProjectMergeRequest,
    ) -> WorkUnit | None:
        log = logging.getLogger(__name__)
        short_ref = get_short_ref(api_item)
        if short_ref in self.items_by_ref:
            return None
        if short_ref in self.do_not_merge:
            log.info(
                "WorkUnitCollection: Not adding item for %s - in do_not_merge",
                short_ref,
            )
            return None
        item = WorkUnit(key_item=api_item)
        self.items.append(item)
        self.items_by_ref[short_ref] = item
        log.info("WorkUnitCollection: adding item %s: %s", short_ref, api_item.title)
        return item

    def _add_refs_to_workunit(
        self,
        proj: gitlab.v4.objects.Project,
        item: WorkUnit,
        refs: Iterable[str],
        data: dict[str, ProjectIssue | ProjectMergeRequest] | None = None,
    ):
        log = logging.getLogger(__name__)
        for ref in refs:
            ref_type = ReferenceType.parse_short_reference(ref)
            ref_num = int(ref[1:])
            if ref_type == ReferenceType.ISSUE:
                issue = get_issue_from_data_or_project(proj, ref, ref_num, data)
                self.add_issue_to_workunit(item, issue)
            elif ref_type == ReferenceType.MERGE_REQUEST:
                try:
                    mr = get_mr_from_data_or_project(proj, ref, ref_num, data)
                except:
                    log.warning("Could not get MR with ref %s", ref)
                    continue
                self.add_mr_to_workunit(item, mr)
            else:
                assert_never(ref_type)

    def add_or_get_item_for_refs(
        self,
        proj: gitlab.v4.objects.Project,
        refs: Sequence[str],
        data: dict[str, ProjectIssue | ProjectMergeRequest] | None = None,
    ) -> WorkUnit:
        """Add a new item for the given refs, or extend an existing item. Returns the relevant item in either case"""
        item, _ = self._add_refs(proj, refs, data)
        if item is None:
            items = self.get_items_for_refs(refs)
            item = items[0]
        return item

    def add_refs(
        self,
        proj: gitlab.v4.objects.Project,
        refs: Sequence[str],
        data: dict[str, ProjectIssue | ProjectMergeRequest] | None = None,
    ) -> WorkUnit | None:
        """Add a new item for the given refs, or extend an existing item and return None if they overlap one."""
        item, is_new = self._add_refs(proj, refs, data)
        if is_new:
            return item
        return None

    def get_items_for_refs(self, refs: Sequence[str]) -> list[WorkUnit]:
        """Return a list of all unique WorkUnits that the refs belong to."""
        log = logging.getLogger(__name__)
        retrieved_items: list[WorkUnit] = []
        retrieved_key_refs: set[str] = set()
        log.debug("Getting items for refs %s", str(refs))
        for ref in refs:
            if ref in self.do_not_merge:
                log.info(
                    "WorkUnitCollection.get_items_for_refs: Not returning WorkUnit "
                    "for %s - in do_not_merge",
                    ref,
                )
                continue
            if ref not in self.items_by_ref:
                # this ref not known already
                log.debug("We don't yet know about %s", ref)
                continue

            retrieved_item = self.items_by_ref[ref]
            if retrieved_item.ref in retrieved_key_refs:
                # already got this one in the list
                log.debug(
                    "We know about %s, and already found the corresponding item %s in these refs",
                    ref,
                    retrieved_item.ref,
                )
                continue

            # OK retrieve this new one. Hopefully only hit this code once per call...
            retrieved_items.append(retrieved_item)
            retrieved_key_refs.add(retrieved_item.ref)

        return retrieved_items

    def _add_refs(
        self,
        proj: gitlab.v4.objects.Project,
        refs: Sequence[str],
        data: dict[str, ProjectIssue | ProjectMergeRequest] | None = None,
    ) -> tuple[WorkUnit | None, bool]:
        """Add a new item for the given refs, or extend an existing item and return None if they overlap one."""

        item: WorkUnit | None = None
        items = self.get_items_for_refs(refs)
        if items:
            log = logging.getLogger(__name__)
            # We have overlap with at least one existing item.
            if len(items) > 1:
                log.warning(
                    "The provided references overlap with more than one existing work unit, choosing the first arbitrarily: %s",
                    ", ".join(item.ref for item in items),
                )
            item = items[0]
            # we had at least some overlap, add remaining refs!
            self._add_refs_to_workunit(proj, item, refs, data)
            # Not a new thing.
            return item, False

        # OK, nothing in common with existing items
        # Make an item for the first ref
        refs_filtered = [r for r in refs if r not in self.do_not_merge]
        if not refs_filtered:
            return item, False
        ref = refs_filtered[0]
        ref_type = ReferenceType.parse_short_reference(ref)
        ref_num = int(ref[1:])

        if ref_type == ReferenceType.ISSUE:
            issue = get_issue_from_data_or_project(proj, ref, ref_num, data)
            item = self.add_issue(proj, issue, also_add_related_mrs=False)

        elif ref_type == ReferenceType.MERGE_REQUEST:
            mr = get_mr_from_data_or_project(proj, ref, ref_num, data)
            item = self.add_mr(proj, mr)

        else:
            assert_never(ref_type)

        assert item

        # Add subsequent refs to it
        self._add_refs_to_workunit(proj, item, refs[1:], data)
        return item, True

    def add_issue(
        self,
        proj: gitlab.v4.objects.Project,
        issue: ProjectIssue,
        also_add_related_mrs: bool = True,
    ) -> WorkUnit | None:
        item = self._add_item(issue)
        if not item:
            return None
        if also_add_related_mrs:
            self.add_related_mrs_to_issue_workunit(proj, item)
        return item

    def add_related_mrs_to_issue_workunit(
        self, proj: gitlab.v4.objects.Project, item: WorkUnit
    ):
        issue = item.get_key_item_as_issue()
        if not issue:
            raise RuntimeError("You passed in a workunit from an MR, not an issue!")

        # TODO closed_by instead?
        for mr_dict in issue.related_merge_requests():
            mr_num: int = mr_dict["iid"]  # type: ignore
            self.add_mr_to_workunit_by_number(proj, item, mr_num)

    def add_mr_to_workunit_by_number(
        self, proj: gitlab.v4.objects.Project, item: WorkUnit, mr_num: int
    ):
        mr = proj.mergerequests.get(mr_num)
        self.add_mr_to_workunit(item, mr)

    def add_issue_to_workunit_by_number(
        self, proj: gitlab.v4.objects.Project, item: WorkUnit, issue_num: int
    ):
        issue = proj.issues.get(issue_num)
        self.add_issue_to_workunit(item, issue)

    def add_mr_to_workunit(self, item: WorkUnit, mr: ProjectMergeRequest) -> int:
        log = logging.getLogger(__name__)
        ref = get_short_ref(mr)
        if self._should_add_issue_or_mr_to_workunit(item, mr):
            log.debug("Adding %s to item %s", ref, item.ref)
            item.mrs.append(mr)
            return 1
        log.debug("Not adding %s to item %s, it's already in it", ref, item.ref)
        return 0

    def add_issue_to_workunit(self, item: WorkUnit, issue: ProjectIssue):
        log = logging.getLogger(__name__)
        ref = get_short_ref(issue)
        if self._should_add_issue_or_mr_to_workunit(item, issue):
            log.debug("Adding %s to item %s", ref, item.ref)
            item.issues.append(issue)
            return 1
        log.debug("Not adding %s to item %s, it's already in it", ref, item.ref)
        return 0

    def _should_add_issue_or_mr_to_workunit(
        self, item: WorkUnit, issue_or_mr: ProjectMergeRequest | ProjectIssue
    ):
        """Add to items_by_ref and return true if you should finish adding this mr/issue."""
        short_ref = issue_or_mr.references["short"]
        if short_ref in item.refs():
            return False

        self.items_by_ref[short_ref] = item
        return True

    def add_mr(
        self, _proj: gitlab.v4.objects.Project, mr: ProjectMergeRequest
    ) -> WorkUnit | None:
        item = self._add_item(mr)
        if not item:
            return None
        # TODO combine other stuff?
        return item

    def _merge_two_workunits(self, item: WorkUnit, other: WorkUnit) -> int:
        log = logging.getLogger(__name__)

        try:
            self.items.remove(other)
        except ValueError:
            log.info(
                "Could not remove item %s from list: not found, probably already removed",
                other.ref,
            )
        items_transfered = 0
        key_mr = other.get_key_item_as_mr()
        if key_mr:
            items_transfered += self.add_mr_to_workunit(item, key_mr)

        key_issue = other.get_key_item_as_issue()
        if key_issue:
            items_transfered += self.add_issue_to_workunit(item, key_issue)

        for issue in other.issues:
            items_transfered += self.add_issue_to_workunit(item, issue)

        for mr in other.mrs:
            items_transfered += self.add_mr_to_workunit(item, mr)

        log.debug(
            "Transfered %d items from %s to %s during merge.",
            items_transfered,
            other.ref,
            item.ref,
        )
        return items_transfered

    def merge_workunits(self, item: WorkUnit, other: WorkUnit):
        self._merge_two_workunits(item, other)

    def merge_many_workunits(self, items: Sequence[WorkUnit]):
        log = logging.getLogger(__name__)

        deduplicated = []
        deduped_refs = set()
        for item in items:
            if item.ref not in deduped_refs:
                deduplicated.append(item)
                deduped_refs.add(item.ref)

        main_item = deduplicated[0]
        items_transferred = 0
        for item in deduplicated[1:]:
            items_transferred += self._merge_two_workunits(main_item, item)

        if len(deduplicated) > 1:
            log.info(
                "Merge: transfered %d items into %s from %d unique work units",
                items_transferred,
                main_item.ref,
                len(deduplicated) - 1,
            )
        return deduplicated[0]
