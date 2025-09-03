#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging

from openxr_ops.checklists import ReleaseChecklistCollection
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.labels import ColumnName, OpsProjectLabels
from openxr_ops.vendors import VendorNames

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument("--dump", action="store_true", help="Dump out info")
    parser.add_argument(
        "-l", "--update-labels", action="store_true", help="Update labels on MRs"
    )
    parser.add_argument(
        "-d",
        "--update-descriptions",
        action="store_true",
        help="Update descriptions on MRs",
    )
    parser.add_argument(
        "--mr-needs-review",
        type=int,
        nargs="*",
        help="Update the ticket corresponding to the MR to NeedsReview",
    )
    parser.add_argument(
        "--mr-needs-revision",
        type=int,
        nargs="*",
        help="Update the ticket corresponding to the MR to NeedsRevision",
    )
    parser.add_argument(
        "--mr-awaiting-merge",
        type=int,
        nargs="*",
        help="Update the ticket corresponding to the MR to AwaitingMerge",
    )
    parser.add_argument(
        "--mr-needs-champion",
        type=int,
        nargs="*",
        help="Update the ticket corresponding to the MR to NeedsChampionApprovalOrRatification",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()
    log.info("Performing startup queries")
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

    if args.update_labels:
        collection.update_mr_labels()
    if args.update_descriptions:
        collection.update_mr_descriptions()
    if args.mr_needs_review:
        for mr in args.mr_needs_review:
            collection.mr_set_column(mr, ColumnName.AWAITING_SPEC_REVIEW)
    if args.mr_needs_revision:
        for mr in args.mr_needs_revision:
            collection.mr_set_column(
                mr,
                ColumnName.NEEDS_SPEC_REVISION,
                add_labels=[OpsProjectLabels.INITIAL_SPEC_REVIEW_COMPLETE],
                remove_labels=[OpsProjectLabels.CHAMPION_APPROVED],
            )
    if args.mr_needs_champion:
        for mr in args.mr_needs_champion:
            collection.mr_set_column(
                mr, ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION
            )
    if args.mr_awaiting_merge:
        for mr in args.mr_awaiting_merge:
            collection.mr_set_column(mr, ColumnName.AWAITING_MERGE)

    if args.dump:
        for issue_ref, mr in collection.issue_to_mr.items():
            issue_obj = collection.mr_to_issue_object[mr]
            print(
                issue_obj.attributes["title"],
                ",",
                issue_ref,
                ",",
                issue_obj.attributes["state"],
                ",",
                mr,
                issue_obj.attributes["web_url"],
                issue_obj.attributes["labels"],
            )
