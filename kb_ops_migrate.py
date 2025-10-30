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
from dataclasses import dataclass
from typing import Literal, Optional, Union

import gitlab
import gitlab.v4.objects
import kanboard

from openxr_ops.checklists import ReleaseChecklistCollection
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardProject
from openxr_ops.kb_defaults import USERNAME, get_kb_api_token, get_kb_api_url
from openxr_ops.kb_ops_collection import TaskCollection
from openxr_ops.kb_ops_config import ConfigSubtaskGroup, get_all_subtasks
from openxr_ops.kb_ops_queue import COLUMN_CONVERSION, COLUMN_TO_SWIMLANE
from openxr_ops.kb_ops_stages import TaskCategory, TaskSwimlane
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
    update_title: bool = True
    update_description: bool = True
    update_column_and_swimlane: bool = True
    update_category: bool = True
    update_tags: bool = True


class OperationsGitLabToKanboard:

    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        gl_collection: ReleaseChecklistCollection,
        # kb: kanboard.Client,
        kb_project_name: str,
        update_options: UpdateOptions,
    ):
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        self.gl_collection: ReleaseChecklistCollection = gl_collection
        # self.kb: kanboard.Client = kb
        self.kb_project_name: str = kb_project_name
        self.update_options: UpdateOptions = update_options

        self.subtask_groups = get_all_subtasks()

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.dates: list[dict[str, Union[str, int]]] = []
        """Rows for a CSV file."""

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
            raise RuntimeError("Failed to get subtasks for task ID " + str(task_id))

        existing_subtask_titles = {subtask["title"] for subtask in existing_subtasks}
        checkbox_state_and_line: list[tuple[bool, str]] = list(
            _find_checkboxes(description.splitlines())
        )
        new_subtask_titles: set[str] = set()
        new_subtasks: list[tuple[bool, str]] = []
        new_subtask_futures: list = []
        for group in self.subtask_groups:
            if not _should_apply_subtask_group(group, data):
                continue
            for entry in group.subtasks:
                entry_title = entry.get_full_subtask_name(group)
                if entry_title in new_subtask_titles:
                    # do not dupe within a single pass
                    continue

                if (
                    group.condition
                    and not group.condition.allow_duplicate_subtasks
                    and entry_title in existing_subtask_titles
                ):
                    # But allow some overall dupes
                    # TODO really?
                    continue

                for checkbox_state, line in checkbox_state_and_line:
                    if entry.migration_prefix in line:
                        new_subtask_futures.append(
                            self.kb.create_subtask_async(
                                task_id=task_id,
                                title=entry_title,
                                status=_bool_to_subtask_status(checkbox_state),
                            )
                        )
                        new_subtasks.append((checkbox_state, entry_title))
                        new_subtask_titles.add(entry_title)

        if new_subtask_futures:
            self.log.info(
                "Adding %d new subtasks: %s",
                len(new_subtask_futures),
                str(new_subtask_futures),
            )
            for new_subtask in new_subtask_futures:
                await new_subtask

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
                raise RuntimeError("Could not find column ID for " + str(data.column))

            swimlane_id = data.swimlane.to_swimlane_id(self.kb_project)
            if swimlane_id is None:
                raise RuntimeError(
                    "Could not find swimlane ID for " + str(data.swimlane)
                )
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

        kb_task = self.task_collection.get_task_by_mr(mr_num)

        if kb_task is not None:
            # Already existing.
            await self.update_task(
                kb_task=kb_task,
                mr_num=mr_num,
                data=data,
            )
            await self._process_subtasks(
                kb_task.task_id,
                checklist_issue.issue_obj.attributes["description"],
                data,
            )
            return None

        task_dates = get_dates(checklist_issue)
        new_task_id = await data.create_task(kb_project=self.kb_project)

        if new_task_id is not None:
            self.log.info(
                "Created new task ID %d: %s %s",
                new_task_id,
                checklist_issue.title,
            )

            await self._process_subtasks(
                new_task_id,
                checklist_issue.issue_obj.attributes["description"],
                data,
            )

            if task_dates is not None:
                task_dates["task_id"] = new_task_id
        return task_dates

    async def process_all_mrs(self):
        # TODO stop limiting
        for issue_ref, mr_num in itertools.islice(
            self.gl_collection.issue_to_mr.items(), 0, 50
        ):
            task_dates = await self.process_mr(
                mr_num=mr_num,
            )

            if task_dates is not None:
                self.dates.append(task_dates)

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
):
    obj = OperationsGitLabToKanboard(
        oxr_gitlab=oxr_gitlab,
        gl_collection=gl_collection,
        kb_project_name=project_name,
        update_options=UpdateOptions(),
    )
    await obj.prepare()
    await obj.process_all_mrs()
    if obj.dates:
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


