#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import datetime
import itertools
import logging
import re
from typing import Optional

import gitlab
import gitlab.v4.objects
import kanboard

from openxr_ops.checklists import ReleaseChecklistCollection
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardBoard
from openxr_ops.kb_defaults import USERNAME, get_kb_api_token, get_kb_api_url
from openxr_ops.kb_ops_card import OperationsCardCreationData, OperationsCardFlags
from openxr_ops.kb_ops_collection import CardCollection
from openxr_ops.kb_ops_queue import COLUMN_CONVERSION, COLUMN_TO_SWIMLANE
from openxr_ops.kb_ops_stages import CardCategory, CardSwimlane
from openxr_ops.labels import ColumnName
from openxr_ops.priority_results import ReleaseChecklistIssue
from openxr_ops.vendors import VendorNames

_PROJ_NAME = "test1"

_UNWRAP_RE = re.compile(r"\['(?P<ext>.*)'\]")


async def async_main(
    oxr_gitlab: OpenXRGitlab, gl_collection: ReleaseChecklistCollection
):
    log = logging.getLogger(__name__)
    from pprint import pprint

    kb_board, card_collection = await load_kb_ops()

    # TODO stop limiting
    for issue_ref, mr_num in itertools.islice(gl_collection.issue_to_mr.items(), 0, 50):
        issue_obj = gl_collection.mr_to_issue_object[mr_num]
        kb_card = card_collection.get_card_by_mr(mr_num)
        if kb_card is not None:
            # already created
            assert kb_card.task_dict is not None
            log.info(
                "MR !%d: Card already exists - %s", mr_num, kb_card.task_dict["url"]
            )
            # TODO verify it's fully populated here
            continue

        new_card_id = await create_equiv_card(
            oxr_gitlab, gl_collection, kb_board, mr_num, issue_obj
        )
        if new_card_id is not None:
            log.info("Created new card ID %d", new_card_id)


def get_category(checklist_issue: ReleaseChecklistIssue) -> Optional[CardCategory]:
    """Get KB category from checklist issue."""
    log = logging.getLogger(__name__ + "get_category")

    category = None
    if checklist_issue.is_outside_ipr_framework:
        log.info("Outside IPR policy: %s", checklist_issue.title)
        category = CardCategory.OUTSIDE_IPR_POLICY
    return category


def get_swimlane_and_column(checklist_issue: ReleaseChecklistIssue):
    """Get KB column from checklist issue."""
    old_col = ColumnName.from_labels([checklist_issue.status])
    assert old_col
    converted_column = COLUMN_CONVERSION[old_col]
    swimlane = COLUMN_TO_SWIMLANE[old_col]
    return swimlane, converted_column


def get_started_date(checklist_issue: ReleaseChecklistIssue):
    """Get KB start date from checklist issue."""
    started = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        days=checklist_issue.latency
    )

    return started


def get_title(checklist_issue: ReleaseChecklistIssue) -> str:
    """Get KB title from checklist issue."""
    title = checklist_issue.title
    m = _UNWRAP_RE.match(title)
    if m:
        title = m.group("ext")
    return title


def get_description(issue_obj) -> str:
    """Get initial KB description from ops issue."""
    description = issue_obj.attributes["description"].replace("- [ ]", "- [_]")
    return description


def get_flags(checklist_issue):
    """Get KB tags from checklist issue labels."""
    flags = OperationsCardFlags(
        api_frozen=checklist_issue.unchangeable,
        initial_design_review_complete=checklist_issue.initial_design_review_complete,
        initial_spec_review_complete=checklist_issue.initial_spec_review_complete,
        spec_support_review_comments_pending=False,
    )

    return flags


async def create_equiv_card(
    oxr_gitlab,
    gl_collection,
    kb_board,
    mr_num,
    issue_obj: gitlab.v4.objects.ProjectIssue,
):
    log = logging.getLogger(__name__)
    if issue_obj.attributes["state"] == "closed":
        # skip it
        return
    mr_obj = oxr_gitlab.main_proj.mergerequests.get(mr_num)
    if mr_obj.attributes["state"] in ("closed", "merged"):
        # skip it
        return
    statuses = [
        label for label in issue_obj.attributes["labels"] if label.startswith("status:")
    ]
    if len(statuses) != 1:
        log.warning("Wrong status count on %d", mr_num)
        return
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

    started = get_started_date(checklist_issue)

    data = OperationsCardCreationData(
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
    card_id = await data.create_card(kb_board=kb_board)
    return card_id


async def load_kb_ops():
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

    proj = await kb.get_project_by_name_async(name=_PROJ_NAME)
    if proj == False:
        raise RuntimeError("No project named " + _PROJ_NAME)

    log.debug("Project data: %s", pformat(proj))

    kb_board = KanboardBoard(kb, int(proj["id"]))
    log.info("Getting columns, swimlanes, and categories")
    await asyncio.gather(
        kb_board.fetch_columns(),
        kb_board.fetch_swimlanes(),
        kb_board.fetch_categories(),
    )

    log.info("Loading all active cards")
    card_collection = CardCollection(kb_board)
    await card_collection.load_board()
    return kb_board, card_collection


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
    oxr_gitlab, collection = load_gitlab_ops()
    assert collection

    loop = asyncio.get_event_loop()
    # loop.
    project_id = loop.run_until_complete(async_main(oxr_gitlab, collection))
