#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from pprint import pformat
from typing import Any, Awaitable, Coroutine, Literal, TypedDict, cast

import kanboard

from .kanboard_helpers import KanboardProject
from .kb_auto_actions import AutoActionABC, get_and_parse_actions


class NameIdResults(TypedDict):
    name: str
    id: int


async def populate_columns_general(
    kb: kanboard.Client, project_id: int, enum: type[Enum], descriptions: dict[Any, str]
):
    class ColumnsResultEntry(TypedDict):
        title: str
        id: int

    log = logging.getLogger(f"{__name__}.populate_columns_general")
    cols = cast(
        list[ColumnsResultEntry], await kb.get_columns_async(project_id=project_id)
    )

    col_titles: set[str] = {col["title"] for col in cols}

    futures: list[Awaitable[Any]] = [
        kb.add_column_async(
            project_id=project_id,
            title=col.value,
            description=descriptions[col],
        )
        for col in enum
        if col.value not in col_titles
    ]
    if futures:
        log.info("Adding %d columns", len(futures))
        for future in futures:
            await future

    desired: set[str] = {col.value for col in enum}

    # Remove extra columns
    futures = [
        kb.remove_column_async(column_id=col["id"])
        for col in cols
        if col["title"] not in desired
    ]
    if futures:
        log.info("Removing %d unneeded columns", len(futures))
        await asyncio.gather(*futures)

    updated_cols = cast(
        list[ColumnsResultEntry], await kb.get_columns_async(project_id=project_id)
    )
    col_ids: dict[str, int] = {col["title"]: col["id"] for col in updated_cols}

    desired_order = [col.value for col in enum]

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


async def populate_swimlanes_general(
    kb: kanboard.Client, project_id: int, enum: type[Enum], descriptions: dict[Any, str]
):
    log = logging.getLogger(f"{__name__}.populate_swimlanes_general")

    lanes = cast(
        list[NameIdResults],
        await kb.get_all_swimlanes_async(project_id=project_id),
    )

    lane_names = {sl["name"] for sl in lanes}

    if len(lanes) == 1 and "Default swimlane" in lane_names:
        # Rename our default lane to be the first lane in the list.
        log.info("Updating default swimlane")
        first_lane = list(enum)[0]
        await kb.update_swimlane_async(
            project_id=project_id,
            swimlane_id=lanes[0]["id"],
            name=first_lane.value,
            description=descriptions[first_lane],
        )

        # Avoid adding it again below.
        lane_names.add(first_lane.value)

    futures: list[Awaitable[Any]] = [
        kb.add_swimlane_async(
            project_id=project_id,
            name=lane.value,
            description=descriptions[lane],
        )
        for lane in enum
        if lane.value not in lane_names
    ]

    if futures:
        log.info("Creating %d swimlane(s)", len(futures))
        # we actually want these in order
        for future in futures:
            await future


async def populate_categories_general(
    kb: kanboard.Client, project_id: int, enum: type[Enum], colors: dict[Any, str]
):
    log = logging.getLogger(f"{__name__}.populate_categories_general")

    cats = cast(
        list[NameIdResults],
        await kb.get_all_categories_async(project_id=project_id),
    )

    cat_names = {cat["name"] for cat in cats}

    futures: list[Awaitable[Any]] = [
        kb.create_category_async(
            project_id=project_id,
            name=category.value,
            color_id=colors[category],
        )
        for category in enum
        if category.value not in cat_names
    ]

    if futures:
        log.info("Creating %d category(ies)", len(futures))
        await asyncio.gather(*futures)


