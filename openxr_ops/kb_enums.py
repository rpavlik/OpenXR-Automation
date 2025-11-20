#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

from enum import Enum
from typing import Optional

from .kanboard_helpers import LinkIdMapping


class InternalLinkRelation(Enum):
    RELATES_TO = "relates to"  # no opposite
    BLOCKS = "blocks"
    IS_BLOCKED_BY = "is blocked by"
    DUPLICATES = "duplicates"
    IS_DUPLICATED_BY = "is duplicated by"
    IS_A_PARENT_OF = "is a parent of"
    IS_A_CHILD_OF = "is a child of"
    IS_A_MILESTONE_OF = "is a milestone of"
    TARGETS_MILESTONE = "targets milestone"
    IS_FIXED_BY = "is fixed by"
    FIXES = "fixes"

    def try_to_link_id(self, link_mapping: LinkIdMapping) -> Optional[int]:
        # depends on data cached by link_mapping
        return link_mapping.link_label_to_id.get(self.value)

    def to_link_id(self, link_mapping: LinkIdMapping) -> int:
        result = self.try_to_link_id(link_mapping)
        if result is None:
            raise RuntimeError(f"Missing link ID for {self!s}")
        return result

    @classmethod
    def from_link_id(
        cls, link_mapping: LinkIdMapping, label_id: int
    ) -> "InternalLinkRelation":
        # depends on data cached by link_mapping
        return cls(link_mapping.link_id_to_label[label_id])


INTERNAL_LINK_OPPOSITES: dict[InternalLinkRelation, InternalLinkRelation] = {
    InternalLinkRelation.BLOCKS: InternalLinkRelation.IS_BLOCKED_BY,
    InternalLinkRelation.IS_BLOCKED_BY: InternalLinkRelation.BLOCKS,
    InternalLinkRelation.DUPLICATES: InternalLinkRelation.IS_BLOCKED_BY,
    InternalLinkRelation.IS_DUPLICATED_BY: InternalLinkRelation.DUPLICATES,
    InternalLinkRelation.IS_A_PARENT_OF: InternalLinkRelation.IS_DUPLICATED_BY,
    InternalLinkRelation.IS_A_CHILD_OF: InternalLinkRelation.IS_A_PARENT_OF,
    InternalLinkRelation.IS_A_MILESTONE_OF: InternalLinkRelation.IS_A_CHILD_OF,
    InternalLinkRelation.TARGETS_MILESTONE: InternalLinkRelation.IS_A_MILESTONE_OF,
    InternalLinkRelation.IS_FIXED_BY: InternalLinkRelation.TARGETS_MILESTONE,
    InternalLinkRelation.FIXES: InternalLinkRelation.IS_FIXED_BY,
}


class AutoActionEvents(Enum):
    TASK_CREATE = "task.create"
    TASK_CREATE_UPDATE = "task.create_update"
    TASK_MOVE_COLUMN = "task.move.column"


class AutoActionTypes(Enum):
    SUBTASKS_FROM_CATEGORY = (
        "\\Kanboard\\Plugin\\AutoSubtasks\\Action\\CategoryAutoSubtaskVanilla"
    )
    SUBTASKS_FROM_COLUMN = (
        "\\Kanboard\\Plugin\\AutoSubtasks\\Action\\AutoCreateSubtaskVanilla"
    )
    SUBTASKS_FROM_COLUMN_AND_CATEGORY = (
        "\\Kanboard\\Plugin\\AutoSubtasks\\Action\\CategoryColAutoSubtaskVanilla"
    )
    SUBTASKS_FROM_COLUMN_AND_SWIMLANE = (
        "\\Kanboard\\Plugin\\AutoSubtasks\\Action\\SwimlaneAutoCreateSubtaskVanilla"
    )

    SUBTASKS_FROM_COLUMN_AND_SWIMLANE_AND_CATEGORY = "\\Kanboard\\Plugin\\AutoSubtasks\\Action\\SwimlaneCategoryColAutoSubtaskVanilla"

    ASSIGN_CURRENT_USER_ON_COLUMN = "\\Kanboard\\Action\\TaskAssignCurrentUserColumn"

    TAG_FROM_COLUMN = "\\Kanboard\\Plugin\\TagAutomaticAction\\Action\\TaskAssignTagCol"

    TAG_FROM_COLUMN_AND_SWIMLANE = (
        "\\Kanboard\\Plugin\\TagAutomaticAction\\Action\\TaskAssignTagColSwimlane"
    )


EVENT_NAME = "event_name"
ACTION_NAME = "action_name"
