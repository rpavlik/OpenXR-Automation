#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

import itertools
import json
import os
from typing import cast
from work_item_and_collection import WorkUnitCollection
from nullboard_gitlab import ListName, update_board

import gitlab
import gitlab.v4.objects
from dotenv import load_dotenv

load_dotenv()


def main(in_filename, out_filename):
    collection = WorkUnitCollection()

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )

    proj = gl.projects.get("openxr/openxr")

    print("Handling GitLab issues")
    for issue in proj.issues.list(
        labels=["Contractor Approved Backlog"], iterator=True
    ):
        print("Issue:", issue.references["short"])
        collection.add_issue(proj, cast(gitlab.v4.objects.ProjectIssue, issue))

    for mr in itertools.chain(
        *[
            proj.mergerequests.list(labels=[label], iterator=True)
            for label in ("Contractor Approved Backlog", "Conformance Implementation")
        ]
    ):
        print("MR:", mr.references["short"])
        collection.add_mr(proj, cast(gitlab.v4.objects.ProjectMergeRequest, mr))

    print("Reading", in_filename)
    with open(in_filename, "r") as fp:
        existing_board = json.load(fp)

    update_board(
        collection, existing_board, list_titles_to_skip_adding_to=[ListName.DONE]
    )

    with open(out_filename, "w", encoding="utf-8") as fp:
        json.dump(existing_board, fp, indent=2)


if __name__ == "__main__":
    main(
        # "/home/ryan/Downloads/Nullboard-1661530413298-OpenXR-CTS.nbx",
        "Nullboard-1661530413298-OpenXR-CTS.nbx",
        "Nullboard-1661530413298-OpenXR-CTS-updated.nbx",
    )
