#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""This updates a CTS workboard, but starting with the board, rather than GitLab."""

import asyncio
import logging
import os
from typing import Any

import kanboard

from cts_workboard_update2 import WorkboardUpdate
from nullboard_gitlab import extract_refs
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardProject
from openxr_ops.labels import MainProjectLabels

_SERVER = "openxr-boards.khronos.org"
_USERNAME = "khronos-bot"
_PROJ_NAME = "CTS Test"

# List stuff that causes undesired merging here
# Anything on this list will be excluded from the board
DO_NOT_MERGE = {
    "!2887",  # hand tracking permission
    "!3194",  # usage flag errors - merged
    "!3224",  # more
    "!3312",  # use .../click action - merged
    "!3344",  # generate interaction profile spec from xml
    "!3418",  # swapchain format list - merged
    "!3466",  # validate action set names - merged
    "#1460",
    "#1828",
    "#1950",
    "#1978",
    "#2072",  # catch2 test number, etc mismatch
    "#2162",  # unordered success
    "#2220",  # generic controller test
    "#2275",  # vulkan layer
    "#2312",  # subimage y offset with 2 parts
    "#2350",  # xml stuff with 2 parts
    # "#2553",  # Check format returned
    # Release candidates
    "!3053",
    "!3692",
}

# Anything on this list will skip looking for related MRs.
# The contents of DO_NOT_MERGE are also included
FILTER_OUT = DO_NOT_MERGE.union(
    {
        # stuff getting merged into 1.0 v 1.1 that we don't want like that
        "#2245",
        "!3499",
        "!3505",
    }
)

# Must have at least one of these labels to show up on this board
# since there are now two projects using "Contractor:Approved"
REQUIRED_LABEL_SET = set(
    (
        MainProjectLabels.CONFORMANCE_IMPLEMENTATION,
        MainProjectLabels.CONFORMANCE_IN_THE_WILD,
        MainProjectLabels.CONFORMANCE_QUESTION,
    )
)


async def _handle_item(
    wbu: WorkboardUpdate, kb_project: KanboardProject, list_title: str
):
    pass


async def _handle_note(
    wbu: WorkboardUpdate,
    kb_project: KanboardProject,
    list_title: str,
    note_dict: dict[str, Any],
):
    log = logging.getLogger(__name__ + "._handle_note")

    refs = extract_refs(note_dict)
    log.debug("Extracted refs: %s", str(refs))
    if not refs:
        # Can't find a reference to an item in the text
        return

    items = wbu.work.get_items_for_refs(refs)
    if not items:
        # Can't find a match for any references
        log.debug("Could not find an entry for '%s'", ",".join(refs))
        return

    top_item = items[0]


async def main(in_filename):
    logging.basicConfig(level=logging.INFO)

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
    kb_proj_future = kb.get_project_by_name_async(name=_PROJ_NAME)

    oxr_gitlab = OpenXRGitlab.create()

    wbu = WorkboardUpdate(oxr_gitlab)
    wbu.load_board(in_filename)

    kb_proj = await kb_proj_future
    print(kb_proj["url"]["board"])
    kb_proj_id = kb_proj["id"]

    kb_project = KanboardProject(kb, kb_proj_id)
    await kb_project.fetch_columns()

    # Create all the columns
    await asyncio.gather(
        *[
            kb_project.get_or_create_column(nb_list_obj["title"])
            for nb_list_obj in wbu.board["lists"]
        ]
    )
    # updated = wbu.update_board()

    # if updated:
    #     log.info("Board contents have been changed.")
    # else:
    #     log.info("No changes to board, output is the same data as input.")


if __name__ == "__main__":

    asyncio.run(
        main(
            "Nullboard-1661530413298-OpenXR-CTS.nbx",
        )
    )
