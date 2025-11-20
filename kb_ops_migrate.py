#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import csv
import datetime
import itertools
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pprint import pformat
from typing import Any, Optional, Union

import gitlab
import gitlab.v4.objects
import kanboard

from openxr_ops.checklists import ReleaseChecklistCollection
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardProject
from openxr_ops.kb_defaults import REAL_PROJ_NAME, connect_and_get_project
from openxr_ops.kb_ops_collection import TaskCollection
from openxr_ops.kb_ops_config import (
    ConfigSubtaskEntry,
    ConfigSubtaskGroup,
    get_config_data,
)
from openxr_ops.kb_ops_gitlab import update_mr_desc
from openxr_ops.kb_ops_queue import COLUMN_CONVERSION, COLUMN_TO_SWIMLANE
from openxr_ops.kb_ops_stages import TaskCategory
from openxr_ops.kb_ops_task import (
    OperationsTask,
    OperationsTaskCreationData,
    OperationsTaskFlags,
)
from openxr_ops.labels import ColumnName
from openxr_ops.priority_results import ReleaseChecklistIssue
from openxr_ops.vendors import VendorNames

_PROJ_NAME = "test1"

_UNWRAP_RE = re.compile(r"\['(?P<ext>.*)'\]")

_MR_REF_RE = re.compile(
    r"(openxr/openxr!|openxr!|!|https://gitlab.khronos.org/openxr/openxr/-/merge_requests/)(?P<mrnum>[0-9]+)"
)


@dataclass
class UpdateOptions:
    # Changes affecting Kanboard
    create_task: bool = True
    update_title: bool = True
    update_description: bool = True
    update_column_and_swimlane: bool = True
    update_category: bool = True
    update_tags: bool = True

    # Changes affecting GitLab MRs
    update_mr_desc: bool = True
    mark_old_links_obsolete: bool = False

    def make_dry_run(self):
        self.create_task = False
        self.update_title = False
        self.update_description = False
        self.update_column_and_swimlane = False
        self.update_category = False
        self.update_tags = False

        self.update_mr_desc = False
        self.mark_old_links_obsolete = False


class MigrateChecklistToSubtasks:
    def __init__(
        self,
        kb: kanboard.Client,
        task_id: int,
        existing_subtasks: list[dict[str, Any]],
        description: str,
    ):
        self.kb = kb
        self.task_id = task_id
        self.existing_subtask_titles_and_ids: dict[str, int] = {
            subtask["title"]: subtask["id"] for subtask in existing_subtasks
        }
        self.existing_by_id: dict[int, dict[str, Any]] = {
            int(subtask["id"]): subtask for subtask in existing_subtasks
        }
        self.checkbox_state_and_line: list[tuple[bool, str]] = list(
            _find_checkboxes(description.splitlines())
        )
        self.new_subtask_titles: set[str] = set()
        self.new_subtasks: list[tuple[bool, str]] = []
        self.futures: list = []
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def perform_queued_operations(self):
        if self.futures:
            self.log.info(
                "Performing %d operations on subtasks",
                len(self.futures),
            )
            for subtask_future in self.futures:
                await subtask_future
        self.futures = []

    def queue_for_group(self, group: ConfigSubtaskGroup):

        for entry in group.subtasks:
            self.queue_for_group_entry(group, entry)

    def queue_for_group_entry(
        self, group: ConfigSubtaskGroup, entry: ConfigSubtaskEntry
    ):
        entry_title = entry.get_full_subtask_name(group)
        if entry_title in self.new_subtask_titles:
            # do not dupe within a single pass
            return

        existing_id_full = self.existing_subtask_titles_and_ids.get(entry_title)
        existing_id_for_partial_title = self.existing_subtask_titles_and_ids.get(
            entry.name
        )
        existing_ids: list[int] = [
            x
            for x in [existing_id_for_partial_title, existing_id_full]
            if x is not None
        ]

        if len(existing_ids) > 1 and not group.allow_duplicate_subtasks:
            self.log.debug("Dropping %d subtasks", len(existing_ids) - 1)
            self.futures.extend(
                self.kb.remove_subtask_async(subtask_id=sub_id)
                for sub_id in existing_ids[1:]
            )

        matching_state_and_line = [
            (checkbox_state, line)
            for checkbox_state, line in self.checkbox_state_and_line
            if entry.migration_prefix in line
        ]
        if not matching_state_and_line:
            # no checklist lines matched this entry
            return

        # Take only the first match
        checkbox_state, _ = matching_state_and_line[0]
        new_status = _bool_to_subtask_status(checkbox_state)

        if existing_ids:
            if group.allow_duplicate_subtasks:
                # do not update if we're allowing dupes
                return
            existing_id = existing_ids[0]

            existing = self.existing_by_id[existing_id]

            orig_title = existing["title"].strip()
            orig_status = int(existing["status"])
            if orig_title != entry_title or orig_status != new_status:
                self.log.debug(
                    "Updating subtask:\n%s -- %d\nfrom:\n%s -- %d",
                    entry_title,
                    new_status,
                    orig_title,
                    orig_status,
                )
                self.futures.append(
                    self.kb.update_subtask_async(
                        id=existing_id,
                        task_id=self.task_id,
                        title=entry_title,
                        status=new_status,
                    )
                )

            # Either way, we already have an entry here
            return

        # Make a new subtask
        self.futures.append(
            self.kb.create_subtask_async(
                task_id=self.task_id,
                title=entry_title,
                status=new_status,
            )
        )
        self.new_subtasks.append((checkbox_state, entry_title))
        self.new_subtask_titles.add(entry_title)


