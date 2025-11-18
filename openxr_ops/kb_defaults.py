#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging
import os
from typing import Any

import kanboard

SERVER = "openxr-boards.khronos.org"
USERNAME = "khronos-bot"

REAL_PROJ_NAME = "OpenXRExtensions"
REAL_PROJ_NUMBER = 29

REAL_HUMAN_BOARD_URL = f"https://{SERVER}/board/{REAL_PROJ_NUMBER}"
REAL_HUMAN_OVERVIEW_URL = f"https://{SERVER}/project/{REAL_PROJ_NUMBER}/overview/"

CTS_PROJ_NAME = "CTS Contractor"

def get_kb_api_url():
    url = os.environ.get("KANBOARD_URL", default=f"https://{SERVER}/jsonrpc.php")
    return url


def get_kb_api_token():
    return os.environ.get("KANBOARD_API_TOKEN", default="")


async def connect_and_get_project(
    project_name: str = REAL_PROJ_NAME,
) -> tuple[kanboard.Client, dict[str, Any]]:
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
    log.info("Getting project by name")
    from pprint import pformat

    proj = await kb.get_project_by_name_async(name=project_name)
    if proj == False:
        raise RuntimeError("No project named " + project_name)

    log.debug("Project data: %s", pformat(proj))
    return kb, proj
