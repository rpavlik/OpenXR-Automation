#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""This updates a CTS workboard, but starting with the board, rather than GitLab."""

import itertools
import json
import logging
from typing import cast

import gitlab
import gitlab.v4.objects

from nullboard_gitlab import ListName, make_note_text, parse_board, update_board
from openxr_ops.gitlab import OpenXRGitlab
from work_item_and_collection import WorkUnitCollection, get_short_ref

# List stuff that causes undesired merging here
SKIP_RELATED_MR_LOOKUP = {
    "#1828",
    "#1978",
    "#1950",
    "#1460",
    "#2072",  # catch2 test number, etc mismatch
    "!3053",  # 1.1 candidate
}

# Must have at least one of these labels to show up on this board
# since there are now two projects using "contractor approved"
REQUIRED_LABEL_SET = set(
    (
        "Conformance Implementation",
        "Conformance IN THE WILD",
        "Conformance Question",
    )
)


def main(in_filename, out_filename):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)
    work = WorkUnitCollection()
    work.do_not_merge = SKIP_RELATED_MR_LOOKUP

    oxr_gitlab = OpenXRGitlab.create()

    proj = oxr_gitlab.main_proj

    log.info("Reading %s", in_filename)
    with open(in_filename, "r", encoding="utf-8") as fp:
        existing_board = json.load(fp)

    log.info("Parsing board loaded from %s", in_filename)
    parse_board(proj, work, existing_board)

    # Grab all "Contractor Approved Backlog" issues.
    log.info("Handling GitLab issues")
    for issue in proj.issues.list(
        labels=["Contractor Approved Backlog"], state="opened", iterator=True
    ):
        proj_issue = cast(gitlab.v4.objects.ProjectIssue, issue)
        ref = get_short_ref(proj_issue)
        issue_labels = set(proj_issue.attributes["labels"])
        if not issue_labels.intersection(REQUIRED_LABEL_SET):
            log.info(
                "Skipping contractor approved but non-CTS issue: %s: %s  %s",
                ref,
                proj_issue.title,
                proj_issue.attributes["web_url"],
            )
            continue

        if ref in SKIP_RELATED_MR_LOOKUP:
            log.info(
                "Skipping GitLab Issue Search for: %s: %s",
                ref,
                proj_issue.title,
            )
            continue
        refs = [ref]
        refs.extend(
            mr["references"]["short"]  # type: ignore
            for mr in proj_issue.related_merge_requests()
        )
        log.info(
            "GitLab Issue Search: %s: %s  (refs: %s)",
            ref,
            proj_issue.title,
            ",".join(refs),
        )
        work.add_refs(proj, refs)

    # Grab all "contractor approved backlog" MRs as well as all
    # "Conformance Implementation" ones (whether or not written
    #  by contractor, as part of maintaining the cts)

    log.info("Handling GitLab MRs")
    for mr in itertools.chain(
        *[
            proj.mergerequests.list(labels=[label], state="opened", iterator=True)
            for label in ("Contractor Approved Backlog", "Conformance Implementation")
        ]
    ):
        proj_mr = cast(gitlab.v4.objects.ProjectMergeRequest, mr)
        ref = get_short_ref(proj_mr)
        if "release candidate" in proj_mr.title.casefold():
            log.info("Skipping release candidate MR %s: %s", ref, proj_mr.title)
            continue
        log.info("GitLab MR Search: %s: %s", ref, proj_mr.title)
        work.add_refs(proj, [ref])

    log.info("Updating board with the latest data")
    updated = update_board(
        work,
        existing_board,
        list_titles_to_skip_adding_to=[ListName.DONE],
        note_text_maker=lambda x: make_note_text(
            x, show_mr_votes=True, show_objection_window=True
        ),
    )

    log.info("Writing output file %s", out_filename)
    with open(out_filename, "w", encoding="utf-8") as fp:
        json.dump(existing_board, fp, indent=4)

    if updated:
        log.info("Board contents have been changed.")
    else:
        log.info("No changes to board, output is the same data as input.")


if __name__ == "__main__":
    main(
        # "/home/ryan/Downloads/Nullboard-1661530413298-OpenXR-CTS.nbx",
        "Nullboard-1661530413298-OpenXR-CTS.nbx",
        "Nullboard-1661530413298-OpenXR-CTS-updated.nbx",
    )