class OperationsGitLabToKanboard:

    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        gl_collection: ReleaseChecklistCollection,
        kb_project_name: str,
        update_options: UpdateOptions,
    ):
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        self.gl_collection: ReleaseChecklistCollection = gl_collection
        self.kb_project_name: str = kb_project_name
        self.update_options: UpdateOptions = update_options

        self.config = get_config_data()

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.dates: list[dict[str, str | int]] = []
        """Rows for a CSV file."""

        self.mr_to_task_id: dict[int, int] = {}
        """MR number to kanboard task id"""

        self.update_subtask_futures: list = []

        # these are populated later in prepare
        self.kb_project: KanboardProject
        self.task_collection: TaskCollection
        self.kb: kanboard.Client

    async def prepare(self):
        self.kb_project, self.task_collection = await load_kb_ops(self.kb_project_name)
        self.kb = self.kb_project.kb

    async def _process_subtasks(
        self,
        task_id: int,
        description: str,
        data: OperationsTaskCreationData,
    ):
        existing_subtasks = await self.kb.get_all_subtasks_async(task_id=task_id)
        if existing_subtasks == False:
            raise RuntimeError(f"Failed to get subtasks for task ID {task_id!s}")

        subtask_migration = MigrateChecklistToSubtasks(
            self.kb,
            task_id=task_id,
            existing_subtasks=existing_subtasks,
            description=description,
        )
        for group in self.config.subtask_groups:
            if not _should_apply_subtask_group(group, data):
                continue
            subtask_migration.queue_for_group(group)

        await subtask_migration.perform_queued_operations()

    async def update_task(
        self,
        kb_task: OperationsTask,
        mr_num: int,
        data: OperationsTaskCreationData,
    ):
        # already created
        assert kb_task.task_dict is not None
        self.log.info(
            "MR !%d: Task already exists - %s", mr_num, kb_task.task_dict["url"]
        )

        ## Category
        if kb_task.category != data.category:
            self.log.info(
                "MR !%d: Mismatch in category %s != %s",
                mr_num,
                str(data.category),
                str(kb_task.category),
            )
            if self.update_options.update_category:
                cat_id = TaskCategory.optional_to_category_id(
                    kb_project=self.kb_project, category=data.category
                )
                if cat_id is not None:
                    await self.kb.update_task_async(
                        id=kb_task.task_id, category_id=cat_id
                    )

        ## Title
        if kb_task.title != data.title:
            self.log.info(
                "MR !%d: Mismatch in title %s != %s",
                mr_num,
                str(data.title),
                str(kb_task.title),
            )
            if self.update_options.update_title:
                await self.kb.update_task_async(id=kb_task.task_id, title=data.title)

        ## Description
        if data.description and kb_task.description != data.description:
            self.log.info("MR !%d: Mismatch in description", mr_num)
            if self.update_options.update_description:
                await self.kb.update_task_async(
                    id=kb_task.task_id, description=data.description
                )

        ## Swimlane or Column
        must_move = False
        if kb_task.swimlane != data.swimlane:
            self.log.info(
                "MR !%d: Mismatch in swimlane %s != %s",
                mr_num,
                str(data.swimlane),
                str(kb_task.swimlane),
            )
            must_move = True

        if kb_task.column != data.column:
            self.log.info(
                "MR !%d: Mismatch in column %s != %s",
                mr_num,
                str(data.column),
                str(kb_task.column),
            )
            must_move = True

        if must_move and self.update_options.update_column_and_swimlane:
            column_id = data.column.to_column_id(self.kb_project)
            if column_id is None:
                raise RuntimeError(f"Could not find column ID for {data.column!s}")

            swimlane_id = data.swimlane.to_swimlane_id(self.kb_project)
            if swimlane_id is None:
                raise RuntimeError(f"Could not find swimlane ID for {data.swimlane!s}")
            await self.kb.move_task_position_async(
                project_id=self.kb_project.project_id,
                task_id=kb_task.task_id,
                column_id=column_id,
                swimlane_id=swimlane_id,
                position=1,
            )

        if kb_task.flags != data.flags:
            self.log.info(
                "MR !%d: Mismatch in flags %s != %s",
                mr_num,
                str(data.flags),
                str(kb_task.flags),
            )
            if self.update_options.update_tags:
                tags = []
                if data.flags is not None:
                    tags = data.flags.to_string_list()
                await self.kb.set_task_tags_async(
                    project_id=self.kb_project.project_id,
                    task_id=kb_task.task_id,
                    tags=tags,
                )

    async def process_mr(
        self,
        mr_num: int,
    ):
        """
        Create or update the KB task for a given MR.

        Returns a dict containing a CSV row of timestamps for external application
        if task is newly created.
        """
        issue_obj = self.gl_collection.mr_to_issue_object[mr_num]
        checklist_issue = make_checklist_issue(
            oxr_gitlab=oxr_gitlab,
            gl_collection=self.gl_collection,
            mr_num=mr_num,
            issue_obj=issue_obj,
        )
        if checklist_issue is None:
            return None

        data = populate_data_from_gitlab(
            checklist_issue=checklist_issue,
            mr_num=mr_num,
        )
        if data is None:
            return None

        task_id: int | None = None
        kb_task = self.task_collection.get_task_by_mr(mr_num)

        if kb_task is not None:
            # Existing task
            await self.update_task(
                kb_task=kb_task,
                mr_num=mr_num,
                data=data,
            )
            task_id = kb_task.task_id
        else:
            # New task
            if not self.update_options.create_task:
                self.log.info(
                    "Would create a new task here for %s: %s",
                    checklist_issue.title,
                    pformat(data),
                )
                return None
            new_task_id = await data.create_task(kb_project=self.kb_project)

            if new_task_id is not None:
                self.log.info(
                    "Created new task ID %d: %s",
                    new_task_id,
                    checklist_issue.title,
                )
                task_id = new_task_id

        if task_id is None:
            return None

        self.mr_to_task_id[mr_num] = task_id

        self.update_subtask_futures.append(
            self._process_subtasks(
                task_id,
                checklist_issue.issue_obj.attributes["description"],
                data,
            )
        )

        task_dates = get_dates(checklist_issue)
        if task_dates is not None:
            task_dates["task_id"] = task_id
        return task_dates

    def _update_mr_desc(self, mr_num: int, task_id: int):
        merge_request: gitlab.v4.objects.ProjectMergeRequest = (
            self.gl_collection.proj.mergerequests.get(mr_num)
        )
        update_mr_desc(
            merge_request=merge_request,
            task_id=task_id,
            save_changes=self.update_options.update_mr_desc,
            mark_old_as_obsolete=self.update_options.mark_old_links_obsolete,
        )

    async def process_all_mrs(self, limit: int | None = None):
        collection: Iterable[int] = self.gl_collection.issue_to_mr.values()
        if limit is not None:
            collection = itertools.islice(
                self.gl_collection.issue_to_mr.values(), 0, limit
            )

        for mr_num in collection:
            task_dates = await self.process_mr(
                mr_num=mr_num,
            )

            if task_dates is not None:
                self.dates.append(task_dates)

        # we deferred subtask updating to parallelize better
        # do it now
        await asyncio.gather(*self.update_subtask_futures)
        self.update_subtask_futures = []

        # Now update gitlab, synchronously
        self.log.info("Checking GitLab MR descriptions")
        for mr_num in self.gl_collection.issue_to_mr.values():
            task_id = self.mr_to_task_id.get(mr_num)
            if task_id is None:
                continue

            self._update_mr_desc(mr_num=mr_num, task_id=task_id)

    def write_datetime_csv(self):

        datestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H.%M.%S")
        fn = f"dates-{datestamp}.csv"
        self.log.info("Writing dates to %s", fn)
        with open(fn, "w") as fp:
            datafile = csv.DictWriter(
                fp, ["task_id", "created_on", "started_on", "moved"]
            )
            datafile.writeheader()
            for entry in self.dates:
                datafile.writerow(entry)


