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
import datetime
import logging
import re
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from pprint import pformat
from typing import Any, cast

import kanboard
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from ..cts_board_utils import (
    FILTER_OUT,
    REQUIRED_LABEL_SET,
    compute_api_item_state_and_suffix,
)
from ..gitlab import STATES_CLOSED_MERGED, OpenXRGitlab, ReferenceType, get_short_ref
from ..kanboard_helpers import KanboardProject, LinkIdMapping
from ..kb_defaults import CTS_PROJ_NAME, connect_and_get_project
from ..kb_enums import InternalLinkRelation
from ..labels import MainProjectLabels
from .collection import TaskCollection
from .stages import TaskCategory, TaskColumn, TaskSwimlane
from .task import CTSTask, CTSTaskCreationData, CTSTaskFlags


def _title_from_gitlab_item(
    api_item: ProjectIssue | ProjectMergeRequest,
) -> str:

    state, suffix = compute_api_item_state_and_suffix(api_item)
    state_str = " ".join(state)
    short_ref = api_item.references["short"]
    if short_ref[0] == "#":
        kind = "Issue"
    else:
        kind = "MR"

    return f"{kind} {short_ref}: {state_str}{api_item.title}{suffix}"


def _color_id_from_ref_type(ref_type: ReferenceType) -> str:
    if ref_type == ReferenceType.ISSUE:
        return "grey"
    # apparently white is not officially a selectable color?
    return "blue"


def _category_from_labels(labels: set[str]) -> TaskCategory | None:
    if MainProjectLabels.CONTRACTOR_APPROVED in labels:
        return TaskCategory.CONTRACTOR
    return None


def _guess_mr_column(mr: ProjectMergeRequest):
    column = TaskColumn.NEEDS_REVIEW
    if mr.attributes["work_in_progress"]:
        column = TaskColumn.IN_PROGRESS
    if MainProjectLabels.NEEDS_AUTHOR_ACTION in mr.attributes["labels"]:
        column = TaskColumn.IN_PROGRESS
    return column


# If something is assigned to one of these, we just skip updating assignee
_BOT_USERNAMES = {"realitymerger"}

_TASK_BASE_URL = "https://openxr-boards.khronos.org/task/"


_CTS_BOARD_LINK = re.compile(
    rf"CTS Board Tracking Task: {re.escape(_TASK_BASE_URL)}(?P<task_id>[0-9]+)"
)


def _make_cts_board_link(task_id: int):
    return f"CTS Board Tracking Task: {_TASK_BASE_URL}{task_id}"


def update_item_desc(
    item: ProjectIssue | ProjectMergeRequest,
    task: CTSTask,
    *,
    save_changes: bool,
) -> bool:
    log = logging.getLogger(f"{__name__}.update_item_desc")

    new_front = _make_cts_board_link(task.task_id)
    prepend = f"{new_front}\n\n"

    if item.description.strip() == new_front:
        # minimal desc
        return False

    desc: str = item.description
    new_desc: str = desc

    m = _CTS_BOARD_LINK.search(desc)
    if m:
        replaced_desc = prepend + _CTS_BOARD_LINK.sub("", desc, 1).strip()
        if not m.group(0).startswith(new_front):
            log.info(f"{task.gitlab_link_title} description starts with the wrong link")
            new_desc = replaced_desc
    else:
        new_desc = prepend + desc
        log.info("%s needs task link", task.gitlab_link_title)

    if new_desc != desc:
        if save_changes:
            log.info("Saving change to %s", task.gitlab_link_title)
            item.description = new_desc
            item.save()
            return True
        log.info(
            "Would have made changes to %s description but skipping that by request.",
            task.gitlab_link_title,
        )
        log.debug(
            "Updated description would have been:\n%s",
            new_desc,
        )
    return False


async def add_link(
    kb: kanboard.Client,
    link_mapping: LinkIdMapping,
    a: CTSTask,
    b: CTSTask,
    link_type: InternalLinkRelation,
    dry_run: bool = False,
) -> bool:
    # Assumes a and b both have their links populated.
    log = logging.getLogger(f"{__name__}.add_link")
    if a.task_id == b.task_id:
        log.warning(
            "Trying to self-link task ID %d with relation '%s'",
            a.task_id,
            link_type.value,
        )
        return False
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
        return False

    link_type_id = link_type.to_link_id(link_mapping)
    if dry_run:
        log.info(
            "Skipping creation of link '%s' (type ID %d) from %d to %d, due to options",
            link_type.value,
            link_type_id,
            a.task_id,
            b.task_id,
        )
        return False
    await kb.create_task_link_async(
        task_id=a.task_id, opposite_task_id=b.task_id, link_id=link_type_id
    )
    return True


