#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import os

SERVER = "openxr-boards.khronos.org"
USERNAME = "khronos-bot"


def get_kb_api_url():
    url = os.environ.get("KANBOARD_URL", default=f"https://{SERVER}/jsonrpc.php")
    return url


def get_kb_api_token():
    return os.environ.get("KANBOARD_API_TOKEN", default="")
