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
) -> Optional[str]:
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
    api_item: Union[ProjectIssue, ProjectMergeRequest],
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
