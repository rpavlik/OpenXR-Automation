#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

from enum import Enum
from dataclasses import dataclass

from .kanboard_helpers import KanboardBoard
from .kb_ops_stages import CardCategory, CardColumn


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
    ASSIGN_CURRENT_USER_ON_COLUMN = "\\Kanboard\\Action\\TaskAssignCurrentUserColumn"


EVENT_NAME = "event_name"
ACTION_NAME = "action_name"


def to_check_box_no_duplicates(allow_duplicate_subtasks: bool):
    if allow_duplicate_subtasks:
        return 0
    return 1


def to_multitasktitles(tasks: list[str]):
    return "\n".join(tasks)


@dataclass
class SubtasksFromCategory:
    """
    Automatic action to create subtasks on creation or update of a task.

    In AutoSubtasks plugin.
    """

    category: CardCategory

    subtasks: list[str]

    allow_duplicate_subtasks: bool = False
    """Whether to add these subtasks even if they already exist."""

    @classmethod
    def get_action_name(cls):
        return AutoActionTypes.SUBTASKS_FROM_CATEGORY.value

    @classmethod
    def get_event_name(cls):
        return "task.create_update"

    def to_arg_dict(self, kb_board: KanboardBoard):
        return {
            EVENT_NAME: self.get_event_name(),
            ACTION_NAME: self.get_action_name(),
            "params": {
                "category_id": self.category.to_category_id(kb_board),
                "user_id": 0,  # not using this for now
                "multitasktitles": to_multitasktitles(self.subtasks),
                "time_estimated": 0,  # unused for now
                "check_box_no_duplicates": to_check_box_no_duplicates(
                    self.allow_duplicate_subtasks
                ),
            },
        }


@dataclass
class SubtasksFromColumn:
    """
    Automatic action to create subtasks on moving a task to a column.

    In AutoSubtasks plugin.
    """

    column: CardColumn

    subtasks: list[str]

    allow_duplicate_subtasks: bool = False
    """Whether to add these subtasks even if they already exist."""

    @classmethod
    def get_action_name(cls):
        return AutoActionTypes.SUBTASKS_FROM_COLUMN.value

    @classmethod
    def get_event_name(cls):
        return "task.create_update"

    def to_arg_dict(self, kb_board: KanboardBoard):
        return {
            EVENT_NAME: self.get_event_name(),
            ACTION_NAME: self.get_action_name(),
            "params": {
                "column_id": self.column.to_column_id(kb_board),
                "user_id": 0,  # not using this for now
                "multitasktitles": to_multitasktitles(self.subtasks),
                "time_estimated": 0,  # unused for now
                "check_box_no_duplicates": not self.allow_duplicate_subtasks,
                "check_box_all_columns": 0,  # unused for now
            },
        }


@dataclass
class SubtasksFromColumnAndCategory:
    """
    Automatic action to create subtasks on moving a task to a column if in a category.

    In AutoSubtasks plugin fork.
    """

    column: CardColumn
    category: CardCategory

    subtasks: list[str]

    allow_duplicate_subtasks: bool = False
    """Whether to add these subtasks even if they already exist."""

    @classmethod
    def get_action_name(cls):
        return AutoActionTypes.SUBTASKS_FROM_COLUMN_AND_CATEGORY.value

    @classmethod
    def get_event_name(cls):
        return "task.move.column"

    def to_arg_dict(self, kb_board: KanboardBoard):
        return {
            EVENT_NAME: self.get_event_name(),
            ACTION_NAME: self.get_action_name(),
            "params": {
                "column_id": self.column.to_column_id(kb_board),
                "category_id": self.category.to_category_id(kb_board),
                "user_id": 0,  # not using this for now
                "multitasktitles": to_multitasktitles(self.subtasks),
                "time_estimated": 0,  # unused for now
                "check_box_no_duplicates": not self.allow_duplicate_subtasks,
            },
        }
