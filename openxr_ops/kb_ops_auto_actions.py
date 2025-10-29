#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

from enum import Enum
from dataclasses import dataclass, field
from typing import Any

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


def _to_check_box_no_duplicates(allow_duplicate_subtasks: bool):
    if allow_duplicate_subtasks:
        return 0
    return 1


def _to_multitasktitles(tasks: list[str]):
    return "\n".join(tasks)


class AutoActionEvents(Enum):
    TASK_CREATE_UPDATE = "task.create_update"
    TASK_MOVE_COLUMN = "task.move.column"


@dataclass
class AutoSubtasksBase:
    """Base for creating subtasks automatically."""

    action_name: AutoActionTypes
    event: AutoActionEvents

    subtasks: list[str]

    allow_duplicate_subtasks: bool
    """Whether to add these subtasks even if they already exist."""

    def make_args(self, specific_params: dict[str, Any]):
        specific_params.update(
            {
                "user_id": 0,  # not using this for now
                "multitasktitles": _to_multitasktitles(self.subtasks),
                "time_estimated": 0,  # unused for now
                "check_box_no_duplicates": _to_check_box_no_duplicates(
                    self.allow_duplicate_subtasks
                ),
            }
        )
        return {
            EVENT_NAME: self.event.value,
            ACTION_NAME: self.action_name.value,
            "params": specific_params,
        }


@dataclass
class SubtasksFromCategory(AutoSubtasksBase):
    """
    Automatic action to create subtasks on creation or update of a task.

    In AutoSubtasks plugin.
    """

    category: CardCategory

    # @classmethod
    # def get_action_name(cls):
    #     return AutoActionTypes.SUBTASKS_FROM_CATEGORY.value

    # @classmethod
    # def get_event_name(cls):
    #     return "task.create_update"

    @classmethod
    def create(
        cls,
        category: CardCategory,
        subtasks: list[str],
        allow_duplicate_subtasks: bool = False,
    ):
        return SubtasksFromCategory(
            action_name=AutoActionTypes.SUBTASKS_FROM_CATEGORY,
            event=AutoActionEvents.TASK_CREATE_UPDATE,
            subtasks=subtasks,
            allow_duplicate_subtasks=allow_duplicate_subtasks,
            category=category,
        )

    def to_arg_dict(self, kb_board: KanboardBoard):
        assert self.event == AutoActionEvents.TASK_CREATE_UPDATE
        assert self.action_name == AutoActionTypes.SUBTASKS_FROM_CATEGORY
        return self.make_args({"category_id": self.category.to_category_id(kb_board)})


@dataclass
class SubtasksFromColumn(AutoSubtasksBase):
    """
    Automatic action to create subtasks on moving a task to a column.

    In AutoSubtasks plugin.
    """

    column: CardColumn

    # @classmethod
    # def get_action_name(cls):
    #     return AutoActionTypes.SUBTASKS_FROM_COLUMN.value

    # @classmethod
    # def get_event_name(cls):
    #     return "task.create_update"

    @classmethod
    def create(
        cls,
        column: CardColumn,
        subtasks: list[str],
        allow_duplicate_subtasks: bool = False,
    ):
        return cls(
            action_name=AutoActionTypes.SUBTASKS_FROM_COLUMN,
            event=AutoActionEvents.TASK_CREATE_UPDATE,
            subtasks=subtasks,
            allow_duplicate_subtasks=allow_duplicate_subtasks,
            column=column,
        )

    def to_arg_dict(self, kb_board: KanboardBoard):
        assert self.event == AutoActionEvents.TASK_CREATE_UPDATE
        assert self.action_name == AutoActionTypes.SUBTASKS_FROM_CATEGORY
        return self.make_args(
            {
                "column_id": self.column.to_column_id(kb_board),
                "check_box_all_columns": 0,  # unused for now
            }
        )


@dataclass
class SubtasksFromColumnAndCategory(AutoSubtasksBase):
    """
    Automatic action to create subtasks on moving a task to a column if in a category.

    In AutoSubtasks plugin fork.
    """

    column: CardColumn
    category: CardCategory

    # @classmethod
    # def get_action_name(cls):
    #     return AutoActionTypes.SUBTASKS_FROM_COLUMN_AND_CATEGORY.value

    # @classmethod
    # def get_event_name(cls):
    #     return "task.move.column"

    @classmethod
    def create(
        cls,
        column: CardColumn,
        category: CardCategory,
        subtasks: list[str],
        allow_duplicate_subtasks: bool = False,
    ):
        return cls(
            action_name=AutoActionTypes.SUBTASKS_FROM_COLUMN_AND_CATEGORY,
            event=AutoActionEvents.TASK_MOVE_COLUMN,
            subtasks=subtasks,
            allow_duplicate_subtasks=allow_duplicate_subtasks,
            column=column,
            category=category,
        )

    def to_arg_dict(self, kb_board: KanboardBoard):
        assert self.event == AutoActionEvents.TASK_MOVE_COLUMN
        assert self.action_name == AutoActionTypes.SUBTASKS_FROM_COLUMN_AND_CATEGORY
        return self.make_args(
            {
                "column_id": self.column.to_column_id(kb_board),
                "category_id": self.category.to_category_id(kb_board),
            }
        )

    # def to_arg_dict(self, kb_board: KanboardBoard):
    #     return {
    #         EVENT_NAME: self.get_event_name(),
    #         ACTION_NAME: self.get_action_name(),
    #         "params": {
    #             "column_id": self.column.to_column_id(kb_board),
    #             "category_id": self.category.to_category_id(kb_board),
    #             "user_id": 0,  # not using this for now
    #             "multitasktitles": to_multitasktitles(self.subtasks),
    #             "time_estimated": 0,  # unused for now
    #             "check_box_no_duplicates": not self.allow_duplicate_subtasks,
    #         },
    #     }
