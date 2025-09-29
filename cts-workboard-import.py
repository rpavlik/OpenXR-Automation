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

import kanboard

from cts_workboard_update2 import WorkboardUpdate
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardBoard
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

    kb_board = KanboardBoard(kb, kb_proj_id)
    await kb_board.fetch_col_titles()

    # updated = wbu.update_board()

    # if updated:
    #     log.info("Board contents have been changed.")
    # else:
    #     log.info("No changes to board, output is the same data as input.")


if __name__ == "__main__":

    loop = asyncio.get_event_loop()

    loop.run_until_complete(
        main(
            "Nullboard-1661530413298-OpenXR-CTS.nbx",
        )
    )
