#!/usr/bin/env python3 -i
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

import dataclasses
from typing import Any, Dict, List, Optional, Union, cast

import gitlab
import gitlab.v4.objects

from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest


def make_url_list_item(issue_or_mr) -> str:
    return "• {}: {} {}".format(
        issue_or_mr.references["short"], issue_or_mr.title, issue_or_mr.web_url
    )


@dataclasses.dataclass
class WorkUnit:
    key_item: Union[ProjectIssue, ProjectMergeRequest]

    mrs: List[ProjectMergeRequest] = dataclasses.field(default_factory=list)
    issues: List[ProjectIssue] = dataclasses.field(default_factory=list)

    list_name: Optional[str] = None

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
        return "merge_status" in self.key_item.attributes

    def refs(self):
        yield self.ref
        for issue in self.issues:
            yield issue.references["short"]
        for mr in self.mrs:
            yield mr.references["short"]

    def get_key_item_as_mr(self) -> Optional[ProjectMergeRequest]:
        if not self.is_mr:
            return None
        return cast(ProjectMergeRequest, self.key_item)

    def get_key_item_as_issue(self) -> Optional[ProjectIssue]:
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


@dataclasses.dataclass
class WorkUnitCollection:
    items_by_ref: Dict[str, WorkUnit] = dataclasses.field(default_factory=dict)
    items: List[WorkUnit] = dataclasses.field(default_factory=list)

    def _add_item(
        self,
        api_item: Union[ProjectIssue, ProjectMergeRequest],
    ) -> Optional[WorkUnit]:
        short_ref = api_item.references["short"]
        if short_ref in self.items_by_ref:
            return
        item = WorkUnit(key_item=api_item)
        self.items.append(item)
        self.items_by_ref[short_ref] = item
        print(short_ref, api_item.title)
        return item

    def add_issue(
        self,
        proj: gitlab.v4.objects.Project,
        issue: ProjectIssue,
        also_add_related_mrs: bool = True,
    ) -> Optional[WorkUnit]:
        item = self._add_item(issue)
        if not item:
            return
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
            self.add_mr_to_workunit(proj, item, mr_num)

    def add_mr_to_workunit(
        self, proj: gitlab.v4.objects.Project, item: WorkUnit, mr_num: int
    ):
        mr = proj.mergerequests.get(mr_num)
        self._add_mr_to_workunit(item, mr)

    def _add_mr_to_workunit(self, item: WorkUnit, mr: ProjectMergeRequest):
        if self._should_add_issue_or_mr_to_workunit(item, mr):
            item.mrs.append(mr)

    def _add_issue_to_workunit(self, item: WorkUnit, issue: ProjectIssue):
        if self._should_add_issue_or_mr_to_workunit(item, issue):
            item.issues.append(issue)

    def _should_add_issue_or_mr_to_workunit(
        self, item: WorkUnit, issue_or_mr: Union[ProjectMergeRequest, ProjectIssue]
    ):
        """Add to items_by_ref and return true if you should finish adding this mr/issue."""
        short_ref = issue_or_mr.references["short"]
        if any(short_ref == ref for ref in item.refs()):
            return False

        self.items_by_ref[short_ref] = item
        print("->", short_ref)
        return True

    def add_mr(
        self, _proj: gitlab.v4.objects.Project, mr: ProjectMergeRequest
    ) -> Optional[WorkUnit]:
        item = self._add_item(mr)
        if not item:
            return
        # TODO combine other stuff?
        return item

    def merge_workunits(self, item: WorkUnit, other: WorkUnit):
        key_mr = other.get_key_item_as_mr()
        if key_mr:
            self._add_mr_to_workunit(item, key_mr)

        key_issue = other.get_key_item_as_issue()
        if key_issue:
            self._add_issue_to_workunit(item, key_issue)

        for issue in other.issues:
            self._add_issue_to_workunit(item, issue)

        for mr in other.mrs:
            self._add_mr_to_workunit(item, mr)
