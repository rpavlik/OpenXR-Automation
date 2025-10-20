#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import logging
import os
from pprint import pformat
from typing import Literal, Union

import kanboard

from .kanboard_helpers import KanboardBoard
from .kb_defaults import SERVER, USERNAME
from .kb_ops_stages import (
    CATEGORY_COLORS,
    COLUMN_DESCRIPTIONS,
    SWIMLANE_DESCRIPTIONS,
    TAG_COLORS,
    CardCategory,
    CardColumn,
    CardSwimlane,
    CardTags,
)


async def populate_columns(kb: kanboard.Client, project_id: int):
    log = logging.getLogger(__name__ + ".populate_columns")
    cols = await kb.get_columns_async(project_id=project_id)

    col_titles = {col["title"] for col in cols}

    futures = [
        kb.add_column_async(
            project_id=project_id,
            title=col.value,
            description=COLUMN_DESCRIPTIONS[col],
        )
        for col in CardColumn
        if col.value not in col_titles
    ]
    if futures:
        log.info("Adding %d columns", len(futures))
        await asyncio.gather(*futures)

    desired = {col.value for col in CardColumn}

    # Remove extra columns
    futures = [
        kb.remove_column_async(column_id=col["id"])
        for col in cols
        if col["title"] not in desired
    ]
    if futures:
        log.info("Removing %d unneeded columns", len(futures))
        await asyncio.gather(*futures)

    updated_cols = await kb.get_columns_async(project_id=project_id)
    col_ids = {col["title"]: col["id"] for col in updated_cols}

    desired_order = [col.value for col in CardColumn]

    # Make sure column order matches
    if any(
        col["title"] != desired_title
        for col, desired_title in zip(updated_cols, desired_order)
    ):
        log.info("Correcting column order")
        for position, col_name in enumerate(desired_order, 1):
            col_id = col_ids[col_name]
            await kb.change_column_position_async(
                project_id=project_id, column_id=col_id, position=position
            )


async def populate_swimlanes(kb: kanboard.Client, project_id: int):
    log = logging.getLogger(__name__ + ".populate_swimlanes")
    lanes = await kb.get_all_swimlanes_async(project_id=project_id)

    lane_names = {sl["name"] for sl in lanes}

    if len(lanes) == 1 and "Default swimlane" in lane_names:
        # Rename our default lane to be the first lane in the list.
        log.info("Updating default swimlane")
        first_lane = list(CardSwimlane)[0]
        await kb.update_swimlane_async(
            project_id=project_id,
            swimlane_id=lanes[0]["id"],
            name=first_lane.value,
            description=SWIMLANE_DESCRIPTIONS[first_lane],
        )

        # Avoid adding it again below.
        lane_names.add(first_lane.value)

    futures = [
        kb.add_swimlane_async(
            project_id=project_id,
            name=lane.value,
            description=SWIMLANE_DESCRIPTIONS[lane],
        )
        for lane in CardSwimlane
        if lane.value not in lane_names
    ]

    if futures:
        log.info("Creating %d swimlane(s)", len(futures))
        await asyncio.gather(*futures)


async def populate_categories(kb: kanboard.Client, project_id: int):
    log = logging.getLogger(__name__ + ".populate_categories")
    cats = await kb.get_all_categories_async(project_id=project_id)

    cat_names = {cat["name"] for cat in cats}

    futures = [
        kb.create_category_async(
            project_id=project_id,
            name=category.value,
            color_id=CATEGORY_COLORS[category],
        )
        for category in CardCategory
        if category.value not in cat_names
    ]

    if futures:
        log.info("Creating %d category(ies)", len(futures))
        await asyncio.gather(*futures)


async def populate_tags(kb: kanboard.Client, project_id: int):
    log = logging.getLogger(__name__ + ".populate_tags")
    tags = await kb.get_tags_by_project_async(project_id=project_id)

    tag_names = {tag["name"] for tag in tags}

    futures = [
        kb.create_tag_async(
            project_id=project_id,
            tag=tag.value,
            color_id=TAG_COLORS[tag],
        )
        for tag in CardTags
        if tag.value not in tag_names
    ]

    if futures:
        log.info("Creating %d tag(s)", len(futures))
        await asyncio.gather(*futures)


async def populate_project(kb: kanboard.Client, proj_id: int):
    log = logging.getLogger(__name__ + ".populate_project")

    proj = await kb.get_project_by_id_async(project_id=proj_id)

    log.info("Project ID is %d", proj_id)
    log.info("Board: %s", proj["url"]["board"])

    # Apply the setup
    await asyncio.gather(
        populate_categories(kb, proj_id),
        populate_columns(kb, proj_id),
        populate_swimlanes(kb, proj_id),
        populate_tags(kb, proj_id),
    )

    kb_board = KanboardBoard(kb, proj_id)

    # Repopulate
    await asyncio.gather(
        kb_board.fetch_columns(),
        kb_board.fetch_swimlanes(),
        kb_board.fetch_categories(),
    )


async def create_or_populate_project(kb: kanboard.Client, project_name: str):
    log = logging.getLogger(__name__ + ".create_or_populate_project")

    proj: Union[dict, Literal[False]] = await kb.get_project_by_name_async(
        name=project_name
    )
    print(proj)
    if not proj:
        log.info("Project '%s' not found, will create.", project_name)

        proj_id = await kb.create_project_async(name=project_name)
        # proj = await kb.get_project_by_id_async(project_id=proj_id)
    else:
        proj_id = int(proj["id"])

    # assert proj

    await populate_project(kb, proj_id)


async def get_projects(kb: kanboard.Client):
    log = logging.getLogger(__name__ + ".get_projects")
    projects = await kb.get_all_projects_async()
    log.info("All projects: %s", pformat(projects))


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv

    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_help = True
    parser.add_argument(
        "--project",
        type=str,
        nargs=1,
        help="Create or update the named project",
    )

    parser.add_argument(
        "--project-id",
        type=int,
        nargs=1,
        help="Update the project with the given ID",
    )
    args = parser.parse_args()

    # if not args.project:
    #     parser.print_help()
    #     sys.exit(1)

    log = logging.getLogger(__name__)

    token = os.environ.get("KANBOARD_API_TOKEN", "")

    url = f"https://{SERVER}/jsonrpc.php"

    kb = kanboard.Client(
        url=url,
        username=USERNAME,
        password=token,
        # cafile="/path/to/my/cert.pem",
        # ignore_hostname_verification=True,
        # insecure=True,
    )

    log.info("Client created: %s @ %s", USERNAME, url)

    # jobs = [get_projects(kb)]

    loop = asyncio.get_event_loop()
    if args.project:

        async def runner():
            await get_projects(kb)
            await create_or_populate_project(kb, args.project[0])

        loop.run_until_complete(runner())

    if args.project_id:
        # jobs.append(populate_project(kb, args.project_id))

        async def runner():
            await get_projects(kb)
            await populate_project(kb, args.project_id[0])

        loop.run_until_complete(runner())

    # loop.run_until_complete(asyncio.gather(*jobs))
