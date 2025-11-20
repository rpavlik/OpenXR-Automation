# Copyright 2022, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
from dataclasses import dataclass
from typing import Any, Optional

from .kb_enums import InternalLinkRelation


@dataclass
class InternalLinkData:
    """Data describing both ends of an internal link."""

    task_id: int
    link_type: InternalLinkRelation
    other_task_id: int

    task_link_id: int | None = None

    @classmethod
    def parse_internal_links(
        cls, task_id: int, internal_links_list: list[dict[str, Any]]
    ):
        """Parse results of get_all_task_links"""
        return [
            InternalLinkData(
                task_id=task_id,
                link_type=InternalLinkRelation(link["label"]),
                other_task_id=link["task_id"],
                task_link_id=link["id"],
            )
            for link in internal_links_list
        ]
