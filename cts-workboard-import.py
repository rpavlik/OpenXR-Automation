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
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generator, Iterable, Optional, Union, cast

import kanboard

from cts_workboard_update2 import WorkboardUpdate
from nullboard_gitlab import extract_refs, extract_refs_from_str
from openxr_ops.gitlab import OpenXRGitlab, ReferenceType
from openxr_ops.kanboard_helpers import KanboardProject
from openxr_ops.kb_cts.collection import TaskCollection
from openxr_ops.kb_cts.stages import TaskColumn, TaskSwimlane
from openxr_ops.kb_cts.task import CTSTaskCreationData, CTSTaskFlags
from openxr_ops.kb_defaults import CTS_PROJ_NAME, connect_and_get_project
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


class CTSNullboardToKanboard:

    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        # gl_collection: ReleaseChecklistCollection,
        kb_project_name: str,
        wbu: WorkboardUpdate,
        limit: Optional[int],
        # update_options: UpdateOptions,
    ):
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        # self.gl_collection: ReleaseChecklistCollection = gl_collection
        self.kb_project_name: str = kb_project_name
        # self.update_options: UpdateOptions = update_options
        self.wbu: WorkboardUpdate = wbu
        self.limit: Optional[int] = limit

        # self.config = get_config_data()

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.mr_to_task_id: dict[int, int] = {}
        """MR number to kanboard task id"""

        self.issue_to_task_id: dict[int, int] = {}
        """issue number to kanboard task id"""

        self.update_subtask_futures: list = []

        # these are populated later in prepare
        self.kb_project: KanboardProject
        # self.task_collection: TaskCollection
        self.kb: kanboard.Client

    def decrement_limit_and_return_true_if_reached(self, count: int = 1):
        if self.limit is None:
            return False
        if self.limit < 0:
            return True

        self.limit -= count

        return self.limit < 0

    def _find_list_notes(self, title: str) -> NBNotes:
        for nb_list in self.wbu.board["lists"]:
            if nb_list["title"] == title:  # type: ignore
                return nb_list["notes"]  # type: ignore
        return []

    async def _create_task_for_ref(
        self,
        short_ref: str,
        column: TaskColumn,
        swimlane: TaskSwimlane,
        flags: CTSTaskFlags,
    ):
        ref_type, num = ReferenceType.short_reference_to_type_and_num(short_ref)
        if ref_type == ReferenceType.ISSUE:
            issue_num = num
            mr_num = None
        else:
            issue_num = None
            mr_num = num

        # TODO
        title = short_ref
        data = CTSTaskCreationData(
            mr_num=mr_num,
            issue_num=issue_num,
            column=column,
            swimlane=swimlane,
            title=title,
            description="",
            flags=flags,
        )

        task_id = await data.create_task(self.kb_project)
        if task_id is None:
            return
        await self.task_collection.load_task_id(task_id)
        pass

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

        mr_flags = dataclasses.replace(
            flags, contractor_reviewed=mr_contractor_reviewed
        )

        refs = extract_refs_from_str(note_data.note_text)
        existing_tasks = {
            ref: self.task_collection.get_task_by_ref(ref) for ref in refs
        }

        missing_issues_futures = {
            int(ref[1:]): self._create_task_for_ref(ref, column, swimlane, flags)
            for ref, task in existing_tasks.items()
            if task is None and ref.startswith("#")
        }

        missing_mrs_futures = {
            int(ref[1:]): self._create_task_for_ref(ref, column, swimlane, mr_flags)
            for ref, task in existing_tasks.items()
            if task is None and ref.startswith("!")
        }
        for issue_num, future in missing_issues_futures.items():
            new_task_id = await future

        for mr_num, future in missing_mrs_futures.items():
            new_task_id = await future

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

    async def process(self, board) -> None:
        note_datas: Iterable[NoteData] = NoteData.iterate_notes(board)
        if self.limit is not None:
            note_datas = itertools.islice(NoteData.iterate_notes(board), self.limit)

        for note_data in note_datas:
            await self._process_note(note_data)

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

    wbu = WorkboardUpdate(oxr_gitlab)
    wbu.load_board(in_filename)

    obj = CTSNullboardToKanboard(
        oxr_gitlab=oxr_gitlab,
        kb_project_name=project_name,
        wbu=wbu,
        limit=limit,
    )
    await obj.prepare()
    await obj.process(obj.wbu.board)

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
