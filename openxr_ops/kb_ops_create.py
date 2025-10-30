#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import logging
from pprint import pformat
from typing import Literal, Optional, Union

import kanboard

from openxr_ops.kb_ops_auto_actions import (
    actions_from_migration_subtasks_group,
    get_and_parse_actions,
)
from openxr_ops.kb_ops_subtasks import get_all_subtasks

from .kanboard_helpers import KanboardProject
from .kb_defaults import USERNAME, get_kb_api_token, get_kb_api_url
from .kb_ops_stages import (
    CATEGORY_COLORS,
    COLUMN_DESCRIPTIONS,
    SWIMLANE_DESCRIPTIONS,
    TAG_COLORS,
    TaskCategory,
    TaskColumn,
    TaskSwimlane,
    TaskTags,
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
        for col in TaskColumn
        if col.value not in col_titles
    ]
    if futures:
        log.info("Adding %d columns", len(futures))
        await asyncio.gather(*futures)

    desired = {col.value for col in TaskColumn}

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

    desired_order = [col.value for col in TaskColumn]

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
        first_lane = list(TaskSwimlane)[0]
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
        for lane in TaskSwimlane
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
        for category in TaskCategory
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
        for tag in TaskTags
        if tag.value not in tag_names
    ]

    if futures:
        log.info("Creating %d tag(s)", len(futures))
        await asyncio.gather(*futures)


def find_auto_action(action, expected_auto_actions) -> Optional[int]:
    for i, expected_action in enumerate(expected_auto_actions):
        if action == expected_action:
            return i
    return None


async def populate_actions(
    kb: kanboard.Client, kb_project: KanboardProject, project_id: int
):
    log = logging.getLogger(f"{__name__}.populate_actions")
    subtask_groups = get_all_subtasks()

    expected_auto_actions = []
    """Actions from config file."""

    current_actions_future = get_and_parse_actions(kb, kb_project, project_id)
    for group in subtask_groups:
        action = actions_from_migration_subtasks_group(group)
        if action is not None:
            expected_auto_actions.append(action)

    unparsed, existing_dict = await current_actions_future
    existing_action_ids_to_drop: list[int] = []
    discovered_expected_indices: set[int] = set()
    for action_id, existing_action in existing_dict.items():
        expected_index = find_auto_action(existing_action, expected_auto_actions)
        if expected_index is None:
            log.info(
                "Found that existing auto action with action id %d is not in our expected list. %s",
                action_id,
                pformat(existing_action),
            )
            existing_action_ids_to_drop.append(action_id)
        elif expected_index in discovered_expected_indices:

            log.info(
                "Found that existing auto action with action id %d is a duplicate of index %d in our expected list, will drop it.",
                action_id,
                expected_index,
            )
            existing_action_ids_to_drop.append(action_id)
        else:
            log.info(
                "Found that existing auto action with action id %d is index %d in our expected list. %s",
                action_id,
                expected_index,
                pformat(expected_auto_actions[expected_index]),
            )
            discovered_expected_indices.add(expected_index)
    log.info(
        "Parsed %d automatic actions, left %d unparsed",
        len(existing_dict),
        len(unparsed),
    )

    log.info("Matched %d automatic actions", len(discovered_expected_indices))

    to_destroy = [
        kb.remove_action_async(action_id=action_id)
        for action_id in existing_action_ids_to_drop
    ]
    log.info("Removing %d automatic actions", len(to_destroy))
    await asyncio.gather(*to_destroy)

    to_create = []
    for expected_index, expected_action in enumerate(expected_auto_actions):
        if expected_index in discovered_expected_indices:
            continue
        to_create.append(
            kb.create_action_async(
                project_id=project_id, **expected_action.to_arg_dict(kb_project)
            )
        )

    log.info("Creating %d automatic actions", len(to_create))

    await asyncio.gather(*to_create)


async def populate_project(kb: kanboard.Client, proj_id: int):
    log = logging.getLogger(__name__ + ".populate_project")

    proj = await kb.get_project_by_id_async(project_id=proj_id)

    log.info("Project ID is %d", proj_id)
    log.info("Board URL: %s", proj["url"]["board"])

    # Apply the setup
    await asyncio.gather(
        populate_categories(kb, proj_id),
        populate_columns(kb, proj_id),
        populate_swimlanes(kb, proj_id),
        populate_tags(kb, proj_id),
    )

    kb_project = KanboardProject(kb, proj_id)

    # Repopulate
    await asyncio.gather(
        kb_project.fetch_columns(),
        kb_project.fetch_swimlanes(),
        kb_project.fetch_categories(),
    )

    await populate_actions(kb, kb_project, proj_id)


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

    token = get_kb_api_token()

    url = get_kb_api_url()

    kb = kanboard.Client(
        url=url,
        username=USERNAME,
        password=token,
        # cafile="/path/to/my/cert.pem",
        ignore_hostname_verification=True,
        insecure=True,
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
