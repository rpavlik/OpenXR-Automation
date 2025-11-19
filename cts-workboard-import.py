#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""This updates a CTS workboard, but starting with the board, rather than GitLab."""

import asyncio
import dataclasses
import itertools
import json
import logging
from dataclasses import dataclass
from enum import Enum
from pprint import pformat
from typing import Any, Awaitable, Generator, Iterable, Optional, Union

import kanboard
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from cts_workboard_update2 import WorkboardUpdate
from nullboard_gitlab import extract_refs, extract_refs_from_str
from openxr_ops.gitlab import OpenXRGitlab, ReferenceType
from openxr_ops.kanboard_helpers import KanboardProject, LinkIdMapping
from openxr_ops.kb_cts.collection import TaskCollection
from openxr_ops.kb_cts.stages import TaskColumn, TaskSwimlane
from openxr_ops.kb_cts.task import CTSTask, CTSTaskCreationData, CTSTaskFlags
from openxr_ops.kb_defaults import CTS_PROJ_NAME, connect_and_get_project
from openxr_ops.kb_enums import InternalLinkRelation
from openxr_ops.labels import MainProjectLabels

# List stuff that causes undesired merging here
# Anything on this list will be excluded from the board
DO_NOT_MERGE = {
    "!2887",  # hand tracking permission
    "!3194",  # usage flag errors - merged
    "!3224",  # more
    "!3312",  # use .../click action - merged
    "!3344",  # generate interaction profile spec from xml
    "!3418",  # swapchain format list - merged
    "!3466",  # validate action set names - merged
    "#1460",
    "#1828",
    "#1950",
    "#1978",
    "#2072",  # catch2 test number, etc mismatch
    "#2162",  # unordered success
    "#2220",  # generic controller test
    "#2275",  # vulkan layer
    "#2312",  # subimage y offset with 2 parts
    "#2350",  # xml stuff with 2 parts
    # "#2553",  # Check format returned
    # Release candidates
    "!3053",
    "!3692",
}

# Anything on this list will skip looking for related MRs.
# The contents of DO_NOT_MERGE are also included
FILTER_OUT = DO_NOT_MERGE.union(
    {
        # stuff getting merged into 1.0 v 1.1 that we don't want like that
        "#2245",
        "!3499",
        "!3505",
    }
)

# Must have at least one of these labels to show up on this board
# since there are now two projects using "Contractor:Approved"
REQUIRED_LABEL_SET = set(
    (
        MainProjectLabels.CONFORMANCE_IMPLEMENTATION,
        MainProjectLabels.CONFORMANCE_IN_THE_WILD,
        MainProjectLabels.CONFORMANCE_QUESTION,
    )
)


async def _handle_item(
    wbu: WorkboardUpdate, kb_project: KanboardProject, list_title: str
):
    pass


@dataclass
class UpdateOptions:
    # Changes affecting Kanboard
    create_task: bool = True
    update_title: bool = False
    update_description: bool = False
    update_column_and_swimlane: bool = False
    update_category: bool = False
    update_tags: bool = False
    add_internal_links: bool = True

    # Changes affecting GitLab MRs
    update_mr_desc: bool = False

    def make_dry_run(self):
        self.create_task = False
        self.update_title = False
        self.update_description = False
        self.update_column_and_swimlane = False
        self.update_category = False
        self.update_tags = False
        self.add_internal_links = False

        self.update_mr_desc = False


@dataclass
class NoteData:
    list_title: str
    subhead: Optional[str]
    note_text: str

    @classmethod
    def iterate_notes(cls, board) -> Generator["NoteData", None, None]:
        log = logging.getLogger(f"{__name__}.{cls.__name__}.iterate_notes")
        for notelist in board["lists"]:
            list_title = notelist["title"]
            log.info("In list %s", list_title)
            subhead: Optional[str] = None
            for note in notelist["notes"]:
                if note.get("raw"):
                    subhead = note["text"]
                    continue
                yield NoteData(
                    list_title=list_title,
                    subhead=subhead,
                    note_text=note["text"],
                )


