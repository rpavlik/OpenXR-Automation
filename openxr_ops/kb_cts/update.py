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
import itertools
import json
import logging
from dataclasses import dataclass
from enum import Enum
from pprint import pformat
from typing import Awaitable, Generator, Iterable, Optional, Union

import kanboard
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from ..cts_board_utils import compute_api_item_state_and_suffix
from ..gitlab import OpenXRGitlab, ReferenceType
from ..kanboard_helpers import KanboardProject, LinkIdMapping
from ..kb_cts.collection import TaskCollection
from ..kb_cts.stages import TaskColumn, TaskSwimlane
from ..kb_cts.task import CTSTask, CTSTaskCreationData, CTSTaskFlags
from ..kb_defaults import CTS_PROJ_NAME, connect_and_get_project
from ..kb_enums import InternalLinkRelation
from ..labels import MainProjectLabels


def _make_api_item_text(
    api_item: Union[ProjectIssue, ProjectMergeRequest],
) -> str:

    state, suffix = compute_api_item_state_and_suffix(api_item)
    state_str = " ".join(state)

    return "{ref}: {state}{title}{suffix}".format(
        ref=api_item.references["short"],
        state=state_str,
        title=api_item.title,
        suffix=suffix,
    )


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

    update_title: bool = True
    create_task: bool = True


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

    def get_or_fetch_gitlab_mr(self, num: int) -> ProjectMergeRequest:
        item = self.gitlab_mrs.get(num)
        if item is not None:
            # already had it
            return item

        fetched = self.oxr_gitlab.main_proj.mergerequests.get(num)
        self.gitlab_mrs[num] = fetched
        return fetched

    def get_or_fetch_gitlab_ref(
        self, short_ref: str
    ) -> Union[ProjectIssue, ProjectMergeRequest]:
        ref_type, num = ReferenceType.short_reference_to_type_and_num(short_ref)
        if ref_type == ReferenceType.ISSUE:
            return self.get_or_fetch_gitlab_issue(num)

        assert ref_type == ReferenceType.MERGE_REQUEST
        return self.get_or_fetch_gitlab_mr(num)

    async def create_task_for_ref(
        self,
        short_ref: str,
        column: TaskColumn,
        swimlane: TaskSwimlane,
        starting_flags: CTSTaskFlags,
    ) -> Optional[int]:
        ref_type, num = ReferenceType.short_reference_to_type_and_num(short_ref)
        custom_flags = dataclasses.replace(starting_flags)
        gl_item: Union[ProjectIssue, ProjectMergeRequest]
        if ref_type == ReferenceType.ISSUE:
            issue_num = num
            mr_num = None
            gl_item = self.oxr_gitlab.main_proj.issues.get(num)
        else:
            issue_num = None
            mr_num = num
            gl_item = self.oxr_gitlab.main_proj.mergerequests.get(num)

        # TODO customize custom_flags based on the gitlab item

        title = _make_api_item_text(gl_item)

        data = CTSTaskCreationData(
            mr_num=mr_num,
            issue_num=issue_num,
            column=column,
            swimlane=swimlane,
            title=title,
            description="",
            flags=custom_flags,
        )

        if self.options.create_task:
            task_id = await data.create_task(self.kb_project)
            if task_id is None:
                return None
            await self.task_collection.load_task_id(task_id)
            return task_id

        self.log.info("Skipping creating task due to options: %s", pformat(data))
        return None

    async def update_issue(self, task: CTSTask, gl_issue: ProjectIssue):
        new_title = _make_api_item_text(gl_issue)
        if new_title == task.title:
            # no new title needed
            self.log.debug("No issue task title update needed for: '%s'", task.title)
            return

        if not self.options.update_title:
            self.log.info(
                "Skipping issue task title update by request: would have changed '%s' to '%s'",
                task.title,
                new_title,
            )
            return
        self.log.info(
            "Updating issue task title: '%s' to '%s'",
            task.title,
            new_title,
        )
        await self.kb.update_task_async(id=task.task_id, title=new_title)

    async def update_mr(self, task: CTSTask, gl_mr: ProjectMergeRequest):
        new_title = _make_api_item_text(gl_mr)
        if new_title == task.title:
            # no new title needed
            self.log.debug("No MR task title update needed for: '%s'", task.title)
            return
        if not self.options.update_title:
            self.log.info(
                "Skipping MR task title update by request: would have changed '%s' to '%s'",
                task.title,
                new_title,
            )
            return
        self.log.info(
            "Updating MR task title: '%s' to '%s'",
            task.title,
            new_title,
        )
        await self.kb.update_task_async(id=task.task_id, title=new_title)

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