def get_category(checklist_issue: ReleaseChecklistIssue) -> Optional[TaskCategory]:
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


def get_dates(checklist_issue: ReleaseChecklistIssue) -> dict[str, Union[str, int]]:
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


_KEY_DATA_HEADER = "Key Data"
_STATUS_AND_DATES_HEADER = "Status and Important Dates, if any"
_PRECOND_FOR_SPEC_REVIEW_HEADER = "Preconditions for Spec Editor Review"

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
        return 1
    return 0


def _get_checkbox(line: str) -> Optional[bool]:
    m = _CHECKBOX_RE.match(line)
    if m:
        return m.group("content") == "x"
    return None


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
    # headers = [_KEY_DATA_HEADER, _STATUS_AND_DATES_HEADER, _PRECOND_FOR_SPEC_REVIEW_HEADER]
    if _STATUS_AND_DATES_HEADER in header_line_indices:
        # We have a status section
        if _BLANK_STATUS_SECTION in full_desc:
            # but it is unmodified
            end_line = header_line_indices[_STATUS_AND_DATES_HEADER]
        # status_lines = lines[header_line_indices[_STATUS_AND_DATES_HEADER]:first_precondition_line]
        # check_data = [_get_checkbox(line) for line in status_lines]
        # checkboxes = [check for check in check_data if check is not None]
        # has_check = checkboxes and any(checkboxes)
        # placeholder_lines
    # if all(header in header_line_indices for header in headers):
    #     # We can do the smart thing.
    #     status_lines = lines[header_line_indices[]]

    # key_data_index = header_line_indices[]
    # status_index = header_line_indices[]
    # for line in lines:
    #     if "Preconditions" in line:
    #         break
    #     keeper_lines.append(line)
    joined = "\n".join(lines[:end_line]).replace("- [ ]", "- [_]")
    # Format some merge request links
    return _MR_REF_RE.sub(_format_mr, joined, count=10)

    # description = issue_obj.attributes["description"].replace("- [ ]", "- [_]")
    # return description


def get_flags(checklist_issue: ReleaseChecklistIssue):
    """Get KB tags from checklist issue labels."""
    return OperationsTaskFlags(
        api_frozen=checklist_issue.unchangeable,
        initial_design_review_complete=checklist_issue.initial_design_review_complete,
        initial_spec_review_complete=checklist_issue.initial_spec_review_complete,
        spec_support_review_comments_pending=False,
        editor_review_requested=checklist_issue.editor_review_requested,
    )


def make_checklist_issue(
    oxr_gitlab,
    gl_collection,
    mr_num,
    issue_obj: gitlab.v4.objects.ProjectIssue,
) -> Optional[ReleaseChecklistIssue]:
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
) -> Optional[OperationsTaskCreationData]:
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


async def load_kb_ops(project_name: str):
    log = logging.getLogger(__name__)
    token = get_kb_api_token()
    url = get_kb_api_url()
    kb = kanboard.Client(
        url=url,
        username=USERNAME,
        password=token,
        # cafile="/path/to/my/cert.pem",
        ignore_hostname_verification=True,
        insecure=True,
    )
    log.info("Getting project by name")
    from pprint import pformat

    proj = await kb.get_project_by_name_async(name=project_name)
    if proj == False:
        raise RuntimeError("No project named " + project_name)

    log.debug("Project data: %s", pformat(proj))

    kb_project = KanboardProject(kb, int(proj["id"]))
    log.info("Getting columns, swimlanes, and categories")
    await kb_project.fetch_all_id_maps()

    log.info("Loading all active KB tasks")
    task_collection = TaskCollection(kb_project)
    await task_collection.load_project()
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
    except IOError:
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
        nargs=1,
        help="Migrate to the named project",
        default=_PROJ_NAME,
        required=True,
    )

    args = parser.parse_args()
    oxr_gitlab, collection = load_gitlab_ops()
    assert collection

    asyncio.run(async_main(oxr_gitlab, collection, args.project[0]))
