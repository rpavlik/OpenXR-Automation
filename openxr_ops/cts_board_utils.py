#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""Utilities related to a CTS workboard."""

import re
from typing import Optional, Union, cast

from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from .labels import MainProjectLabels

_THUMBSUP = "thumbsup"
_REQUIRED_THUMB_COUNT = 3

_COMPANY_RE = re.compile(r".*[(](.*)[)]")

# Normalize and shorten company names
_COMPANY_MAP = {
    "Facebook, Inc.": "Meta",
    "Meta Platforms": "Meta",
    "Google, Inc.": "Google",
}


def _find_thumb_companies(
    api_item: ProjectMergeRequest,
) -> str | None:
    companies = []
    awards = api_item.awardemojis.list(get_all=True)
    for award in awards:
        if award.attributes["name"] == _THUMBSUP:
            name = award.attributes["user"]["name"]
            m = _COMPANY_RE.match(name)
            if m:
                name = m.group(1)
            # Map the company name if required.
            companies.append(_COMPANY_MAP.get(name, name))
    if companies:
        if len(companies) == 1:
            return f"(Thumb from {companies[0]})"

        return f"(Thumbs from {', '.join(companies)})"
    return None


def compute_api_item_state_and_suffix(
    api_item: ProjectIssue | ProjectMergeRequest,
) -> tuple[list[str], str]:

    state = []
    suffix = ""
    if api_item.state == "closed":
        state.append("(CLOSED)")
    elif api_item.state == "merged":
        state.append("(MERGED)")

    is_mr = hasattr(api_item, "target_branch")

    if is_mr and hasattr(api_item, "upvotes") and api_item.upvotes > 0:
        state.append("👍" * api_item.upvotes)
        if api_item.upvotes < _REQUIRED_THUMB_COUNT:
            companies = _find_thumb_companies(cast(ProjectMergeRequest, api_item))
            if companies:
                suffix += f"   {companies}"

    if is_mr and hasattr(api_item, "downvotes") and api_item.downvotes > 0:
        state.append("👎" * api_item.downvotes)

    if api_item.attributes.get("has_conflicts"):
        state.append("⚠️")

    if hasattr(api_item, "labels"):
        if MainProjectLabels.OBJECTION_WINDOW in api_item.labels:
            state.append("⏰")

        if MainProjectLabels.NEEDS_AUTHOR_ACTION in api_item.labels:
            state.append("🚧")

        if any("fast track" in label.casefold() for label in api_item.labels):
            state.append("⏩")

    if not api_item.attributes.get("blocking_discussions_resolved", True):
        state.append("💬")

    if state:
        # If we have at least one item, add an empty entry for the trailing space
        state.append("")
    return state, suffix


# Must have at least one of these labels to show up on this board
# since there are now two projects using "Contractor:Approved"
REQUIRED_LABEL_SET = {
    MainProjectLabels.CONFORMANCE_IMPLEMENTATION,
    MainProjectLabels.CONFORMANCE_IN_THE_WILD,
    MainProjectLabels.CONFORMANCE_QUESTION,
}

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
