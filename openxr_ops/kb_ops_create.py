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

import kanboard

from .kb_auto_actions import AutoActionABC, auto_actions_from_config
from .kb_create import (
    ProjectData,
    create_or_populate_project_general,
    populate_project_general,
)
from .kb_defaults import USERNAME, get_kb_api_token, get_kb_api_url
from .kb_ops_config import get_config_data
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


def get_ops_project_data() -> ProjectData:
    config = get_config_data()
    expected_auto_actions: list[AutoActionABC] = auto_actions_from_config(config)
    return ProjectData(
        column_enum=TaskColumn,
        column_descriptions=COLUMN_DESCRIPTIONS,
        swimlanes_enum=TaskSwimlane,
        swimlanes_descriptions=SWIMLANE_DESCRIPTIONS,
        categories_enum=TaskCategory,
        categories_colors=CATEGORY_COLORS,
        tags_enum=TaskTags,
        tags_colors=TAG_COLORS,
        expected_auto_actions=expected_auto_actions,
        remove_unexpected_actions=True,
    )


async def populate_project(kb: kanboard.Client, proj_id: int):
    kb_project = await populate_project_general(
        kb,
        proj_id,
        get_ops_project_data(),
    )
    return kb_project


async def create_or_populate_project(kb: kanboard.Client, project_name: str):
    await create_or_populate_project_general(kb, project_name, get_ops_project_data())


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

    async def runner():
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

        if args.project:
            await get_projects(kb)
            await create_or_populate_project(kb, args.project[0])

        if args.project_id:

            await get_projects(kb)
            await populate_project(kb, args.project_id[0])

    asyncio.run(runner())
