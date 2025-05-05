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
from typing import Union, cast

import gitlab
import gitlab.v4.objects
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from nullboard_gitlab import ListName, parse_board, update_board
from openxr_ops.gitlab import OpenXRGitlab
from work_item_and_collection import WorkUnit, WorkUnitCollection, get_short_ref

# List stuff that causes undesired merging here
# Anything on this list will be excluded from the board
DO_NOT_MERGE = {
    "#1828",
    "#1978",
    "#1950",
    "#1460",
    "#2072",  # catch2 test number, etc mismatch
    "#2350",  # xml stuff with 2 parts
    "#2312",  # subimage y offset with 2 parts
    "!3344",  # generate interaction profile spec from xml
    "!3224",  # more
    "#2162",  # unordered success
    "#2220",  # generic controller test
    "!3466",  # validate action set names - merged
    "!2887",  # hand tracking permission
    # Release candidates
    "!3053",
    "!3692",
}

# Anything on this list will skip looking for related MRs.
# The contents of DO_NOT_MERGE are also included
SKIP_RELATED_MR_LOOKUP = DO_NOT_MERGE.union(
    {
        # stuff getting merged into 1.0 v 1.1 that we don't want like that
        "#2245",
        "!3499",
        "!3505",
    }
)

# Must have at least one of these labels to show up on this board
# since there are now two projects using "contractor approved"
REQUIRED_LABEL_SET = set(
    (
        "Conformance Implementation",
        "Conformance IN THE WILD",
        "Conformance Question",
    )
)


def _make_api_item_text(
    api_item: Union[ProjectIssue, ProjectMergeRequest],
) -> str:
    state = []
    if api_item.state == "closed":
        state.append("(CLOSED)")
    elif api_item.state == "merged":
        state.append("(MERGED)")

    is_mr = hasattr(api_item, "target_branch")

    if is_mr and hasattr(api_item, "upvotes") and api_item.upvotes > 0:
        state.append("👍" * api_item.upvotes)

    if is_mr and hasattr(api_item, "downvotes") and api_item.downvotes > 0:
        state.append("👎" * api_item.downvotes)

    if api_item.attributes.get("has_conflicts"):
        state.append("⚠️")

    if hasattr(api_item, "labels"):
        if "Objection Window" in api_item.labels:
            state.append("⏰")

        if "Needs Author Action" in api_item.labels:
            state.append("🚧")

        if any("fast track" in label.casefold() for label in api_item.labels):
            state.append("⏩")

    if not api_item.attributes.get("blocking_discussions_resolved", True):
        state.append("💬")

    if state:
        # If we have at least one item, add an empty entry for the trailing space
        state.append("")

    state_str = " ".join(state)

    return "[{ref}]({url}): {state}{title}".format(
        ref=api_item.references["short"],
        state=state_str,
        title=api_item.title,
        url=api_item.web_url,
    )


def make_note_text(item: WorkUnit, item_formatter) -> str:
    return "{key_item}\n{rest}".format(
        key_item=item_formatter(
            item.key_item,
        ),
        rest="\n".join(
            "• {}".format(
                item_formatter(
                    api_item,
                )
            )
            for api_item in item.non_key_issues_and_mrs()
        ),
    )


def main(in_filename, out_filename):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)
    work = WorkUnitCollection()
    work.do_not_merge = DO_NOT_MERGE

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

        labels = set(proj_issue.attributes["labels"])
        if not labels.intersection(REQUIRED_LABEL_SET):
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

        labels = set(proj_mr.attributes["labels"])
        if not labels.intersection(REQUIRED_LABEL_SET):
            log.info(
                "Skipping contractor approved but non-CTS MR: %s: %s  %s",
                ref,
                proj_mr.title,
                proj_mr.attributes["web_url"],
            )
            continue

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
        note_text_maker=lambda x: make_note_text(x, _make_api_item_text),
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
