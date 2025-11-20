#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
import re

from .gitlab import GITLAB_SERVER, MAIN_PROJECT_NAME

_MR_URL_RE = re.compile(
    rf"{GITLAB_SERVER}/{MAIN_PROJECT_NAME}/(-/)?merge_requests/(?P<num>[0-9]+)"
)

_ISSUE_URL_RE = re.compile(
    rf"{GITLAB_SERVER}/{MAIN_PROJECT_NAME}/(-/)?issues/(?P<num>[0-9]+)"
)


def extract_mr_number(uri: str | None) -> int | None:
    """Pull out the merge request number from a URI."""
    if not uri:
        return None

    m = _MR_URL_RE.match(uri)
    if not m:
        return None

    return int(m.group("num"))


def extract_issue_number(uri: str | None) -> int | None:
    """Pull out the issue number from a URI."""
    if not uri:
        return None

    m = _ISSUE_URL_RE.match(uri)
    if not m:
        return None

    return int(m.group("num"))
