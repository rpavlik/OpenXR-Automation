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
from typing import Any, Awaitable, Optional, Union, cast

import kanboard
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from ..cts_board_utils import (
    FILTER_OUT,
    REQUIRED_LABEL_SET,
    compute_api_item_state_and_suffix,
)
from ..gitlab import OpenXRGitlab, ReferenceType, get_short_ref
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


def _guess_mr_column(mr):
    column = TaskColumn.NEEDS_REVIEW
    if mr["work_in_progress"]:
        column = TaskColumn.IN_PROGRESS
    if MainProjectLabels.NEEDS_AUTHOR_ACTION in mr["labels"]:
        column = TaskColumn.IN_PROGRESS
    return column


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
    add_internal_links: bool

    @classmethod
    def all_true(cls):
        return cls(
            update_title=True,
            update_category=True,
            update_tags=True,
            update_color=True,
            create_task=True,
            add_internal_links=True,
        )

    @classmethod
    def all_false(cls):
        return cls(
            update_title=False,
            update_category=False,
            update_tags=False,
            update_color=False,
            create_task=False,
            add_internal_links=False,
        )


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

    def compute_creation_data_for_item(
        self,
        ref_type: ReferenceType,
        num: int,
        gl_item: Union[ProjectIssue, ProjectMergeRequest],
        column: TaskColumn,
        swimlane: TaskSwimlane,
        starting_flags: CTSTaskFlags,
    ) -> CTSTaskCreationData:

        custom_flags = dataclasses.replace(starting_flags)
        if ref_type == ReferenceType.ISSUE:
            issue_num = num
            mr_num = None
        else:
            issue_num = None
            mr_num = num

        labels: set[str] = set(gl_item.attributes["labels"])

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

    async def create_task_from_data(
        self, short_ref: str, data: CTSTaskCreationData
    ) -> Optional[int]:

        if not self.options.create_task:

            self.log.info("Skipping creating task due to options: %s", pformat(data))
            return None
        self.log.debug("Creating task for %s: %s", short_ref, pformat(data))
        task_id = await data.create_task(self.kb_project)
        if task_id is None:
            self.log.error("Failed to create task for %s!", short_ref)
            return None

        self.log.debug("Task ID for %s: %d", short_ref, task_id)
        await self.task_collection.load_task_id(task_id)
        return task_id

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
        return await self.create_task_from_data(short_ref, data)

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


_CONTRACTOR_USERNAMES = {"rpavlik", "safarimonkey", "haagch", "simonz"}


def _guess_mr_swimlane(mr):
    if MainProjectLabels.CONTRACTOR_APPROVED in mr["labels"]:
        return TaskSwimlane.CTS_CONTRACTOR
    if mr["author"]["username"] in _CONTRACTOR_USERNAMES:
        return TaskSwimlane.CTS_CONTRACTOR
    return TaskSwimlane.GENERAL


