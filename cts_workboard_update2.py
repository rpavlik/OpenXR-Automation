#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>
"""This updates a CTS workboard, but starting with the board, rather than GitLab."""

import itertools
import json
import logging
import os
from typing import cast

import gitlab
import gitlab.v4.objects
from dotenv import load_dotenv

from nullboard_gitlab import ListName, parse_board, update_board
from work_item_and_collection import WorkUnitCollection, get_short_ref

load_dotenv()


def main(in_filename, out_filename):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)
    work = WorkUnitCollection()

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )

    proj = gl.projects.get("openxr/openxr")

    log.info("Reading %s", in_filename)
    with open(in_filename, "r") as fp:
        existing_board = json.load(fp)

    log.info("Parsing board loaded from %s", in_filename)
    parse_board(proj, work, existing_board)

    log.info("Handling GitLab issues")
    for issue in proj.issues.list(
        labels=["Contractor Approved Backlog"], state="opened", iterator=True
    ):
        proj_issue = cast(gitlab.v4.objects.ProjectIssue, issue)
        ref = get_short_ref(proj_issue)
        refs = [ref]
        refs.extend(
            mr["references"]["short"] for mr in proj_issue.related_merge_requests()  # type: ignore
        )
        log.info(
            "GitLab Issue Search: %s: %s  (refs: %s)",
            ref,
            proj_issue.title,
            ",".join(refs),
        )
        work.add_refs(proj, refs)

    for mr in itertools.chain(
        *[
            proj.mergerequests.list(labels=[label], state="opened", iterator=True)
            for label in ("Contractor Approved Backlog", "Conformance Implementation")
        ]
    ):
        proj_mr = cast(gitlab.v4.objects.ProjectMergeRequest, mr)
        ref = get_short_ref(proj_mr)
        log.info("GitLab MR Search: %s: %s", ref, proj_mr.title)
        work.add_refs(proj, [ref])

    log.info("Updating board with the latest data")
    update_board(work, existing_board, list_titles_to_skip_adding_to=[ListName.DONE])

    log.info("Writing output file %s", out_filename)
    with open(out_filename, "w", encoding="utf-8") as fp:
        json.dump(existing_board, fp, indent=4)


if __name__ == "__main__":
    main(
        # "/home/ryan/Downloads/Nullboard-1661530413298-OpenXR-CTS.nbx",
        "Nullboard-1661530413298-OpenXR-CTS.nbx",
        "Nullboard-1661530413298-OpenXR-CTS-updated.nbx",
    )
