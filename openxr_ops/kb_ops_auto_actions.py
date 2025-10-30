#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from pprint import pformat
from typing import Any, Literal, Optional, Union

import kanboard

from .kanboard_helpers import KanboardProject
from .kb_defaults import USERNAME, get_kb_api_token, get_kb_api_url
from .kb_ops_config import ConfigSubtaskGroup
from .kb_ops_stages import TaskCategory, TaskColumn, TaskSwimlane


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


EVENT_NAME = "event_name"
ACTION_NAME = "action_name"


def _to_check_box_no_duplicates(allow_duplicate_subtasks: bool):
    if allow_duplicate_subtasks:
        return 0
    return 1


def _to_multitasktitles(tasks: list[str]):
    return "\r\n".join(tasks)


class AutoActionEvents(Enum):
    TASK_CREATE_UPDATE = "task.create_update"
    TASK_MOVE_COLUMN = "task.move.column"


@dataclass
class AutoSubtasksBase:
    """Base for creating subtasks automatically."""

    subtasks: list[str]

    allow_duplicate_subtasks: bool
    """Whether to add these subtasks even if they already exist."""

    def make_args(
        self,
        action: AutoActionTypes,
        event: AutoActionEvents,
        params: dict[str, Any],
    ):
        params.update(
            {
                "user_id": 0,  # not using this for now
                "multitasktitles": _to_multitasktitles(self.subtasks),
                "time_estimated": "",  # unused for now
                "check_box_no_duplicates": _to_check_box_no_duplicates(
                    self.allow_duplicate_subtasks
                ),
            }
        )
        return {
            EVENT_NAME: event.value,
            ACTION_NAME: action.value,
            "params": params,
        }

    @classmethod
    def base_try_from_json(cls, action: dict[str, Any]) -> "Optional[AutoSubtasksBase]":
        log = logging.getLogger(f"{__name__}.{cls.__name__}")
        params = action["params"]

        if params["user_id"] not in (0, "0"):
            log.warning("Unexpected user id: %s", str(params["user_id"]))
            return None

        if "time_estimated" in params and params["time_estimated"] not in (0, "0", ""):
            log.warning("Unexpected time estimated: %s", str(params["params"]))
            return None

        multitasktitles: str = params["multitasktitles"]
        subtasks = [subtask.strip() for subtask in multitasktitles.split("\n")]
        allow_duplicate = False
        checkbox_no_dupe = params.get("check_box_no_duplicates", 0)
        if (
            checkbox_no_dupe == 0
            or checkbox_no_dupe == "0"
            or checkbox_no_dupe == "false"
            or checkbox_no_dupe == False
        ):
            allow_duplicate = True
        return cls(subtasks=subtasks, allow_duplicate_subtasks=allow_duplicate)


@dataclass
class SubtasksFromCategory(AutoSubtasksBase):
    """
    Automatic action to create subtasks on creation or update of a task.

    In AutoSubtasks plugin.
    """

    category: Optional[TaskCategory]

    @classmethod
    def create(
        cls,
        category: Optional[TaskCategory],
        subtasks: list[str],
        allow_duplicate_subtasks: bool = False,
    ):
        return SubtasksFromCategory(
            subtasks=subtasks,
            allow_duplicate_subtasks=allow_duplicate_subtasks,
            category=category,
        )

    @classmethod
    def action_name(cls):
        return AutoActionTypes.SUBTASKS_FROM_CATEGORY

    @classmethod
    def default_event_name(cls):
        return AutoActionEvents.TASK_CREATE_UPDATE

    def to_arg_dict(self, kb_project: KanboardProject):
        return self.make_args(
            action=self.action_name(),
            event=self.default_event_name(),
            params={
                "category_id": TaskCategory.optional_to_category_id(
                    kb_project, self.category
                )
            },
        )

    @classmethod
    def try_from_json(cls, kb_project, action: dict[str, Any]):
        log = logging.getLogger(f"{__name__}.{cls.__name__}")
        if action["action_name"] != cls.action_name().value:
            return None
        if action["event_name"] != cls.default_event_name().value:
            return None

        base = AutoSubtasksBase.base_try_from_json(action)
        if base is None:
            return None

        params = action["params"]
        category = TaskCategory.from_category_id_maybe_none(
            kb_project=kb_project, category_id=int(params["category_id"])
        )
        return cls(
            subtasks=base.subtasks,
            allow_duplicate_subtasks=base.allow_duplicate_subtasks,
            category=category,
        )