@dataclass
class BaseOptions:
    """Options for CTSBoardUpdater."""

    update_title: bool
    update_category: bool
    update_tags: bool
    update_color: bool
    update_owner: bool
    update_column: bool
    create_task: bool
    add_internal_links: bool

    modify_gitlab_desc: bool

    @classmethod
    def all_true(cls):
        return cls(
            update_title=True,
            update_category=True,
            update_tags=True,
            update_color=True,
            update_owner=True,
            update_column=True,
            create_task=True,
            add_internal_links=True,
            modify_gitlab_desc=True,
        )

    @classmethod
    def all_false(cls):
        return cls(
            update_title=False,
            update_category=False,
            update_tags=False,
            update_color=False,
            update_owner=False,
            update_column=False,
            create_task=False,
            add_internal_links=False,
            modify_gitlab_desc=False,
        )


def _assignee_from_task_and_item(
    task: CTSTask,
    gl_item: ProjectIssue | ProjectMergeRequest,
) -> tuple[str | None, str | None]:
    active_assignees = [
        assignee
        for assignee in gl_item.attributes["assignees"]
        if assignee["state"] == "active"
    ]
    reviewer: str | None = None

    if task.is_mr() and len(gl_item.attributes["reviewers"]) > 0:
        rev = gl_item.attributes["reviewers"][0]
        if rev["state"] == "active":
            reviewer = rev["username"]

    if active_assignees:
        assignee = active_assignees[0]
        # Do not return the reviewer for the common case where somebody
        # assigns an MR to the reviewer.
        if reviewer is None or reviewer != assignee["username"]:
            return assignee["username"], assignee["name"]

    # If this is an MR, assume it is assigned to the author by default,
    # if the assignee is not useful
    if task.is_mr():
        author = gl_item.attributes["author"]
        if author["state"] == "active":
            return author["username"], author["name"]

    return None, None


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

        self.changes_made: bool = False

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
    ) -> ProjectIssue | ProjectMergeRequest:
        ref_type, num = ReferenceType.short_reference_to_type_and_num(short_ref)
        if ref_type == ReferenceType.ISSUE:
            return self.get_or_fetch_gitlab_issue(num)

        assert ref_type == ReferenceType.MERGE_REQUEST
        return self.get_or_fetch_gitlab_mr(num)

    def compute_creation_data_for_item(
        self,
        ref_type: ReferenceType,
        num: int,
        gl_item: ProjectIssue | ProjectMergeRequest,
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
        gl_item: ProjectIssue | ProjectMergeRequest
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
    ) -> int | None:

        if not self.options.create_task:

            self.log.info("Skipping creating task due to options: %s", pformat(data))
            return None
        self.log.debug("Creating task for %s: %s", short_ref, pformat(data))
        task_id = await data.create_task(self.kb_project)
        if task_id is None:
            self.log.error("Failed to create task for %s!", short_ref)
            return None

        self.changes_made = True

        self.log.debug("Task ID for %s: %d", short_ref, task_id)
        await self.task_collection.load_task_id(task_id)
        return task_id

    async def create_task_for_ref(
        self,
        short_ref: str,
        column: TaskColumn,
        swimlane: TaskSwimlane,
        starting_flags: CTSTaskFlags,
    ) -> int | None:
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
        gl_item: ProjectIssue | ProjectMergeRequest,
    ):
        issue_or_mr = "issue"
        if ref_type == ReferenceType.MERGE_REQUEST:
            issue_or_mr = "mr"

        # Title
        new_title = _title_from_gitlab_item(gl_item).strip()
        if new_title == task.title.strip():
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
            self.changes_made = True

        labels = set(gl_item.attributes["labels"])

        # Category
        new_category = _category_from_labels(labels)
        if new_category == task.category:
            self.log.debug(
                "No %s task category update needed for: '%s'", issue_or_mr, task.title
            )
        elif new_category is None and task.category == TaskCategory.NOT_CTS:
            self.log.debug(
                "No %s task category update needed for: '%s' - will not remove the not-cts category.",
                issue_or_mr,
                task.title,
            )
        elif not self.options.update_category:
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
            self.changes_made = True

        # We start with the existing flags, to preserve
        # manually-added blocked_on_spec, contractor_reviewed
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
            self.changes_made = True

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
            self.changes_made = True

        await self._try_update_owner(issue_or_mr, task, gl_item)

        # The only auto-move we do is moving into "DONE" when corresponding item is closed/merged.
        # (if not on hold)
        is_closed_or_merged = gl_item.attributes["state"] in STATES_CLOSED_MERGED
        if is_closed_or_merged and task.column not in (
            TaskColumn.DONE,
            TaskColumn.ON_HOLD,
        ):
            if self.options.update_column:
                self.log.info("Moving %s task to DONE", issue_or_mr)
                column_id = TaskColumn.DONE.to_required_column_id(self.kb_project)
                swimlane_id = task.swimlane.to_required_swimlane_id(self.kb_project)
                await self.kb.move_task_position_async(
                    project_id=self.kb_project.project_id,
                    task_id=task.task_id,
                    column_id=column_id,
                    swimlane_id=swimlane_id,
                    position=1,
                )
                self.changes_made = True
            else:
                self.log.info(
                    "Skipping %s task column update by request: would have moved from '%s' to DONE",
                    issue_or_mr,
                    task.column,
                )

    async def _try_update_owner(
        self,
        issue_or_mr: str,
        task: CTSTask,
        gl_item: ProjectIssue | ProjectMergeRequest,
    ):

        if not task.task_dict:
            return

        if gl_item.attributes["state"] in STATES_CLOSED_MERGED:
            # Don't update old news.
            return

        owner_username = task.get_owner_username(self.kb_project)

        username, name = _assignee_from_task_and_item(task, gl_item)

        if username in _BOT_USERNAMES:
            # Early out, no need to update owner if it's assigned to the marge bot.
            self.log.debug("%s - assigned to bot user %s", task.gitlab_link, username)
            return

        if owner_username == username:
            # Already assigned correctly
            return

        desired_owner_id: int | None = self.kb_project.lookup_user_id_for_username(
            username
        )

        if desired_owner_id is None:
            # Could not be found
            self.log.warning(
                "Could not find Kanboard user ID for user %s (%s) - "
                "probably has not logged in yet",
                username,
                name,
            )
            return

        if not self.options.update_owner:
            self.log.info(
                "Skipping %s (%s) task owner update by request: "
                "would have changed '%s' to '%s' - see %s: %s",
                issue_or_mr,
                task.gitlab_link_title,
                str(owner_username),
                str(username),
                gl_item.attributes["title"],
                task.gitlab_link,
            )
        else:
            self.log.info(
                "Updating %s (%s) task owner : '%s' to '%s'",
                issue_or_mr,
                task.gitlab_link_title,
                str(owner_username),
                str(username),
            )
            await self.kb.update_task_async(id=task.task_id, owner_id=desired_owner_id)
            self.changes_made = True

    async def update_issue(self, task: CTSTask, gl_issue: ProjectIssue):
        await self._update_either(task, ReferenceType.ISSUE, gl_issue)

    async def update_mr(self, task: CTSTask, gl_mr: ProjectMergeRequest):
        await self._update_either(task, ReferenceType.MERGE_REQUEST, gl_mr)

    def _process_gitlab_desc(
        self, task_id: int, gl_item: ProjectIssue | ProjectMergeRequest
    ):
        if gl_item.attributes["state"] in STATES_CLOSED_MERGED:
            # Let bygones be bygones
            return
        did_update = update_item_desc(
            gl_item,
            self.task_collection.tasks[task_id],
            save_changes=self.options.modify_gitlab_desc,
        )
        if did_update:
            self.changes_made = True

    def fetch_all_from_gitlab(self) -> None:
        # First, fetch everything from gitlab if possible. Serially.
        self.log.info("Fetching data on known issues with tasks from GitLab")
        for issue_num in self.task_collection.issue_to_task_id.keys():
            self.get_or_fetch_gitlab_issue(issue_num)

        self.log.info("Fetching data on known MRs with tasks from GitLab")
        for mr_num in self.task_collection.mr_to_task_id.keys():
            self.get_or_fetch_gitlab_mr(mr_num)

    async def update_existing_tasks(self) -> None:
        self.log.info("Updating issue tasks")
        issue_update_futures: list[Awaitable[Any]] = []
        for issue_num, task_id in self.task_collection.issue_to_task_id.items():
            gl_issue = self.get_or_fetch_gitlab_issue(issue_num)
            issue_update_futures.append(
                self.update_issue(self.task_collection.tasks[task_id], gl_issue)
            )
        await asyncio.gather(*issue_update_futures)

        self.log.info("Updating MR tasks")
        mr_update_futures: list[Awaitable[Any]] = []
        for mr_num, task_id in self.task_collection.mr_to_task_id.items():
            gl_mr = self.get_or_fetch_gitlab_mr(mr_num)
            mr_update_futures.append(
                self.update_mr(self.task_collection.tasks[task_id], gl_mr)
            )
        await asyncio.gather(*mr_update_futures)

        self.log.info("Updating issue and MR descriptions on GitLab")
        task_id_and_gl_item_list: list[
            tuple[int, ProjectIssue | ProjectMergeRequest]
        ] = []
        for issue_num, task_id in self.task_collection.issue_to_task_id.items():
            gl_issue = self.get_or_fetch_gitlab_issue(issue_num)
            task_id_and_gl_item_list.append((task_id, gl_issue))

        for mr_num, task_id in self.task_collection.mr_to_task_id.items():
            gl_mr = self.get_or_fetch_gitlab_mr(mr_num)
            task_id_and_gl_item_list.append((task_id, gl_mr))

        # Sort so that we keep the order of recently updated a little tidier.

        def sort_key(
            task_id_and_item: tuple[int, ProjectIssue | ProjectMergeRequest],
        ) -> datetime.datetime:
            _, gl_item = task_id_and_item
            return datetime.datetime.fromisoformat(gl_item.attributes["updated_at"])

        for task_id, gl_item in sorted(task_id_and_gl_item_list, key=sort_key):
            self._process_gitlab_desc(task_id, gl_item)

    async def prepare(self):
        self.kb_project, self.task_collection = await load_kb_cts(self.kb_project_name)
        self.kb = self.kb_project.kb