async def async_main(
    oxr_gitlab: OpenXRGitlab,
    gl_collection: ReleaseChecklistCollection,
    project_name: str,
    limit: int | None,
    dry_run: bool,
    write_dates: bool,
):
    options = UpdateOptions()
    if options.update_mr_desc:
        # for safety, only update MRs when the project name is the real project.
        options.update_mr_desc = project_name == "OpenXRExtensions"

    if dry_run:
        logging.info("Dry run - no changes will be made!")
        options.make_dry_run()

    obj = OperationsGitLabToKanboard(
        oxr_gitlab=oxr_gitlab,
        gl_collection=gl_collection,
        kb_project_name=project_name,
        update_options=options,
    )
    await obj.prepare()
    await obj.process_all_mrs(limit=limit)
    if obj.dates and write_dates:
        obj.write_datetime_csv()


def _should_apply_subtask_group(
    group: ConfigSubtaskGroup, data: OperationsTaskCreationData
):
    if not group.condition:
        # always apply these for now
        return True

    if not group.condition.test_category(data.category):
        return False

    if group.condition.swimlane and group.condition.swimlane != data.swimlane:
        return False

    return True


def get_category(checklist_issue: ReleaseChecklistIssue) -> TaskCategory | None:
    """Get KB category from checklist issue."""

    category = None
    if checklist_issue.is_outside_ipr_framework:
        category = TaskCategory.OUTSIDE_IPR_POLICY
    return category