@dataclass
class SubtasksFromColumn(AutoSubtasksBase):
    """
    Automatic action to create subtasks on moving a task to a column.

    In AutoSubtasks plugin.
    """

    column: TaskColumn

    @classmethod
    def create(
        cls,
        column: TaskColumn,
        subtasks: list[str],
        allow_duplicate_subtasks: bool = False,
    ):
        return cls(
            subtasks=subtasks,
            allow_duplicate_subtasks=allow_duplicate_subtasks,
            column=column,
        )

    @classmethod
    def action_name(cls):
        return AutoActionTypes.SUBTASKS_FROM_COLUMN

    @classmethod
    def default_event_name(cls):
        return AutoActionEvents.TASK_MOVE_COLUMN

    def to_arg_dict(self, kb_project: KanboardProject):
        return self.make_args(
            action=self.action_name(),
            event=self.default_event_name(),
            params={
                "column_id": self.column.to_column_id(kb_project),
                "check_box_all_columns": 0,  # unused for now
            },
        )

    @classmethod
    def try_from_json(cls, kb_project, action: dict[str, Any]):
        log = logging.getLogger(f"{__name__}.{cls.__name__}")
        if action["action_name"] != cls.action_name().value:
            log.debug("action_name mismatch: %s", action["action_name"])
            return None
        if action["event_name"] != cls.default_event_name().value:
            log.debug("event_name mismatch: %s", action["event_name"])
            return None

        base = AutoSubtasksBase.base_try_from_json(action)
        if base is None:
            return None

        params = action["params"]
        column = TaskColumn.from_column_id(kb_project, int(params["column_id"]))
        return cls(
            subtasks=base.subtasks,
            allow_duplicate_subtasks=base.allow_duplicate_subtasks,
            column=column,
        )


@dataclass
class SubtasksFromColumnAndCategory(AutoSubtasksBase):
    """
    Automatic action to create subtasks on moving a task to a column if in a category.

    In AutoSubtasks plugin fork.
    """

    column: TaskColumn
    category: Optional[TaskCategory]

    @classmethod
    def create(
        cls,
        column: TaskColumn,
        category: Optional[TaskCategory],
        subtasks: list[str],
        allow_duplicate_subtasks: bool = False,
    ):
        return cls(
            subtasks=subtasks,
            allow_duplicate_subtasks=allow_duplicate_subtasks,
            column=column,
            category=category,
        )

    @classmethod
    def action_name(cls):
        return AutoActionTypes.SUBTASKS_FROM_COLUMN_AND_CATEGORY

    @classmethod
    def default_event_name(cls):
        return AutoActionEvents.TASK_MOVE_COLUMN

    def to_arg_dict(self, kb_project: KanboardProject):
        return self.make_args(
            action=self.action_name(),
            event=self.default_event_name(),
            params={
                "column_id": self.column.to_column_id(kb_project),
                "category_id": TaskCategory.optional_to_category_id(
                    kb_project, self.category
                ),
            },
        )

    @classmethod
    def try_from_json(cls, kb_project, action: dict[str, Any]):
        log = logging.getLogger(f"{__name__}.{cls.__name__}")
        if action["action_name"] != cls.action_name().value:
            log.debug("action_name mismatch: %s", action["action_name"])
            return None
        if action["event_name"] != cls.default_event_name().value:
            log.debug("event_name mismatch: %s", action["event_name"])
            return None

        base = AutoSubtasksBase.base_try_from_json(action)
        if base is None:
            return None

        params = action["params"]
        column = TaskColumn.from_column_id(kb_project, int(params["column_id"]))
        category = TaskCategory.from_category_id_maybe_none(
            kb_project=kb_project, category_id=int(params["category_id"])
        )
        return cls(
            subtasks=base.subtasks,
            allow_duplicate_subtasks=base.allow_duplicate_subtasks,
            column=column,
            category=category,
        )


