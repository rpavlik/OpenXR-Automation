#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

import json
import os
from typing import cast
from work_item_and_collection import WorkUnitCollection
from nullboard_gitlab import make_empty_board, update_board

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
    for issue in proj.issues.list(labels=["Release Checklist"], iterator=True):
        print("Issue:", issue.references["short"])
        collection.add_issue(proj, cast(gitlab.v4.objects.ProjectIssue, issue))

    existing_board = make_empty_board("OpenXR-Release-Checklists")
    try:
        print("Reading", in_filename)
        with open(in_filename, "r") as fp:
            existing_board = json.load(fp)
    except:
        print("Read failed, using a blank board")

    update_board(collection, existing_board)

    with open(out_filename, "w", encoding="utf-8") as fp:
        json.dump(existing_board, fp, indent=2)


if __name__ == "__main__":
    main("Nullboard-1661545038-OpenXR-Release-Checklists.nbx", "Nullboard-1661545038-OpenXR-Release-Checklists-updated.nbx")