def get_swimlane_and_column(checklist_issue: ReleaseChecklistIssue):
    """Get KB column from checklist issue."""
    old_col = ColumnName.from_labels([checklist_issue.status])
    assert old_col
    converted_column = COLUMN_CONVERSION[old_col]
    swimlane = COLUMN_TO_SWIMLANE[old_col]
    return swimlane, converted_column


def get_latency_date(checklist_issue: ReleaseChecklistIssue):
    """Get KB start date from checklist issue."""
    started = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        days=checklist_issue.latency
    )

    return started


_KANBOARD_DATE_FORMAT = "%Y-%m-%d %H:%M"


def get_dates(checklist_issue: ReleaseChecklistIssue) -> dict[str, str | int]:
    latency_date = get_latency_date(checklist_issue)
    issue_created_at = datetime.datetime.fromisoformat(
        checklist_issue.issue_obj.attributes["created_at"]
    )
    mr_created_at = datetime.datetime.fromisoformat(
        checklist_issue.mr.attributes["created_at"]
    )
    created = min(issue_created_at, mr_created_at)
    date_objects = {
        "created_on": created,
        "started_on": mr_created_at,
        "moved": latency_date,
    }
    return {k: v.strftime(_KANBOARD_DATE_FORMAT) for k, v in date_objects.items()}