@dataclass
class SubtasksFromColumnAndSwimlane(AutoSubtasksBase):
    """
    Automatic action to create subtasks on moving a task to a column if in a swimlane.

    In AutoSubtasks plugin fork.
    """

    column: TaskColumn
    swimlane: TaskSwimlane

    @classmethod
    def create(
        cls,
        column: TaskColumn,
        swimlane: TaskSwimlane,
        subtasks: list[str],
        allow_duplicate_subtasks: bool = False,
    ):
        return cls(
            subtasks=subtasks,
            allow_duplicate_subtasks=allow_duplicate_subtasks,
            column=column,
            swimlane=swimlane,
        )

    @classmethod
    def action_name(cls):
        return AutoActionTypes.SUBTASKS_FROM_COLUMN_AND_SWIMLANE

    @classmethod
    def default_event_name(cls):
        return AutoActionEvents.TASK_MOVE_COLUMN

    def to_arg_dict(self, kb_project: KanboardProject):
        return self.make_args(
            action=self.action_name(),
            event=self.default_event_name(),
            params={
                "column_id": self.column.to_column_id(kb_project),
                "swimlane_id": self.swimlane.to_swimlane_id(kb_project),
            },
        )

    @classmethod
    def try_from_json(cls, kb_project, action: dict[str, Any]):
        log = logging.getLogger(f"{__name__}.{cls.__name__}")
        if action["action_name"] != cls.action_name().value:
            log.debug("action_name mismatch: %s", action["action_name"])
            return None
        if action["event_name"] != cls.default_event_name().value:
            log.debug("event_name mismatch: %s", action["event_name"])
            return None

        base = AutoSubtasksBase.base_try_from_json(action)
        if base is None:
            return None

        params = action["params"]
        column = TaskColumn.from_column_id(kb_project, int(params["column_id"]))
        swimlane = TaskSwimlane.from_swimlane_id(
            kb_project=kb_project, swimlane_id=int(params["swimlane_id"])
        )
        return cls(
            subtasks=base.subtasks,
            allow_duplicate_subtasks=base.allow_duplicate_subtasks,
            column=column,
            swimlane=swimlane,
        )


@dataclass
class SubtasksFromColumnAndSwimlaneAndCategory(AutoSubtasksBase):
    """
    Automatic action to create subtasks on moving a task to a column if in a swimlane and category.

    In AutoSubtasks plugin fork.
    """

    column: TaskColumn
    swimlane: TaskSwimlane
    category: Optional[TaskCategory]

    @classmethod
    def create(
        cls,
        column: TaskColumn,
        swimlane: TaskSwimlane,
        category: Optional[TaskCategory],
        subtasks: list[str],
        allow_duplicate_subtasks: bool = False,
    ):
        return cls(
            subtasks=subtasks,
            allow_duplicate_subtasks=allow_duplicate_subtasks,
            column=column,
            swimlane=swimlane,
            category=category,
        )

    @classmethod
    def action_name(cls):
        return AutoActionTypes.SUBTASKS_FROM_COLUMN_AND_SWIMLANE_AND_CATEGORY

    @classmethod
    def default_event_name(cls):
        return AutoActionEvents.TASK_MOVE_COLUMN

    def to_arg_dict(self, kb_project: KanboardProject):
        return self.make_args(
            action=self.action_name(),
            event=self.default_event_name(),
            params={
                "column_id": self.column.to_column_id(kb_project),
                "swimlane_id": self.swimlane.to_swimlane_id(kb_project),
                "category_id": TaskCategory.optional_to_category_id(
                    kb_project, self.category
                ),
            },
        )

    @classmethod
    def try_from_json(cls, kb_project, action: dict[str, Any]):
        log = logging.getLogger(f"{__name__}.{cls.__name__}")
        if action["action_name"] != cls.action_name().value:
            log.debug("action_name mismatch: %s", action["action_name"])
            return None
        if action["event_name"] != cls.default_event_name().value:
            log.debug("event_name mismatch: %s", action["event_name"])
            return None

        base = AutoSubtasksBase.base_try_from_json(action)
        if base is None:
            return None

        params = action["params"]
        column = TaskColumn.from_column_id(kb_project, int(params["column_id"]))
        swimlane = TaskSwimlane.from_swimlane_id(
            kb_project=kb_project, swimlane_id=int(params["swimlane_id"])
        )
        category = TaskCategory.from_category_id_maybe_none(
            kb_project=kb_project, category_id=int(params["category_id"])
        )
        return cls(
            subtasks=base.subtasks,
            allow_duplicate_subtasks=base.allow_duplicate_subtasks,
            column=column,
            swimlane=swimlane,
            category=category,
        )