async def load_kb_cts(project_name: str = CTS_PROJ_NAME, only_open: bool = True):
    log = logging.getLogger(__name__)

    kb, proj = await connect_and_get_project(project_name)

    kb_project = KanboardProject(kb, int(proj["id"]))
    log.info("Getting columns, swimlanes, categories, etc")
    await kb_project.fetch_all_id_maps()

    log.info("Loading KB tasks")
    task_collection = TaskCollection(kb_project)
    await task_collection.load_project(only_open=only_open)
    return kb_project, task_collection


_CONTRACTOR_USERNAMES = {"rpavlik", "safarimonkey", "haagch", "simonz"}


def _guess_mr_swimlane(mr: ProjectMergeRequest):
    if MainProjectLabels.CONTRACTOR_APPROVED in mr.attributes["labels"]:
        return TaskSwimlane.CTS_CONTRACTOR
    if mr.attributes["author"]["username"] in _CONTRACTOR_USERNAMES:
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

    async def process(self, filter_out_refs: set[str]) -> bool:
        # First, fetch everything from gitlab if possible. Serially.
        self.base.fetch_all_from_gitlab()

        # Now, update stuff.
        await self.base.update_existing_tasks()

        new_issue_futures = self.search_issues(filter_out_refs)
        await asyncio.gather(*new_issue_futures)

        new_mr_futures = self.search_mrs(filter_out_refs)
        await asyncio.gather(*new_mr_futures)

        return self.base.changes_made

    def search_issues(self, filter_out_refs: set[str]) -> list[Awaitable[Any | None]]:
        # Grab all "Contractor:Approved" issues that are CTS related

        self.log.info("Looking for relevant GitLab issues")

        futures: list[Awaitable[Any | None]] = []
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

    def search_mrs(self, filter_out_refs: set[str]) -> list[Awaitable[Any | None]]:
        # Grab all "Contractor:Approved" MRs as well as all
        # CTS ones (whether or not written
        # by contractor, as part of maintaining the cts)
        self.log.info("Looking for relevant GitLab merge requests")

        futures: list[Awaitable[Any | None]] = []
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
    ) -> Awaitable[Any] | None:
        """
        Return a future to perform Kanboard operations associated with the MR.

        (Or, return None, if nothing to do.)

        GitLab operations are performed synchronously in this function.
        """

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
    ) -> Awaitable[Any] | None:
        """
        Return a future to perform Kanboard operations associated with the issue.

        This includes adding MRs that are listed as "closing" it.

        (Or, return None, if nothing to do.)

        GitLab operations are performed synchronously in this function.
        """

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

        task = self.task_collection.get_task_by_issue(num)

        create_future: Awaitable[Any] | None = None

        if task is None:

            self.log.info(
                "GitLab Issue Search: %s: %s - needs task",
                ref,
                proj_issue.title,
            )
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

        async def create_and_link(task: CTSTask | None):
            if create_future:
                task_id = await create_future
                if task_id is None:
                    return
                task = self.task_collection.get_task_by_issue(num)
            if task is None:
                return

            # Make or get all appropriate tasks
            related_mr_tasks = await asyncio.gather(*related_mr_futures)

            # Add the links, if applicable.
            add_link_results: Sequence[bool] = await asyncio.gather(
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
            if any(add_link_results):
                self.base.changes_made = True

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
    changes_made = await obj.process(FILTER_OUT)

    if changes_made:
        log.info("Changes made!")
    else:
        log.info("No changes made")


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