async def _handle_note(
    wbu: WorkboardUpdate,
    kb_project: KanboardProject,
    list_title: str,
    note_dict: dict[str, Any],
):
    log = logging.getLogger(__name__ + "._handle_note")

    refs = extract_refs(note_dict)
    log.debug("Extracted refs: %s", str(refs))
    if not refs:
        # Can't find a reference to an item in the text
        return

    items = wbu.work.get_items_for_refs(refs)
    if not items:
        # Can't find a match for any references
        log.debug("Could not find an entry for '%s'", ",".join(refs))
        return

    top_item = items[0]


NBNote = dict[str, Union[str, bool]]
NBNotes = list[NBNote]


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


class CTSNullboardToKanboard:

    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        # gl_collection: ReleaseChecklistCollection,
        kb_project_name: str,
        # wbu: WorkboardUpdate,
        limit: Optional[int],
        update_options: UpdateOptions,
    ):
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        # self.gl_collection: ReleaseChecklistCollection = gl_collection
        self.kb_project_name: str = kb_project_name
        self.update_options: UpdateOptions = update_options
        # self.wbu: WorkboardUpdate = wbu
        self.limit: Optional[int] = limit

        # self.config = get_config_data()

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # self.mr_to_task_id: dict[int, int] = {}
        # """MR number to kanboard task id"""

        # self.issue_to_task_id: dict[int, int] = {}
        # """issue number to kanboard task id"""

        # self.update_subtask_futures: list = []

        self.gitlab_mrs: dict[int, ProjectMergeRequest] = {}
        self.gitlab_issues: dict[int, ProjectIssue] = {}

        # these are populated later in prepare
        self.kb_project: KanboardProject
        self.task_collection: TaskCollection
        self.kb: kanboard.Client

    def decrement_limit_and_return_true_if_reached(self, count: int = 1):
        if self.limit is None:
            return False
        if self.limit < 0:
            return True

        self.limit -= count

        return self.limit < 0

    # def _find_list_notes(self, title: str) -> NBNotes:
    #     for nb_list in self.wbu.board["lists"]:
    #         if nb_list["title"] == title:  # type: ignore
    #             return nb_list["notes"]  # type: ignore
    #     return []

    def _fetch_gitlab_issue(self, num: int) -> ProjectIssue:
        item = self.gitlab_issues.get(num)
        if item is not None:
            return item

        fetched = self.oxr_gitlab.main_proj.issues.get(num)
        self.gitlab_issues[num] = fetched
        return fetched

    def _fetch_gitlab_mr(self, num: int) -> ProjectMergeRequest:
        item = self.gitlab_mrs.get(num)
        if item is not None:
            return item

        fetched = self.oxr_gitlab.main_proj.mergerequests.get(num)
        self.gitlab_mrs[num] = fetched
        return fetched

    def _fetch_gitlab_ref(
        self, short_ref: str
    ) -> Union[ProjectIssue, ProjectMergeRequest]:
        ref_type, num = ReferenceType.short_reference_to_type_and_num(short_ref)
        if ref_type == ReferenceType.ISSUE:
            return self._fetch_gitlab_issue(num)

        assert ref_type == ReferenceType.MERGE_REQUEST
        return self._fetch_gitlab_mr(num)

    async def _create_task_for_ref(
        self,
        short_ref: str,
        column: TaskColumn,
        swimlane: TaskSwimlane,
        flags: CTSTaskFlags,
    ) -> Optional[int]:
        ref_type, num = ReferenceType.short_reference_to_type_and_num(short_ref)
        gl_item: Union[ProjectIssue, ProjectMergeRequest]
        if ref_type == ReferenceType.ISSUE:
            issue_num = num
            mr_num = None
            gl_item = self.oxr_gitlab.main_proj.issues.get(num)
        else:
            issue_num = None
            mr_num = num
            gl_item = self.oxr_gitlab.main_proj.mergerequests.get(num)

        # TODO
        title = f"{short_ref}: {gl_item.title}"

        data = CTSTaskCreationData(
            mr_num=mr_num,
            issue_num=issue_num,
            column=column,
            swimlane=swimlane,
            title=title,
            description="",
            flags=flags,
        )

        if self.update_options.create_task:
            task_id = await data.create_task(self.kb_project)
            if task_id is None:
                return None
            await self.task_collection.load_task_id(task_id)
            return task_id

        self.log.info("Skipping creating task due to options: %s", pformat(data))
        return None

    def _prefetch_note_deps(
        self,
        note_data: NoteData,
    ):

        refs = extract_refs_from_str(note_data.note_text)
        for ref in refs:
            self._fetch_gitlab_ref(ref)

    async def _process_note(
        self,
        # note_text: str,
        note_data: NoteData,
        # column: TaskColumn,
        # swimlane: TaskSwimlane,
        # flags: CTSTaskFlags,
    ):
        column: TaskColumn = COLUMN_EQUIVALENTS[OldTitles(note_data.list_title)]
        swimlane: TaskSwimlane = TaskSwimlane.GENERAL

        mr_contractor_reviewed = False
        flags = CTSTaskFlags()
        if column in (TaskColumn.BACKLOG, TaskColumn.IN_PROGRESS, TaskColumn.ON_HOLD):
            # these are all approved
            swimlane = TaskSwimlane.CTS_CONTRACTOR
        if note_data.subhead in (
            # "Needs Clarification/Data",
            "Done but Blocked Waiting for Spec Update",
            "Blocked on Spec Issue",
        ):
            flags.blocked_on_spec = True
        if column == TaskColumn.NEEDS_REVIEW:
            if note_data.subhead == "Written by Contractor, more group thumbs needed":
                swimlane = TaskSwimlane.CTS_CONTRACTOR
            elif (
                note_data.subhead == "Reviewed/Tested by Contractor, more thumbs needed"
            ):
                mr_contractor_reviewed = True
        if column == TaskColumn.DONE:
            if note_data.subhead == "Contractor":
                swimlane = TaskSwimlane.CTS_CONTRACTOR
            elif note_data.subhead == "By Others, Contractor Reviewed":
                mr_contractor_reviewed = True

        refs = extract_refs_from_str(note_data.note_text)
        self.log.info("Processing note with refs: %s", ", ".join(refs))

        existing_tasks = {
            ref: self.task_collection.get_task_by_ref(ref) for ref in refs
        }
        # TODO update existing tasks? maybe in separate step?
        missing_parsed_refs: list[tuple[str, ReferenceType, int]] = [
            (ref, *ReferenceType.short_reference_to_type_and_num(ref))
            for ref, task in existing_tasks.items()
            if task is None
        ]

        missing_issues_futures: dict[int, Awaitable[Optional[int]]] = {
            num: self._create_task_for_ref(
                ref,
                column,
                swimlane,
                flags,
            )
            for ref, ref_type, num in missing_parsed_refs
            if ref_type == ReferenceType.ISSUE
        }
        missing_mrs_futures: dict[int, Awaitable[Optional[int]]] = {
            num: self._create_task_for_ref(
                ref,
                column,
                swimlane,
                dataclasses.replace(flags, contractor_reviewed=mr_contractor_reviewed),
            )
            for ref, ref_type, num in missing_parsed_refs
            if ref_type == ReferenceType.MERGE_REQUEST
        }
        for future in missing_issues_futures.values():
            await future

        for future in missing_mrs_futures.values():
            await future

        current_tasks = {ref: self.task_collection.get_task_by_ref(ref) for ref in refs}
        current_valid_tasks = {
            ref: task for ref, task in current_tasks.items() if task is not None
        }
        # Update all link data first
        await asyncio.gather(
            *(
                task.refresh_internal_links(self.kb)
                for task in current_valid_tasks.values()
            )
        )
        current_issue_tasks = [
            task for task in current_valid_tasks.values() if task.is_issue()
        ]
        current_mr_tasks = [
            task for task in current_valid_tasks.values() if task.is_mr()
        ]

        head_task = self.task_collection.get_task_by_ref(refs[0])
        if head_task is None:
            return
        if head_task.is_issue():
            relates_futures = [
                add_link(
                    kb=self.kb,
                    link_mapping=self.kb_project.link_mapping,
                    a=head_task,
                    b=other_issue_task,
                    link_type=InternalLinkRelation.RELATES_TO,
                    dry_run=(not self.update_options.add_internal_links),
                )
                for other_issue_task in current_issue_tasks
                if other_issue_task.task_id != head_task.task_id
            ]

            depends_futures = [
                add_link(
                    kb=self.kb,
                    link_mapping=self.kb_project.link_mapping,
                    a=head_task,
                    b=mr_task,
                    link_type=InternalLinkRelation.IS_BLOCKED_BY,
                    dry_run=(not self.update_options.add_internal_links),
                )
                for mr_task in current_mr_tasks
            ]
            await asyncio.gather(*relates_futures, *depends_futures)
        else:
            # Head task is an MR, so just make them all "relates to" if nothing else
            overall_relates_futures = [
                add_link(
                    kb=self.kb,
                    link_mapping=self.kb_project.link_mapping,
                    a=head_task,
                    b=other_task,
                    link_type=InternalLinkRelation.RELATES_TO,
                    dry_run=(not self.update_options.add_internal_links),
                )
                for other_task in current_valid_tasks.values()
                if other_task.task_id != head_task.task_id
            ]
            await asyncio.gather(*overall_relates_futures)

    # async def _process_list(
    #     self, notes: NBNotes, column: TaskColumn, swimlane: TaskSwimlane
    # ):
    #     futures = []
    #     for note in notes:
    #         if not note.get("raw"):
    #             futures.append(
    #                 self._process_note(
    #                     cast(str, note["text"]),
    #                     # column=column,
    #                     # swimlane=swimlane,
    #                     # flags=CTSTaskFlags(),
    #                 )
    #             )

    #     # TODO parallelize?
    #     for future in futures:
    #         if self.decrement_limit_and_return_true_if_reached():
    #             return
    #         await future

    # async def process_todo(self):
    #     notes = self._find_list_notes(OldTitles.TODO.value)
    #     await self._process_list(
    #         notes, column=TaskColumn.BACKLOG, swimlane=TaskSwimlane.CTS_CONTRACTOR
    #     )

    async def _update_issue(self, task: CTSTask, gl_issue: ProjectIssue):
        pass

    async def _update_mr(self, task: CTSTask, gl_mr: ProjectMergeRequest):
        pass

    async def process(self, board) -> None:
        # First, fetch everything from gitlab if possible. Serially.
        self.log.info("Fetching data on known issues with tasks from GitLab")
        for issue_num in self.task_collection.issue_to_task_id.keys():
            self._fetch_gitlab_issue(issue_num)

        self.log.info("Fetching data on known MRs with tasks from GitLab")
        for mr_num in self.task_collection.mr_to_task_id.keys():
            self._fetch_gitlab_mr(mr_num)

        # Now, update stuff.
        self.log.info("Updating issue tasks")
        issue_update_futures = []
        for issue_num, task_id in self.task_collection.issue_to_task_id.items():
            gl_issue = self._fetch_gitlab_issue(issue_num)
            issue_update_futures.append(
                self._update_issue(self.task_collection.tasks[task_id], gl_issue)
            )
        await asyncio.gather(*issue_update_futures)

        self.log.info("Updating MR tasks")
        mr_update_futures = []
        for mr_num, task_id in self.task_collection.mr_to_task_id.items():
            gl_mr = self._fetch_gitlab_mr(mr_num)
            mr_update_futures.append(
                self._update_mr(self.task_collection.tasks[task_id], gl_mr)
            )
        await asyncio.gather(*mr_update_futures)

        # serially/synchronously in a single thread
        self.log.info("Iterating notes to fetch GitLab refs")
        for note_data in _iterate_notes_with_optional_limit(board, self.limit):
            self._prefetch_note_deps(note_data)

        self.log.info("Iterating notes to process")
        for note_data in _iterate_notes_with_optional_limit(board, self.limit):
            await self._process_note(note_data)

    def _iterate_notes(self, board) -> Iterable[NoteData]:
        note_datas: Iterable[NoteData] = NoteData.iterate_notes(board)
        if self.limit is not None:
            note_datas = itertools.islice(NoteData.iterate_notes(board), self.limit)
        return note_datas

    async def prepare(self):
        self.kb_project, self.task_collection = await load_kb_ops(self.kb_project_name)
        self.kb = self.kb_project.kb


