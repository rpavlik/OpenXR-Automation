#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

from enum import Enum


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
