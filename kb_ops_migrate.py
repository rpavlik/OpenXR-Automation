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
from typing import Optional, Union

import gitlab
import gitlab.v4.objects
import kanboard

from openxr_ops.checklists import ReleaseChecklistCollection
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardProject
from openxr_ops.kb_defaults import USERNAME, get_kb_api_token, get_kb_api_url
from openxr_ops.kb_ops_collection import TaskCollection
from openxr_ops.kb_ops_queue import COLUMN_CONVERSION, COLUMN_TO_SWIMLANE
from openxr_ops.kb_ops_stages import TaskCategory, TaskSwimlane
from openxr_ops.kb_ops_task import OperationsTaskCreationData, OperationsTaskFlags
from openxr_ops.labels import ColumnName
from openxr_ops.priority_results import ReleaseChecklistIssue
from openxr_ops.vendors import VendorNames

_PROJ_NAME = "test1"

_UNWRAP_RE = re.compile(r"\['(?P<ext>.*)'\]")

_MR_REF_RE = re.compile(
    r"(openxr/openxr!|openxr!|!|https://gitlab.khronos.org/openxr/openxr/-/merge_requests/)(?P<mrnum>[0-9]+)"
)


async def async_main(
    oxr_gitlab: OpenXRGitlab,
    gl_collection: ReleaseChecklistCollection,
    project_name: str,
):
    log = logging.getLogger(__name__)
    from pprint import pprint

    kb_project, task_collection = await load_kb_ops(project_name)

    dates: list[dict[str, Union[str, int]]] = []

    # TODO stop limiting
    for issue_ref, mr_num in itertools.islice(gl_collection.issue_to_mr.items(), 0, 50):
        issue_obj = gl_collection.mr_to_issue_object[mr_num]
        kb_task = task_collection.get_task_by_mr(mr_num)
        if kb_task is not None:
            # already created
            assert kb_task.task_dict is not None
            log.info(
                "MR !%d: Task already exists - %s", mr_num, kb_task.task_dict["url"]
            )
            # TODO verify it's fully populated here
            continue

        new_task_id, task_dates = await create_equiv_task(
            oxr_gitlab, gl_collection, kb_project, mr_num, issue_obj
        )
        if new_task_id is not None:
            log.info("Created new task ID %d", new_task_id)
            if task_dates is not None:
                task_dates["task_id"] = new_task_id
                dates.append(task_dates)

    datestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H.%M.%S")
    fn = f"dates-{datestamp}.csv"
    log.info("Writing dates to %s", fn)
    with open(fn, "w") as fp:
        datafile = csv.DictWriter(fp, ["task_id", "created_on", "started_on", "moved"])
        datafile.writeheader()
        for entry in dates:
            datafile.writerow(entry)


def get_category(checklist_issue: ReleaseChecklistIssue) -> Optional[TaskCategory]:
    """Get KB category from checklist issue."""
    log = logging.getLogger(__name__ + "get_category")

    category = None
    if checklist_issue.is_outside_ipr_framework:
        log.info("Outside IPR policy: %s", checklist_issue.title)
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


def get_flags(checklist_issue):
    """Get KB tags from checklist issue labels."""
    flags = OperationsTaskFlags(
        api_frozen=checklist_issue.unchangeable,
        initial_design_review_complete=checklist_issue.initial_design_review_complete,
        initial_spec_review_complete=checklist_issue.initial_spec_review_complete,
        spec_support_review_comments_pending=False,
    )

    return flags


async def create_equiv_task(
    oxr_gitlab,
    gl_collection,
    kb_project,
    mr_num,
    issue_obj: gitlab.v4.objects.ProjectIssue,
) -> tuple[Optional[int], Optional[dict[str, Union[str, int]]]]:
    """
    Create a KB task for a gitlab ops issue.

    Returns task ID and a dict containing a row for the dates CSV.
    """
    log = logging.getLogger(__name__)
    if issue_obj.attributes["state"] == "closed":
        # skip it
        return None, None
    mr_obj = oxr_gitlab.main_proj.mergerequests.get(mr_num)
    if mr_obj.attributes["state"] in ("closed", "merged"):
        # skip it
        return None, None
    statuses = [
        label for label in issue_obj.attributes["labels"] if label.startswith("status:")
    ]
    if len(statuses) != 1:
        log.warning("Wrong status count on %d", mr_num)
        return None, None
    checklist_issue = ReleaseChecklistIssue.create(
        issue_obj, mr_obj, gl_collection.vendor_names
    )

    swimlane, converted_column = get_swimlane_and_column(checklist_issue)

    category = get_category(checklist_issue)

    flags = get_flags(checklist_issue)

    # clean up description.
    description = get_description(issue_obj)

    # Clean up title
    title = get_title(checklist_issue)

    started = get_latency_date(checklist_issue)

    data = OperationsTaskCreationData(
        main_mr=mr_num,
        column=converted_column,
        swimlane=swimlane,
        title=title,
        description=description,
        flags=flags,
        issue_url=issue_obj.attributes["web_url"],
        category=category,
        date_started=started,
    )
    task_id = await data.create_task(kb_project=kb_project)

    return task_id, get_dates(checklist_issue)


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
    await asyncio.gather(
        kb_project.fetch_columns(),
        kb_project.fetch_swimlanes(),
        kb_project.fetch_categories(),
    )

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

    loop = asyncio.new_event_loop()
    project_id = loop.run_until_complete(
        async_main(oxr_gitlab, collection, args.project[0])
    )