def get_title(checklist_issue: ReleaseChecklistIssue) -> str:
    """Get KB title from checklist issue."""
    title = checklist_issue.title
    m = _UNWRAP_RE.match(title)
    if m:
        title = m.group("ext")
    return title


_STATUS_AND_DATES_HEADER = "Status and Important Dates, if any"

_CHECKBOX_RE = re.compile(r"- \[(?P<content>[x _])\] .*")

_BLANK_STATUS_SECTION = """
## Status and Important Dates, if any

- [ ] Structural/overall design finalized
  - Last date for structural design change suggestions:
    (_date, or remove this bullet if N/A or already past_)
- [ ] API shape finalized
  - Last date for API shape change suggestions:
    (_date, or remove this bullet if N/A or already past_)
- [ ] API naming finalized
  - Last date for minor API suggestions (function/struct/member naming, etc.):
    (_date, or remove this bullet if N/A or already past_)
- [ ] OK to release when other requirements satisfied
  - Do not release before: (_N/A or date_)
  - Preferred time range for release: (_N/A or date range_)
""".strip()


def _bool_to_subtask_status(checked: bool) -> int:
    if checked:
        return 2
    return 0


def _find_checkboxes(lines: list[str]):
    for line in lines:
        m = _CHECKBOX_RE.match(line)
        if m:
            yield m.group("content") == "x", line


def _line_contains_placeholder(line: str) -> bool:
    # Only for the placeholders in the status/dates section!
    return "(_date, or remove" in line or "(_N/A or" in line


def _format_mr(m: re.Match):
    num = m.group("mrnum")
    match = m.group(0)
    return f"[{match}](https://gitlab.khronos.org/openxr/openxr/-/merge_requests/{num})"


def get_description(issue_obj) -> str:
    """Get initial KB description from ops issue."""
    # Truncate it to the first section.
    full_desc: str = issue_obj.attributes["description"]
    lines: list[str] = full_desc.splitlines()
    keeper_lines: list[str] = []
    header_line_indices: dict[str, int] = {
        line.strip("#").strip(): i
        for i, line in enumerate(lines)
        if line.startswith("##")
    }
    is_line_precondition: list[bool] = ["Preconditions" in line for line in lines]
    first_precondition_line = is_line_precondition.index(True)

    end_line = first_precondition_line
    if _STATUS_AND_DATES_HEADER in header_line_indices:
        # We have a status section
        if _BLANK_STATUS_SECTION in full_desc:
            # but it is unmodified
            end_line = header_line_indices[_STATUS_AND_DATES_HEADER]

    joined = "\n".join(lines[:end_line]).replace("- [ ]", "- [_]")
    # Format some merge request links
    return _MR_REF_RE.sub(_format_mr, joined, count=10)


