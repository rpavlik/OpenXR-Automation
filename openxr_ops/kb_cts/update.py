#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""This provides utilities to update a CTS workboard."""

import asyncio
import dataclasses
import logging
from dataclasses import dataclass
from pprint import pformat
from typing import Optional, Union

import kanboard
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from ..cts_board_utils import compute_api_item_state_and_suffix
from ..gitlab import OpenXRGitlab, ReferenceType
from ..kanboard_helpers import KanboardProject, LinkIdMapping
from ..kb_defaults import CTS_PROJ_NAME, connect_and_get_project
from ..kb_enums import InternalLinkRelation
from ..labels import MainProjectLabels
from .collection import TaskCollection
from .stages import TaskCategory, TaskColumn, TaskSwimlane
from .task import CTSTask, CTSTaskCreationData, CTSTaskFlags


def _title_from_gitlab_item(
    api_item: Union[ProjectIssue, ProjectMergeRequest],
) -> str:

    state, suffix = compute_api_item_state_and_suffix(api_item)
    state_str = " ".join(state)
    short_ref = api_item.references["short"]
    if short_ref[0] == "#":
        kind = "Issue"
    else:
        kind = "MR"

    return "{kind} {ref}: {state}{title}{suffix}".format(
        kind=kind,
        ref=short_ref,
        state=state_str,
        title=api_item.title,
        suffix=suffix,
    )


def _color_id_from_ref_type(ref_type: ReferenceType) -> str:
    if ref_type == ReferenceType.ISSUE:
        return "grey"
    # apparently white is not officially a selectable color?
    return "blue"


def _category_from_labels(labels: set[str]) -> Optional[TaskCategory]:
    if MainProjectLabels.CONTRACTOR_APPROVED in labels:
        return TaskCategory.CONTRACTOR
    return None


async def add_link(
    kb: kanboard.Client,
    link_mapping: LinkIdMapping,
    a: CTSTask,
    b: CTSTask,
    link_type: InternalLinkRelation,
    dry_run: bool = False,
):
    # Assumes a and b both have their links populated.
    # await asyncio.gather(a.refresh_internal_links(kb), b.refresh_internal_links(kb))
    log = logging.getLogger(f"{__name__}.add_link")
    if a.task_id == b.task_id:
        log.warning(
            "Trying to self-link task ID %d with relation '%s'",
            a.task_id,
            link_type.value,
        )
        return
    matching_links = [
        link_data
        for link_data in a.internal_links_list
        if link_data["task_id"] == b.task_id
    ]
    if matching_links:
        log.info(
            "Found existing link(s) between %d and %d (%s), skipping creation",
            a.task_id,
            b.task_id,
            str([link_data["label"] for link_data in matching_links]),
        )
        return

    link_type_id = link_type.to_link_id(link_mapping)
    if dry_run:
        log.info(
            "Skipping creation of link '%s' (type ID %d) from %d to %d, due to options",
            link_type.value,
            link_type_id,
            a.task_id,
            b.task_id,
        )
        return
    await kb.create_task_link_async(
        task_id=a.task_id, opposite_task_id=b.task_id, link_id=link_type_id
    )


@dataclass
class BaseOptions:
    """Options for CTSBoardUpdater."""

    update_title: bool
    update_category: bool
    update_tags: bool
    update_color: bool
    create_task: bool