def actions_from_subtask_group(group: ConfigSubtaskGroup):
    log = logging.getLogger(f"{__name__}.from_migration_subtasks_group")
    subtask_names = [subtask.get_full_subtask_name(group) for subtask in group.subtasks]

    if group.condition:
        if (
            group.condition.column
            and group.condition.swimlane
            and group.condition.has_category_predicate()
        ):
            return SubtasksFromColumnAndSwimlaneAndCategory.create(
                column=group.condition.column,
                swimlane=group.condition.swimlane,
                category=group.condition.get_category_predicate(),
                subtasks=subtask_names,
                allow_duplicate_subtasks=group.condition.allow_duplicate_subtasks,
            )

        if (
            group.condition.column
            and group.condition.swimlane
            and not group.condition.has_category_predicate()
        ):
            return SubtasksFromColumnAndSwimlane.create(
                column=group.condition.column,
                swimlane=group.condition.swimlane,
                subtasks=subtask_names,
                allow_duplicate_subtasks=group.condition.allow_duplicate_subtasks,
            )

        if (
            group.condition.column
            and group.condition.has_category_predicate()
            and not group.condition.swimlane
        ):
            return SubtasksFromColumnAndCategory.create(
                column=group.condition.column,
                category=group.condition.get_category_predicate(),
                subtasks=subtask_names,
                allow_duplicate_subtasks=group.condition.allow_duplicate_subtasks,
            )

        if (
            group.condition.column
            and not group.condition.has_category_predicate()
            and not group.condition.swimlane
        ):
            return SubtasksFromColumn.create(
                column=group.condition.column,
                subtasks=subtask_names,
                allow_duplicate_subtasks=group.condition.allow_duplicate_subtasks,
            )

        if (
            group.condition.has_category_predicate()
            and not group.condition.column
            and not group.condition.swimlane
        ):
            return SubtasksFromCategory.create(
                category=group.condition.get_category_predicate(),
                subtasks=subtask_names,
                allow_duplicate_subtasks=group.condition.allow_duplicate_subtasks,
            )
        log.warning(
            "Condition does not match any known combo: %s", pformat(group.condition)
        )
        return
    log.warning("No condition provided for %s", group.group_name)


AUTO_ACTION_TYPES = [
    SubtasksFromColumnAndSwimlaneAndCategory,
    SubtasksFromColumnAndSwimlane,
    SubtasksFromColumnAndCategory,
    SubtasksFromCategory,
    SubtasksFromColumn,
]


def from_json(kb_project, action: dict[str, Any]):
    for t in AUTO_ACTION_TYPES:
        result = t.try_from_json(kb_project, action)

        if result is not None:
            return result

    return None


async def get_and_parse_actions(kb: kanboard.Client, kb_project, proj_id: int):
    unparsed = []
    all_parsed: dict[int, AutoSubtasksBase] = dict()

    actions = await kb.get_actions_async(project_id=proj_id)
    for action in actions:
        parsed = from_json(kb_project=kb_project, action=action)
        if parsed is None:
            unparsed.append(action)
        else:
            all_parsed[action["id"]] = parsed

    return unparsed, all_parsed


async def get_and_parse_actions_from_named_project(
    kb: kanboard.Client, project_name: str
):
    log = logging.getLogger(f"{__name__}.get_and_parse_actions_from_named_project")
    proj: Union[dict, Literal[False]] = await kb.get_project_by_name_async(
        name=project_name
    )
    if not proj:
        log.warning("Project '%s' not found, skipping", project_name)
        return None, None

    proj_id = int(proj["id"])
    kb_project = KanboardProject(kb, proj_id)
    await kb_project.fetch_all_id_maps()
    return await get_and_parse_actions(kb, kb_project=kb_project, proj_id=proj_id)


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    from dotenv import load_dotenv

    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_help = True
    parser.add_argument(
        "--project",
        type=str,
        nargs=1,
        help="Create or update the named project",
    )

    parser.add_argument(
        "--project-id",
        type=int,
        nargs=1,
        help="Update the project with the given ID",
    )
    args = parser.parse_args()

    # if not args.project:
    #     parser.print_help()
    #     sys.exit(1)

    log = logging.getLogger(__name__)

    async def runner():

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

        log.info("Client created: %s @ %s", USERNAME, url)

        if args.project:

            unparsed, all_parsed = await get_and_parse_actions_from_named_project(
                kb, args.project
            )
            from pprint import pprint

            print("Unparsed")
            pprint(unparsed)
            print("Parsed")
            pprint(all_parsed)

        if args.project_id:

            proj_id = args.project_id[0]
            kb_project = KanboardProject(kb, proj_id)
            await kb_project.fetch_all_id_maps()
            unparsed, all_parsed = await get_and_parse_actions(kb, kb_project, proj_id)
            from pprint import pprint

            print("Unparsed")
            pprint(unparsed)
            print("Parsed")
            pprint(all_parsed)

    asyncio.run(runner())