def get_flags(checklist_issue: ReleaseChecklistIssue):
    """Get KB tags from checklist issue labels."""
    return OperationsTaskFlags(
        api_frozen=checklist_issue.unchangeable,
        initial_design_review_complete=checklist_issue.initial_design_review_complete,
        initial_spec_review_complete=checklist_issue.initial_spec_review_complete,
        spec_support_review_comments_pending=False,
        editor_review_requested=checklist_issue.editor_review_requested,
        khr_extension=checklist_issue.is_khr,
        multivendor_extension=checklist_issue.is_multivendor,
        single_vendor_extension=checklist_issue.is_vendor,
    )


def make_checklist_issue(
    oxr_gitlab,
    gl_collection,
    mr_num,
    issue_obj: gitlab.v4.objects.ProjectIssue,
) -> ReleaseChecklistIssue | None:
    log = logging.getLogger(__name__)
    if issue_obj.attributes["state"] == "closed":
        # skip it
        return None
    mr_obj = oxr_gitlab.main_proj.mergerequests.get(mr_num)
    if mr_obj.attributes["state"] in ("closed", "merged"):
        # skip it
        return None
    statuses = [
        label for label in issue_obj.attributes["labels"] if label.startswith("status:")
    ]
    if len(statuses) != 1:
        log.warning("Wrong status count on %d", mr_num)
        return None
    return ReleaseChecklistIssue.create(issue_obj, mr_obj, gl_collection.vendor_names)


def populate_data_from_gitlab(
    checklist_issue: ReleaseChecklistIssue,
    mr_num,
) -> OperationsTaskCreationData | None:
    """
    Return KB task creation/update data for a gitlab ops issue.
    """

    swimlane, converted_column = get_swimlane_and_column(checklist_issue)

    category = get_category(checklist_issue)

    flags = get_flags(checklist_issue)

    # clean up description.
    description = get_description(checklist_issue.issue_obj)

    # Clean up title
    title = get_title(checklist_issue)

    started = get_latency_date(checklist_issue)

    return OperationsTaskCreationData(
        main_mr=mr_num,
        column=converted_column,
        swimlane=swimlane,
        title=title,
        description=description,
        flags=flags,
        issue_url=checklist_issue.issue_obj.attributes["web_url"],
        category=category,
        date_started=started,
    )


async def load_kb_ops(project_name: str = REAL_PROJ_NAME, only_open: bool = True):
    log = logging.getLogger(__name__)

    kb, proj = await connect_and_get_project(project_name)

    kb_project = KanboardProject(kb, int(proj["id"]))
    log.info("Getting columns, swimlanes, and categories")
    await kb_project.fetch_all_id_maps()

    log.info("Loading KB tasks")
    task_collection = TaskCollection(kb_project)
    await task_collection.load_project(only_open=only_open)
    return kb_project, task_collection


def load_gitlab_ops(for_real: bool = True):
    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()
    if not for_real:
        return oxr_gitlab, None
    log.info("Performing startup GitLab queries")
    collection = ReleaseChecklistCollection(
        oxr_gitlab.main_proj,
        oxr_gitlab.operations_proj,
        checklist_factory=None,
        vendor_names=VendorNames.from_git(oxr_gitlab.main_proj),
    )

    try:
        collection.load_config("ops_issues.toml")
    except OSError:
        print("Could not load config")

    collection.load_initial_data(deep=False)
    return oxr_gitlab, collection


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
        default=_PROJ_NAME,
        required=True,
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
        "-w",
        "--write-dates",
        action="store_true",
        help="Write CSV file containing date/timestamps to update the tasks in the database directly",
        default=False,
    )

    args = parser.parse_args()

    limit: int | None = None
    if args.limit:
        limit = args.limit
        logging.info("got a limit %s %d", type(args.limit), args.limit)

    oxr_gitlab, collection = load_gitlab_ops()
    assert collection

    asyncio.run(
        async_main(
            oxr_gitlab,
            collection,
            args.project,
            limit=limit,
            dry_run=args.dry_run,
            write_dates=args.write_dates,
        )
    )