class CTSBoardUpdater:
    """Class for handling CTS Kanboard workboard operations."""

    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        kb_project_name: str,
        options: BaseOptions,
    ):
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        self.kb_project_name: str = kb_project_name
        self.options = options

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.gitlab_mrs: dict[int, ProjectMergeRequest] = {}
        self.gitlab_issues: dict[int, ProjectIssue] = {}

        # these are populated later in prepare
        self.kb_project: KanboardProject
        self.task_collection: TaskCollection
        self.kb: kanboard.Client

    def get_or_fetch_gitlab_issue(self, num: int) -> ProjectIssue:
        item = self.gitlab_issues.get(num)
        if item is not None:
            # already had it
            return item

        fetched = self.oxr_gitlab.main_proj.issues.get(num)
        self.gitlab_issues[num] = fetched
        return fetched

    def get_gitlab_issue(self, num: int) -> ProjectIssue:
        return self.gitlab_issues[num]

    def get_or_fetch_gitlab_mr(self, num: int) -> ProjectMergeRequest:
        item = self.gitlab_mrs.get(num)
        if item is not None:
            # already had it
            return item

        fetched = self.oxr_gitlab.main_proj.mergerequests.get(num)
        self.gitlab_mrs[num] = fetched
        return fetched

    def get_gitlab_mr(self, num: int) -> ProjectMergeRequest:
        return self.gitlab_mrs[num]

    def get_or_fetch_gitlab_ref(
        self, short_ref: str
    ) -> Union[ProjectIssue, ProjectMergeRequest]:
        ref_type, num = ReferenceType.short_reference_to_type_and_num(short_ref)
        if ref_type == ReferenceType.ISSUE:
            return self.get_or_fetch_gitlab_issue(num)

        assert ref_type == ReferenceType.MERGE_REQUEST
        return self.get_or_fetch_gitlab_mr(num)

    # def compute_creation_data_for_item(
    #     self,
    #     ref_type: ReferenceType,
    #     num: int,
    #     gl_item: Union[ProjectIssue, ProjectMergeRequest],
    #     column: TaskColumn,
    #     swimlane: TaskSwimlane,
    #     starting_flags: CTSTaskFlags,
    # ) -> CTSTaskCreationData:

    #     custom_flags = dataclasses.replace(starting_flags)
    #     if ref_type == ReferenceType.ISSUE:
    #         issue_num = num
    #         mr_num = None
    #     else:
    #         issue_num = None
    #         mr_num = num

    #     labels: set[str] = set(gl_item.attributes["labels"])

    #     custom_flags.update_from_gitlab_labels(labels)

    #     return CTSTaskCreationData(
    #         mr_num=mr_num,
    #         issue_num=issue_num,
    #         column=column,
    #         swimlane=swimlane,
    #         title=_title_from_gitlab_item(gl_item),
    #         description="",
    #         flags=custom_flags,
    #         category=_category_from_labels(labels),
    #         color_id=_color_id_from_ref_type(ref_type),
    #     )

    def compute_creation_data_for_ref(
        self,
        short_ref: str,
        column: TaskColumn,
        swimlane: TaskSwimlane,
        starting_flags: CTSTaskFlags,
    ) -> CTSTaskCreationData:

        ref_type, num = ReferenceType.short_reference_to_type_and_num(short_ref)
        gl_item: Union[ProjectIssue, ProjectMergeRequest]
        if ref_type == ReferenceType.ISSUE:
            gl_item = self.get_gitlab_issue(num)
            issue_num = num
            mr_num = None
        else:
            gl_item = self.get_gitlab_mr(num)
            issue_num = None
            mr_num = num

        labels: set[str] = set(gl_item.attributes["labels"])

        custom_flags = dataclasses.replace(starting_flags)
        custom_flags.update_from_gitlab_labels(labels)

        return CTSTaskCreationData(
            mr_num=mr_num,
            issue_num=issue_num,
            column=column,
            swimlane=swimlane,
            title=_title_from_gitlab_item(gl_item),
            description="",
            flags=custom_flags,
            category=_category_from_labels(labels),
            color_id=_color_id_from_ref_type(ref_type),
        )

    async def create_task_for_ref(
        self,
        short_ref: str,
        column: TaskColumn,
        swimlane: TaskSwimlane,
        starting_flags: CTSTaskFlags,
    ) -> Optional[int]:
        data = self.compute_creation_data_for_ref(
            short_ref=short_ref,
            column=column,
            swimlane=swimlane,
            starting_flags=starting_flags,
        )

        if self.options.create_task:
            self.log.debug("Creating task for %s: %s", short_ref, pformat(data))
            task_id = await data.create_task(self.kb_project)
            if task_id is None:
                self.log.error("Failed to create task for %s~", short_ref)
                return None
            self.log.debug("Task ID for %s: %d", short_ref, task_id)
            await self.task_collection.load_task_id(task_id)
            return task_id

        self.log.info("Skipping creating task due to options: %s", pformat(data))
        return None

    async def _update_either(
        self,
        task: CTSTask,
        ref_type: ReferenceType,
        gl_item: Union[ProjectIssue, ProjectMergeRequest],
    ):
        issue_or_mr = "issue"
        if ref_type == ReferenceType.MERGE_REQUEST:
            issue_or_mr = "mr"

        # Title
        new_title = _title_from_gitlab_item(gl_item)
        if new_title == task.title:
            self.log.debug(
                "No %s task title update needed for: '%s'", issue_or_mr, task.title
            )
        elif not self.options.update_title:
            self.log.info(
                "Skipping %s task title update by request: would have changed '%s' to '%s'",
                issue_or_mr,
                task.title,
                new_title,
            )
        else:
            self.log.info(
                "Updating %s task title: '%s' to '%s'",
                issue_or_mr,
                task.title,
                new_title,
            )
            await self.kb.update_task_async(id=task.task_id, title=new_title)

        labels = set(gl_item.attributes["labels"])

        # Category
        new_category = _category_from_labels(labels)
        if new_category == task.category:
            self.log.debug(
                "No %s task category update needed for: '%s'", issue_or_mr, task.title
            )
        elif not self.options.update_title:
            self.log.info(
                "Skipping %s task category update by request: would have changed '%s' to '%s'",
                issue_or_mr,
                str(task.category),
                str(new_category),
            )
        else:
            self.log.info(
                "Updating %s task category: '%s' to '%s'",
                issue_or_mr,
                str(task.category),
                str(new_category),
            )
            await self.kb.update_task_async(
                id=task.task_id,
                category_id=TaskCategory.optional_to_category_id(
                    self.kb_project, new_category
                ),
            )

        assert task.flags
        new_flags = dataclasses.replace(task.flags)
        new_flags.update_from_gitlab_labels(labels)

        # tags
        if new_flags == task.flags:
            self.log.debug(
                "No %s task flags update needed for: '%s'", issue_or_mr, task.title
            )
        elif not self.options.update_tags:
            self.log.info(
                "Skipping %s task flags update by request: would have changed '%s' to '%s'",
                issue_or_mr,
                str(task.flags),
                str(new_flags),
            )
        else:
            self.log.info(
                "Updating %s task flags: '%s' to '%s'",
                issue_or_mr,
                str(task.flags),
                str(new_flags),
            )
            await self.kb.update_task_async(
                id=task.task_id, tags=new_flags.to_string_list()
            )

        # Color
        color_id = _color_id_from_ref_type(ref_type)
        if color_id == task.color_id:
            self.log.debug(
                "No %s task color update needed for: '%s'", issue_or_mr, task.title
            )
        elif not self.options.update_color:
            self.log.info(
                "Skipping %s task color update by request: would have changed '%s' to '%s'",
                issue_or_mr,
                task.color_id,
                color_id,
            )
        else:
            self.log.info(
                "Updating %s task color: '%s' to '%s'",
                issue_or_mr,
                task.color_id,
                color_id,
            )
            await self.kb.update_task_async(id=task.task_id, color_id=color_id)

    async def update_issue(self, task: CTSTask, gl_issue: ProjectIssue):
        await self._update_either(task, ReferenceType.ISSUE, gl_issue)

    async def update_mr(self, task: CTSTask, gl_mr: ProjectMergeRequest):
        await self._update_either(task, ReferenceType.MERGE_REQUEST, gl_mr)

    def fetch_all_from_gitlab(self) -> None:
        # First, fetch everything from gitlab if possible. Serially.
        self.log.info("Fetching data on known issues with tasks from GitLab")
        for issue_num in self.task_collection.issue_to_task_id.keys():
            self.get_or_fetch_gitlab_issue(issue_num)

        self.log.info("Fetching data on known MRs with tasks from GitLab")
        for mr_num in self.task_collection.mr_to_task_id.keys():
            self.get_or_fetch_gitlab_mr(mr_num)

    async def update_existing_tasks(self):
        self.log.info("Updating issue tasks")
        issue_update_futures = []
        for issue_num, task_id in self.task_collection.issue_to_task_id.items():
            gl_issue = self.get_or_fetch_gitlab_issue(issue_num)
            issue_update_futures.append(
                self.update_issue(self.task_collection.tasks[task_id], gl_issue)
            )
        await asyncio.gather(*issue_update_futures)

        self.log.info("Updating MR tasks")
        mr_update_futures = []
        for mr_num, task_id in self.task_collection.mr_to_task_id.items():
            gl_mr = self.get_or_fetch_gitlab_mr(mr_num)
            mr_update_futures.append(
                self.update_mr(self.task_collection.tasks[task_id], gl_mr)
            )
        await asyncio.gather(*mr_update_futures)

    async def prepare(self):
        self.kb_project, self.task_collection = await load_kb_ops(self.kb_project_name)
        self.kb = self.kb_project.kb


async def load_kb_ops(project_name: str = CTS_PROJ_NAME, only_open: bool = True):
    log = logging.getLogger(__name__)

    kb, proj = await connect_and_get_project(project_name)

    kb_project = KanboardProject(kb, int(proj["id"]))
    log.info("Getting columns, swimlanes, and categories")
    await kb_project.fetch_all_id_maps()

    log.info("Loading KB tasks")
    task_collection = TaskCollection(kb_project)
    await task_collection.load_project(only_open=only_open)
    return kb_project, task_collection
