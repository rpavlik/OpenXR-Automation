#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

import json
import os
import re
from typing import cast
from work_item_and_collection import WorkUnit, WorkUnitCollection
from nullboard_gitlab import make_empty_board, update_board

import gitlab
import gitlab.v4.objects
from dotenv import load_dotenv

load_dotenv()

_FIND_MR_RE = re.compile(r"Main extension MR:\s*!([0-9]+)")

_SPECEDITOR = "rpavlik"


class ListName:
    INACTIVE = "Inactive"
    WAITING_REVIEW = "Waiting for Spec Editor Review"
    REVIEWING = "Review in Progress"
    WAITING_VENDOR_ACTION = "Waiting for Vendor Action"
    WAITING_VENDOR_APPROVAL = "Waiting for Vendor Merge Approval"
    DONE = "Done"


def guess_list_for_release_checklist(item: WorkUnit) -> str:
    if item.key_item.state in ("merged", "closed"):
        return ListName.DONE
    if item.mrs:
        mr = item.mrs[0]
        # merge request
        if mr.work_in_progress:
            return ListName.WAITING_VENDOR_ACTION
        if mr.assignee and mr.assignee["username"] == _SPECEDITOR:
            return ListName.WAITING_REVIEW
    return ListName.INACTIVE


def make_release_checklist_note_text(item: WorkUnit) -> str:
    return "{}: {} {}\n{}".format(
        item.ref,
        item.title.replace("Release checklist for ", ""),
        item.web_url,
        "\n".join(item.make_mr_url_list()),
    )


def main(in_filename, out_filename):
    collection = WorkUnitCollection()

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )

    proj = gl.projects.get("openxr/openxr")

    print("Handling GitLab issues")
    for issue in proj.issues.list(labels=["Release Checklist"], iterator=True):
        print("Issue:", issue.references["short"])
        item = collection.add_issue(
            proj, cast(gitlab.v4.objects.ProjectIssue, issue), False
        )
        if not item:
            continue
        match_iter = _FIND_MR_RE.finditer(issue.description)
        m = next(match_iter, None)
        if m:
            mr_num = int(m.group(1))
            collection.add_mr_to_workunit(proj, item, mr_num)
            collection.add_related_mrs_to_issue_workunit(proj, item)

    existing_board = make_empty_board("OpenXR-Release-Checklists")
    try:
        print("Reading", in_filename)
        with open(in_filename, "r") as fp:
            existing_board = json.load(fp)
    except:
        print("Read failed, using a blank board")

    update_board(
        collection,
        existing_board,
        note_text_maker=make_release_checklist_note_text,
        list_guesser=guess_list_for_release_checklist,
    )

    with open(out_filename, "w", encoding="utf-8") as fp:
        json.dump(existing_board, fp, indent=4)


if __name__ == "__main__":
    main(
        "Nullboard-1661545038-OpenXR-Release-Checklists.nbx",
        "Nullboard-1661545038-OpenXR-Release-Checklists-updated.nbx",
    )