class CTSBoardSearchUpdater:

    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        kb_project_name: str,
        options: BaseOptions,
    ):
        self.base = CTSBoardUpdater(oxr_gitlab, kb_project_name, options=options)
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        self.kb_project_name: str = kb_project_name

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # these are populated later in prepare
        self.kb_project: KanboardProject
        self.task_collection: TaskCollection
        self.kb: kanboard.Client

    async def prepare(self):
        await self.base.prepare()
        self.kb = self.base.kb
        self.kb_project = self.base.kb_project
        self.task_collection = self.base.task_collection

    async def process(self, filter_out_refs: set[str]) -> None:
        # First, fetch everything from gitlab if possible. Serially.
        self.base.fetch_all_from_gitlab()

        # Now, update stuff.
        await self.base.update_existing_tasks()

        new_issue_futures = self.search_issues(filter_out_refs)

        # we can do the remaining part in parallel.
        await asyncio.gather(*new_issue_futures)

        new_mr_futures = self.search_mrs(filter_out_refs)
        await asyncio.gather(*new_mr_futures)

    def search_issues(
        self, filter_out_refs: set[str]
    ) -> list[Awaitable[Optional[Any]]]:
        # Grab all "Contractor:Approved" issues that are CTS related

        self.log.info("Looking for relevant GitLab issues")

        futures = []
        for issue in self.oxr_gitlab.main_proj.issues.list(
            labels=[
                MainProjectLabels.CONTRACTOR_APPROVED,
                MainProjectLabels.CONFORMANCE_IMPLEMENTATION,
            ],
            state="opened",
            iterator=True,
        ):
            ret = self._handle_approved_issue(
                cast(ProjectIssue, issue), filter_out_refs
            )
            if ret is not None:
                futures.append(ret)

        return futures

    def search_mrs(self, filter_out_refs: set[str]) -> list[Awaitable[Optional[Any]]]:
        # Grab all "Contractor:Approved" MRs as well as all
        # CTS ones (whether or not written
        # by contractor, as part of maintaining the cts)
        self.log.info("Looking for relevant GitLab merge requests")

        futures = []
        for mr in self.oxr_gitlab.main_proj.mergerequests.list(
            labels=[MainProjectLabels.CONFORMANCE_IMPLEMENTATION],
            state="opened",
            iterator=True,
        ):
            proj_mr = cast(ProjectMergeRequest, mr)
            ret = self._handle_cts_mr(proj_mr, filter_out_refs)
            if ret is not None:
                futures.append(ret)
        return futures

    # self.work.add_refs(self.proj, [ref])

    def _handle_cts_mr(
        self, proj_mr: ProjectMergeRequest, filter_out_refs: set[str]
    ) -> Optional[Awaitable[Any]]:

        mr_num = proj_mr.get_id()
        assert isinstance(mr_num, int)
        ref = get_short_ref(proj_mr)
        if ref in filter_out_refs:
            self.log.info(
                "Skipping filtered out MR: %s: %s",
                ref,
                proj_mr.title,
            )
            return None

        if "candidate" in proj_mr.title.casefold():
            self.log.info("Skipping release candidate MR %s: %s", ref, proj_mr.title)
            return None

        task = self.task_collection.get_task_by_mr(mr_num)
        if task is not None:
            self.log.debug(
                "Skipping already handled MR: %s: %s",
                ref,
                proj_mr.title,
            )
            return None

        self.log.info("GitLab MR : %s: %s", ref, proj_mr.title)
        mr_data = self.base.compute_creation_data_for_item(
            ReferenceType.MERGE_REQUEST,
            mr_num,
            proj_mr,
            column=_guess_mr_column(proj_mr),
            swimlane=_guess_mr_swimlane(proj_mr),
            starting_flags=CTSTaskFlags(),
        )
        return self.base.create_task_from_data(ref, mr_data)

    def _handle_approved_issue(
        self, proj_issue: ProjectIssue, filter_out_refs: set[str]
    ) -> Optional[Awaitable[Any]]:

        num = proj_issue.get_id()
        assert isinstance(num, int)
        ref = get_short_ref(proj_issue)
        if ref in filter_out_refs:
            self.log.info(
                "Skipping issue and its related MRs: %s: %s",
                ref,
                proj_issue.title,
            )
            return None

        labels = set(proj_issue.attributes["labels"])
        if not labels.intersection(REQUIRED_LABEL_SET):
            self.log.info(
                "Skipping contractor approved but non-CTS issue: %s: %s  %s",
                ref,
                proj_issue.title,
                proj_issue.attributes["web_url"],
            )
            return None

        self.log.info(
            "GitLab Issue Search: %s: %s",
            ref,
            proj_issue.title,
        )
        task = self.task_collection.get_task_by_issue(num)

        create_future: Optional[Awaitable[Any]] = None

        if task is None:

            data = self.base.compute_creation_data_for_item(
                ReferenceType.ISSUE,
                num,
                proj_issue,
                column=TaskColumn.BACKLOG,
                swimlane=TaskSwimlane.CTS_CONTRACTOR,
                starting_flags=CTSTaskFlags(),
            )
            create_future = self.base.create_task_from_data(ref, data)

        related_mrs = [
            mr
            for mr in proj_issue.closed_by()
            if "candidate" not in mr["title"].casefold()
            and mr["references"]["short"] not in filter_out_refs
        ]

        if not related_mrs:
            # no related stuff
            return create_future

        async def create_or_get_mr_task(mr_num: int, mr):
            task = self.task_collection.get_task_by_mr(mr_num)
            if task is not None:
                return task

            mr_data = self.base.compute_creation_data_for_item(
                ReferenceType.MERGE_REQUEST,
                mr_num,
                mr,
                column=_guess_mr_column(mr),
                swimlane=TaskSwimlane.CTS_CONTRACTOR,
                starting_flags=CTSTaskFlags(),
            )
            self.log.info(
                "Creating task for !%d because of its relationship to %s", mr_num, ref
            )
            await self.base.create_task_from_data(f"!{mr_num}", mr_data)
            return self.task_collection.get_task_by_mr(mr_num)

        related_mr_futures = [
            create_or_get_mr_task(int(mr["iid"]), mr) for mr in related_mrs
        ]

        async def create_and_link(task: Optional[CTSTask]):
            if create_future:
                task_id = await create_future
                if task_id is None:
                    return
                task = self.task_collection.get_task_by_issue(num)
            if task is None:
                return

            related_mr_tasks = await asyncio.gather(*related_mr_futures)
            await asyncio.gather(
                *(
                    add_link(
                        self.kb,
                        self.kb_project.link_mapping,
                        task,
                        mr_task,
                        InternalLinkRelation.IS_BLOCKED_BY,
                        not self.base.options.add_internal_links,
                    )
                    for mr_task in related_mr_tasks
                    if mr_task is not None
                )
            )

        return create_and_link(task)


async def main(
    project_name: str,
    dry_run: bool,
):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()

    options = BaseOptions.all_true()
    if dry_run:
        options = BaseOptions.all_false()

    obj = CTSBoardSearchUpdater(
        oxr_gitlab=oxr_gitlab,
        kb_project_name=project_name,
        options=options,
    )

    await obj.prepare()
    await obj.process(FILTER_OUT)


if __name__ == "__main__":

    from dotenv import load_dotenv

    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_help = True
    parser.add_argument(
        "--project",
        type=str,
        help="Use the named project",
        default=CTS_PROJ_NAME,
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Do not actually make any changes",
        default=False,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Higher log level",
        default=False,
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(
        main(
            project_name=args.project,
            dry_run=args.dry_run,
        )
    )