async def populate_tags_general(
    kb: kanboard.Client, project_id: int, enum: type[Enum], colors: dict[Any, str]
):
    log = logging.getLogger(f"{__name__}.populate_tags_general")
    tags = cast(
        list[NameIdResults], await kb.get_tags_by_project_async(project_id=project_id)
    )

    tag_names = {tag["name"] for tag in tags}

    futures: list[Coroutine[Any, Any, Any]] = [
        kb.create_tag_async(
            project_id=project_id,
            tag=tag.value,
            color_id=colors[tag],
        )
        for tag in enum
        if tag.value not in tag_names and tag in colors
    ]
    futures.extend(
        [
            kb.create_tag_async(
                project_id=project_id,
                tag=tag.value,
            )
            for tag in enum
            if tag.value not in tag_names and tag not in colors
        ]
    )

    if futures:
        log.info("Creating %d tag(s)", len(futures))
        await asyncio.gather(*futures)


def find_auto_action(action, expected_auto_actions) -> int | None:
    for i, expected_action in enumerate(expected_auto_actions):
        if action == expected_action:
            return i
    return None


async def populate_actions(
    kb: kanboard.Client,
    kb_project: KanboardProject,
    project_id: int,
    expected_auto_actions: list[AutoActionABC],
    *,
    remove_unexpected: bool,
):
    log = logging.getLogger(f"{__name__}.populate_actions")
    current_actions_future = get_and_parse_actions(kb, kb_project, project_id)

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
    log.warning("Unparsed auto actions: %s", pformat(unparsed))

    log.info("Matched %d automatic actions", len(discovered_expected_indices))

    if remove_unexpected:
        to_destroy = [
            kb.remove_action_async(action_id=action_id)
            for action_id in existing_action_ids_to_drop
        ]
        log.info("Removing %d automatic actions", len(to_destroy))
        await asyncio.gather(*to_destroy)

    to_create: list[Awaitable[None]] = []
    for expected_index, expected_action in enumerate(expected_auto_actions):
        if expected_index in discovered_expected_indices:
            continue
        to_create.append(
            kb.create_action_async(
                project_id=project_id, **expected_action.to_arg_dict(kb_project)  # type: ignore
            )
        )

    log.info("Creating %d automatic actions", len(to_create))

    await asyncio.gather(*to_create)


@dataclass
class ProjectData:
    column_enum: type[Enum]
    column_descriptions: dict[Any, str]

    swimlanes_enum: type[Enum]
    swimlanes_descriptions: dict[Any, str]

    categories_enum: type[Enum]
    categories_colors: dict[Any, str]

    tags_enum: type[Enum]
    tags_colors: dict[Any, str]

    expected_auto_actions: list[AutoActionABC]
    remove_unexpected_actions: bool


async def populate_project_general(
    kb: kanboard.Client, proj_id: int, data: ProjectData
):
    log = logging.getLogger(f"{__name__}.populate_project_general")

    proj = await kb.get_project_by_id_async(project_id=proj_id)

    log.info("Project ID is %d", proj_id)
    log.info("Project Board URL: %s", proj["url"]["board"])

    # Apply the setup
    await asyncio.gather(
        populate_categories_general(
            kb, proj_id, data.categories_enum, data.categories_colors
        ),
        populate_columns_general(
            kb, proj_id, data.column_enum, data.column_descriptions
        ),
        populate_swimlanes_general(
            kb, proj_id, data.swimlanes_enum, data.swimlanes_descriptions
        ),
        populate_tags_general(kb, proj_id, data.tags_enum, data.tags_colors),
    )

    kb_project = KanboardProject(kb, proj_id)

    # Repopulate
    await kb_project.fetch_all_id_maps()

    await populate_actions(
        kb,
        kb_project,
        proj_id,
        data.expected_auto_actions,
        remove_unexpected=data.remove_unexpected_actions,
    )
    return kb_project


async def create_or_populate_project_general(
    kb: kanboard.Client, project_name: str, data: ProjectData
):
    log = logging.getLogger(f"{__name__}.create_or_populate_project_general")

    proj: dict | Literal[False] = await kb.get_project_by_name_async(name=project_name)
    print(proj)
    if not proj:
        log.info("Project '%s' not found, will create.", project_name)

        proj_id = await kb.create_project_async(name=project_name)
    else:
        proj_id = int(proj["id"])

    # assert proj

    await populate_project_general(kb, proj_id, data)
