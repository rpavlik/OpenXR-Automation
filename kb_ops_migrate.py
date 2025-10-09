#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import logging
import os

import kanboard

from openxr_ops.checklists import ReleaseChecklistCollection
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardBoard
from openxr_ops.kb_ops_card import OperationsCardCreationData, OperationsCardFlags
from openxr_ops.kb_ops_collection import CardCollection
from openxr_ops.kb_ops_queue import COLUMN_CONVERSION
from openxr_ops.kb_ops_stages import CardSwimlane
from openxr_ops.labels import ColumnName, GroupLabels, OpsProjectLabels
from openxr_ops.priority_results import ReleaseChecklistIssue
from openxr_ops.vendors import VendorNames

_SERVER = "openxr-boards.khronos.org"
_USERNAME = "khronos-bot"
_PROJ_NAME = "Operations - More Columns"


async def async_main(
    oxr_gitlab: OpenXRGitlab, gl_collection: ReleaseChecklistCollection
):
    log = logging.getLogger(__name__)
    from pprint import pprint

    kb_board, card_collection = await load_kb_ops()

    pprint(card_collection.cards)

    for issue_ref, mr_num in gl_collection.issue_to_mr.items():
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
        log.info("Created new card ID %d", new_card_id)


async def create_equiv_card(oxr_gitlab, gl_collection, kb_board, mr_num, issue_obj):
    mr_obj = oxr_gitlab.main_proj.mergerequests.get(mr_num)
    checklist_issue = ReleaseChecklistIssue.create(
        issue_obj, mr_obj, gl_collection.vendor_names
    )
    old_col = ColumnName.from_labels([checklist_issue.status])
    assert old_col
    converted_column = COLUMN_CONVERSION[old_col]

    swimlane = CardSwimlane.SUBJECT_TO_IPR_POLICY
    # if GroupLabels.OUTSIDE_IPR_FRAMEWORK in issue_obj.attributes["labels"]:
    if checklist_issue.is_outside_ipr_framework:
        swimlane = CardSwimlane.OUTSIDE_IPR_POLICY

    flags = OperationsCardFlags(
        api_frozen=checklist_issue.unchangeable,
        initial_design_review_complete=checklist_issue.initial_design_review_complete,
        initial_spec_review_complete=checklist_issue.initial_spec_review_complete,
        spec_support_review_comments_pending=False,
    )

    description = issue_obj.attributes["description"].replace("- [ ]", "- [_]")

    data = OperationsCardCreationData(
        main_mr=mr_num,
        column=converted_column,
        swimlane=swimlane,
        title=checklist_issue.title,
        description=description,
        flags=flags,
    )
    card_id = await data.create_card(kb_board=kb_board)
    return card_id


async def load_kb_ops():
    log = logging.getLogger(__name__)
    token = os.environ.get("KANBOARD_API_TOKEN", "")
    kb = kanboard.Client(
        url=f"https://{_SERVER}/jsonrpc.php",
        username=_USERNAME,
        password=token,
        # cafile="/path/to/my/cert.pem",
        ignore_hostname_verification=True,
        insecure=True,
    )
    log.info("Getting project by name")
    from pprint import pformat

    proj = await kb.get_project_by_name_async(name=_PROJ_NAME)

    log.debug("Project data: %s", pformat(proj))

    kb_board = KanboardBoard(kb, int(proj["id"]))
    log.info("Getting column titles and ID")
    await asyncio.gather(kb_board.fetch_col_titles(), kb_board.fetch_swimlanes())

    # oxr_gitlab = OpenXRGitlab.create()

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

    logging.basicConfig(level=logging.DEBUG)
    from dotenv import load_dotenv

    load_dotenv()
    # import argparse

    # parser = argparse.ArgumentParser()

    # parser.add_argument("--dump", action="store_true", help="Dump out info")
    # parser.add_argument(
    #     "-l", "--update-labels", action="store_true", help="Update labels on MRs"
    # )
    # parser.add_argument(
    #     "-d",
    #     "--update-descriptions",
    #     action="store_true",
    #     help="Update descriptions on MRs",
    # )
    # parser.add_argument(
    #     "--mr-needs-review",
    #     type=int,
    #     nargs="*",
    #     help="Update the ticket corresponding to the MR to NeedsReview",
    # )
    # parser.add_argument(
    #     "--mr-needs-revision",
    #     type=int,
    #     nargs="*",
    #     help="Update the ticket corresponding to the MR to NeedsRevision",
    # )
    # parser.add_argument(
    #     "--mr-awaiting-merge",
    #     type=int,
    #     nargs="*",
    #     help="Update the ticket corresponding to the MR to AwaitingMerge",
    # )
    # parser.add_argument(
    #     "--mr-needs-champion",
    #     type=int,
    #     nargs="*",
    #     help="Update the ticket corresponding to the MR to NeedsChampionApprovalOrRatification",
    # )

    # args = parser.parse_args()
    # logging.basicConfig(level=logging.INFO)

    oxr_gitlab, collection = load_gitlab_ops()
    assert collection

    loop = asyncio.get_event_loop()
    # loop.
    project_id = loop.run_until_complete(async_main(oxr_gitlab, collection))

    # oxr_gitlab = OpenXRGitlab.create()
    # log.info("Performing startup queries")
    # collection = ReleaseChecklistCollection(
    #     oxr_gitlab.main_proj,
    #     oxr_gitlab.operations_proj,
    #     checklist_factory=None,
    #     vendor_names=VendorNames.from_git(oxr_gitlab.main_proj),
    # )

    # try:
    #     collection.load_config("ops_issues.toml")
    # except IOError:
    #     print("Could not load config")

    # collection.load_initial_data(deep=False)

    # if args.update_labels:
    #     collection.update_mr_labels()
    # if args.update_descriptions:
    #     collection.update_mr_descriptions()
    # if args.mr_needs_review:
    #     for mr in args.mr_needs_review:
    #         collection.mr_set_column(mr, ColumnName.AWAITING_SPEC_REVIEW)
    # if args.mr_needs_revision:
    #     for mr in args.mr_needs_revision:
    #         collection.mr_set_column(
    #             mr,
    #             ColumnName.NEEDS_SPEC_REVISION,
    #             add_labels=[OpsProjectLabels.INITIAL_SPEC_REVIEW_COMPLETE],
    #             remove_labels=[OpsProjectLabels.CHAMPION_APPROVED],
    #         )
    # if args.mr_needs_champion:
    #     for mr in args.mr_needs_champion:
    #         collection.mr_set_column(
    #             mr, ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION
    #         )
    # if args.mr_awaiting_merge:
    #     for mr in args.mr_awaiting_merge:
    #         collection.mr_set_column(mr, ColumnName.AWAITING_MERGE)

    # if args.dump:
    #     for issue_ref, mr in collection.issue_to_mr.items():
    #         issue_obj = collection.mr_to_issue_object[mr]
    #         print(
    #             issue_obj.attributes["title"],
    #             ",",
    #             issue_ref,
    #             ",",
    #             issue_obj.attributes["state"],
    #             ",",
    #             mr,
    #             issue_obj.attributes["web_url"],
    #             issue_obj.attributes["labels"],
    #         )
