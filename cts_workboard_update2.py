#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>
"""This updates a CTS workboard, but starting with the board, rather than GitLab."""

import itertools
import json
import os
from typing import cast
from work_item_and_collection import WorkUnitCollection, get_short_ref
from nullboard_gitlab import ListName, parse_board, update_board

import gitlab
import gitlab.v4.objects
from dotenv import load_dotenv

load_dotenv()


def main(in_filename, out_filename):
    work = WorkUnitCollection()

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )

    proj = gl.projects.get("openxr/openxr")

    print("Reading", in_filename)
    with open(in_filename, "r") as fp:
        existing_board = json.load(fp)

    parse_board(proj, work, existing_board)

    print("Handling GitLab issues")
    for issue in proj.issues.list(
        labels=["Contractor Approved Backlog"], iterator=True
    ):
        proj_issue = cast(gitlab.v4.objects.ProjectIssue, issue)
        ref = get_short_ref(proj_issue)
        print("Issue:", ref)
        refs = [ref]
        refs.extend(
            mr["references"]["short"] for mr in proj_issue.related_merge_requests()
        )
        print(refs)
        work.add_refs(proj, refs)
        # work.add_issue(proj, )

    for mr in itertools.chain(
        *[
            proj.mergerequests.list(labels=[label], iterator=True)
            for label in ("Contractor Approved Backlog", "Conformance Implementation")
        ]
    ):
        proj_mr = cast(gitlab.v4.objects.ProjectMergeRequest, mr)
        ref = get_short_ref(proj_mr)
        print("MR:", ref)
        work.add_refs(proj, [ref])
        # work.add_mr(proj, cast(gitlab.v4.objects.ProjectMergeRequest, mr))

    update_board(work, existing_board, list_titles_to_skip_adding_to=[ListName.DONE])

    with open(out_filename, "w", encoding="utf-8") as fp:
        json.dump(existing_board, fp, indent=2)


if __name__ == "__main__":
    main(
        # "/home/ryan/Downloads/Nullboard-1661530413298-OpenXR-CTS.nbx",
        "Nullboard-1661530413298-OpenXR-CTS.nbx",
        "Nullboard-1661530413298-OpenXR-CTS-updated.nbx",
    )
