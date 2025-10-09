#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import itertools
import logging
import os
import re
from typing import Optional

import gitlab
import gitlab.v4.objects
import kanboard

from .checklists import ReleaseChecklistCollection
from .gitlab import OpenXRGitlab
from .kanboard_helpers import KanboardBoard
from .kb_ops_card import OperationsCardCreationData, OperationsCardFlags
from .kb_ops_collection import CardCollection
from .kb_ops_queue import COLUMN_CONVERSION, COLUMN_TO_SWIMLANE
from .kb_ops_stages import (
    CardCategory,
    CardSwimlane,
    CardColumn,
    COLUMN_DESCRIPTIONS,
    SWIMLANE_DESCRIPTIONS,
)
from .labels import ColumnName
from .priority_results import ReleaseChecklistIssue
from .vendors import VendorNames
from .kb_defaults import SERVER, USERNAME


async def populate_columns(kb_board: KanboardBoard):
    await kb_board.fetch_col_titles()

    kb = kb_board.kb
    project_id = kb_board.project_id
    await asyncio.gather(
        *[
            kb_board.kb.add_column_async(
                project_id=project_id,
                title=col.value,
                description=COLUMN_DESCRIPTIONS[col],
            )
            for col in CardColumn
            if col.value not in kb_board.col_titles
        ]
    )


async def populate_swimlanes(kb_board: KanboardBoard):
    await kb_board.fetch_swimlanes()

    kb = kb_board.kb
    project_id = kb_board.project_id
    lanes = await kb.get_all_swimlanes_async(project_id = project_id)

    lane_names = {sl['name'] for sl in lanes}
    await asyncio.gather(
        *[
            kb_board.kb.add_swimlane_async(
                project_id=kb_board.project_id,
                name=lane.value,
                description=SWIMLANE_DESCRIPTIONS[lane],
            )
            for lane in CardSwimlane
            if lane.value not in lane_names
        ]
    )

async def populate_swimlanes2(kb_board: KanboardBoard):
    await kb_board.fetch_swimlanes()

    await asyncio.gather(
        *[
            kb_board.kb.add_swimlane_async(
                project_id=kb_board.project_id,
                name=lane.value,
                description=SWIMLANE_DESCRIPTIONS[lane],
            )
            for lane in CardSwimlane
            if lane.value not in kb_board.swimlane_titles
        ]
    )

async def create_or_populate_project(kb: kanboard.Client, project_name: str):
    log = logging.getLogger(__name__)

    proj: Optional[dict] = await kb.get_project_by_name_async(name=project_name)

    if proj is None:
        log.info("Project '%s' not found, will create.", project_name)

        proj_id = await kb.create_project_async(name=project_name)
        # proj = await kb.get_project_by_id_async(project_id=proj_id)
    else:
        proj_id = int(proj["id"])

    kb_board = KanboardBoard(kb, proj_id)

    # Repopulate
    await asyncio.gather(
        kb_board.fetch_col_titles(),
        kb_board.fetch_swimlanes(),
        kb_board.fetch_categories(),
    )


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv

    load_dotenv()

    loop = asyncio.get_event_loop()
    # loop.
    # project_id = loop.run_until_complete(async_main(oxr_gitlab, collection))
