#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""This updates a CTS Kanboard workboard, from a Nullboard export."""

import asyncio
import dataclasses
import itertools
import json
import logging
from collections.abc import Awaitable, Iterable
from dataclasses import dataclass
from enum import Enum

import kanboard

from nullboard_gitlab import extract_refs_from_str
from openxr_ops.gitlab import OpenXRGitlab, ReferenceType
from openxr_ops.kanboard_helpers import KanboardProject
from openxr_ops.kb_cts.collection import TaskCollection
from openxr_ops.kb_cts.stages import TaskColumn, TaskSwimlane
from openxr_ops.kb_cts.task import CTSTask, CTSTaskFlags
from openxr_ops.kb_cts.update import BaseOptions, CTSBoardUpdater, add_link
from openxr_ops.kb_defaults import CTS_PROJ_NAME
from openxr_ops.kb_enums import InternalLinkRelation
from openxr_ops.nullboard import NoteData

SUBHEAD_TO_USER = {
    "Rylie": "rpavlik",
    "Charlton": "safarimonkey",
    "Christoph": "haagch",
    "Simon": "simonz",
}


@dataclass
class UpdateOptions:
    # Changes affecting Kanboard
    create_task: bool = True
    update_title: bool = True
    update_description: bool = False
    update_column_and_swimlane: bool = False
    update_category: bool = True
    update_tags: bool = True
    update_color: bool = True
    update_owner: bool = True
    add_internal_links: bool = True

    # Changes affecting GitLab MRs
    update_mr_desc: bool = False

    def make_dry_run(self):
        self = UpdateOptions(
            create_task=False,
            update_title=False,
            update_description=False,
            update_column_and_swimlane=False,
            update_category=False,
            update_tags=False,
            update_owner=False,
            add_internal_links=False,
            update_mr_desc=False,
        )

    def to_base_options(self) -> BaseOptions:
        return BaseOptions(
            update_title=self.update_title,
            update_category=self.update_category,
            update_tags=self.update_tags,
            update_color=self.update_color,
            update_owner=self.update_owner,
            create_task=self.create_task,
            add_internal_links=self.add_internal_links,
            modify_gitlab_desc=self.update_mr_desc,
        )


class CTSNullboardToKanboard:

    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        kb_project_name: str,
        limit: int | None,
        update_options: UpdateOptions,
    ):
        self.base = CTSBoardUpdater(
            oxr_gitlab, kb_project_name, options=update_options.to_base_options()
        )
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        self.kb_project_name: str = kb_project_name
        self.update_options: UpdateOptions = update_options
        self.limit: int | None = limit

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # these are populated later in prepare
        self.kb_project: KanboardProject
        self.task_collection: TaskCollection
        self.kb: kanboard.Client

    def _prefetch_note_deps(
        self,
        note_data: NoteData,
    ):

        refs = extract_refs_from_str(note_data.note_text)
        for ref in refs:
            self.base.get_or_fetch_gitlab_ref(ref)

    async def _process_note(
        self,
        note_data: NoteData,
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

        missing_parsed_refs: list[tuple[str, ReferenceType, int]] = [
            (ref, *ReferenceType.short_reference_to_type_and_num(ref))
            for ref, task in existing_tasks.items()
            if task is None
        ]

        missing_issues_futures: dict[int, Awaitable[int | None]] = {
            num: self.base.create_task_for_ref(
                ref,
                column,
                swimlane,
                flags,
            )
            for ref, ref_type, num in missing_parsed_refs
            if ref_type == ReferenceType.ISSUE
        }
        missing_mrs_futures: dict[int, Awaitable[int | None]] = {
            num: self.base.create_task_for_ref(
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
            self.log.warning(
                "Head item in note does not have a corresponding task: %s", refs[0]
            )
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

        if column == TaskColumn.IN_PROGRESS and note_data.subhead is not None:
            desired_username: str | None = SUBHEAD_TO_USER.get(note_data.subhead)
            if desired_username is not None:
                await self._update_owner_on_tasks(
                    current_valid_tasks.values(), desired_username
                )

    async def _update_owner_on_tasks(
        self, tasks: Iterable[CTSTask], desired_username: str
    ):
        desired_user_id: int | None = self.kb_project.username_to_id.get(
            desired_username
        )
        if desired_user_id is None:
            return

        await asyncio.gather(
            *(self._update_owner(task, desired_user_id) for task in tasks)
        )

    async def _update_owner(self, task: CTSTask, desired_user_id: int):
        assert task.task_dict
        existing_id = int(task.task_dict.get("owner_id", "0"))
        if existing_id != desired_user_id:
            if not self.update_options.update_owner:
                self.log.info(
                    "Skipping updating owner on '%s' from %d to %d",
                    task.title,
                    existing_id,
                    desired_user_id,
                )
                return

            self.log.info(
                "Updating owner on '%s' from %d to %d",
                task.title,
                existing_id,
                desired_user_id,
            )
            await self.kb.update_task_async(id=task.task_id, owner_id=desired_user_id)

    async def process(self, board) -> None:
        # First, fetch everything from gitlab if possible. Serially.
        self.base.fetch_all_from_gitlab()

        # Now, update stuff.
        await self.base.update_existing_tasks()

        # serially/synchronously in a single thread - prefetch
        self.log.info("Iterating notes to fetch GitLab refs")
        for note_data in _iterate_notes_with_optional_limit(board, self.limit):
            self._prefetch_note_deps(note_data)

        # now handle notes
        self.log.info("Iterating notes to process")

        BATCH_SIZE = 5
        for note_data_batch in itertools.batched(
            _iterate_notes_with_optional_limit(board, self.limit), BATCH_SIZE
        ):
            await asyncio.gather(
                *(self._process_note(note_data) for note_data in note_data_batch)
            )

    def _iterate_notes(self, board) -> Iterable[NoteData]:
        note_datas: Iterable[NoteData] = NoteData.iterate_notes(board)
        if self.limit is not None:
            note_datas = itertools.islice(NoteData.iterate_notes(board), self.limit)
        return note_datas

    async def prepare(self):
        await self.base.prepare()
        self.kb = self.base.kb
        self.kb_project = self.base.kb_project
        self.task_collection = self.base.task_collection


def _iterate_notes_with_optional_limit(
    board, limit: int | None = None
) -> Iterable[NoteData]:
    if limit is not None:
        return itertools.islice(NoteData.iterate_notes(board), limit)
    return NoteData.iterate_notes(board)


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
    limit: int | None,
    dry_run: bool,
    in_filename: str,
):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()

    update_options = UpdateOptions()
    if dry_run:
        update_options.make_dry_run()

    obj = CTSNullboardToKanboard(
        oxr_gitlab=oxr_gitlab,
        kb_project_name=project_name,
        limit=limit,
        update_options=update_options,
    )

    with open(in_filename) as fp:
        nb_board = json.load(fp)

    await obj.prepare()
    await obj.process(nb_board)


if __name__ == "__main__":

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
    )

    parser.add_argument(
        "--filename",
        type=str,
        help="Nullboard export filename",
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

    limit: int | None = None
    if args.limit:
        limit = args.limit
        logging.info("got a limit %s %d", type(args.limit), args.limit)

    asyncio.run(
        main(
            project_name=args.project,
            limit=limit,
            dry_run=args.dry_run,
            in_filename=args.filename,
        )
    )