def _iterate_notes_with_optional_limit(
    board, limit: Optional[int] = None
) -> Iterable[NoteData]:
    if limit is not None:
        return itertools.islice(NoteData.iterate_notes(board), limit)
    return NoteData.iterate_notes(board)


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


class OldTitles(Enum):
    TODO = "TODO"
    ON_HOLD = "On Hold"
    CODING = "Coding"
    NEEDS_REVIEW = "Needs Review"
    DONE = "Done"


COLUMN_EQUIVALENTS = {
    OldTitles.TODO: TaskColumn.BACKLOG,
    OldTitles.ON_HOLD: TaskColumn.ON_HOLD,
    OldTitles.CODING: TaskColumn.IN_PROGRESS,
    OldTitles.NEEDS_REVIEW: TaskColumn.NEEDS_REVIEW,
    OldTitles.DONE: TaskColumn.DONE,
}


async def main(
    project_name: str,
    limit: Optional[int],
    dry_run: bool,
    in_filename: str,
):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()

    update_options = UpdateOptions()
    if dry_run:
        update_options.make_dry_run()

    # wbu = WorkboardUpdate(oxr_gitlab)
    # wbu.load_board(in_filename)

    obj = CTSNullboardToKanboard(
        oxr_gitlab=oxr_gitlab,
        kb_project_name=project_name,
        # wbu=wbu,
        limit=limit,
        update_options=update_options,
    )

    with open(in_filename, "r") as fp:
        nb_board = json.load(fp)

    await obj.prepare()
    await obj.process(nb_board)

    # kb_project, task_collection = await load_kb_ops(project_name, only_open=False)
    # kb_proj = await kb_proj_future
    # print(kb_proj["url"]["board"])
    # kb_proj_id = kb_proj["id"]

    # kb_project = KanboardProject(kb, kb_proj_id)
    # await kb_project.fetch_columns()

    # Create all the columns
    # await asyncio.gather(
    #     *[
    #         kb_project.get_or_create_column(nb_list_obj["title"])
    #         for nb_list_obj in wbu.board["lists"]
    #     ]
    # )
    # updated = wbu.update_board()

    # if updated:
    #     log.info("Board contents have been changed.")
    # else:
    #     log.info("No changes to board, output is the same data as input.")


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv

    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_help = True
    parser.add_argument(
        "--project",
        type=str,
        help="Migrate to the named project",
        default=CTS_PROJ_NAME,
        required=True,
    )

    parser.add_argument(
        "--filename",
        type=str,
        help="Nullboard export filename",
        # required=True,
        default="Nullboard-1661530413298-OpenXR-CTS.nbx",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process a limited number of elements",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Do not actually make any changes",
        default=False,
    )
    args = parser.parse_args()

    limit: Optional[int] = None
    if args.limit:
        limit = args.limit
        logging.info("got a limit %s %d", type(args.limit), args.limit)

    asyncio.run(
        main(
            project_name=args.project,
            limit=limit,
            dry_run=args.dry_run,
            in_filename="Nullboard-1661530413298-OpenXR-CTS.nbx",
        )
    )
