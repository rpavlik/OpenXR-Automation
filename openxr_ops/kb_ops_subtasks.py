#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import importlib
import importlib.resources
import tomllib
from dataclasses import dataclass
from typing import Optional

from .kb_ops_stages import CardCategory, CardColumn, CardSwimlane


@dataclass
class MigrationSubtaskEntry:
    """A single subtask."""

    task: str
    """Subtask name/string."""

    migration_prefix: str
    """String to search for in old checklist to determine the subtask state."""

    @classmethod
    def from_dict(cls, d: dict):
        task = d["task"]
        migration_prefix = d.get("migration_prefix", task)
        return cls(task=task, migration_prefix=migration_prefix)


def parse_into(enum_type, s: Optional[str]):
    if s is None:
        return None
    return enum_type(s)


@dataclass
class MigrationSubtasksGroupCondition:
    """
    Conditions to automatically add a group of subtasks.

    All populated condition fields must match to be true.
    """

    swimlane: Optional[CardSwimlane]
    column: Optional[CardColumn]
    category: Optional[CardCategory]
    exclude_categories: bool = False

    allow_duplicate_subtasks: bool = False
    """Whether to add these subtasks even if they already exist."""

    @classmethod
    def from_dict(cls, d: dict):
        swimlane = parse_into(CardSwimlane, d.get("swimlane"))

        column = parse_into(CardColumn, d.get("column"))

        category = parse_into(CardCategory, d.get("category"))

        return cls(
            swimlane=swimlane,
            column=column,
            category=category,
            exclude_categories=d.get("exclude_categories", False),
            allow_duplicate_subtasks=d.get("allow_duplicate_subtasks", False),
        )


@dataclass
class MigrationSubtasksGroup:
    """A collection of subtasks, often with a related trigger."""

    group_name: str
    """Arbitrary name."""

    tasks: list[MigrationSubtaskEntry]
    """List of subtasks in the group."""

    condition: Optional[MigrationSubtasksGroupCondition] = None
    """Condition to evaluate to auto-create the subtasks in the group."""

    @classmethod
    def from_dict(cls, d: dict):
        """Contruct a group from a dict (generally from TOML)."""
        group_name = d["group_name"]
        tasks = [MigrationSubtaskEntry.from_dict(task) for task in d["task"]]
        condition = None
        cond_dict = d.get("condition")
        if cond_dict:
            condition = MigrationSubtasksGroupCondition.from_dict(cond_dict)
        return cls(group_name=group_name, tasks=tasks, condition=condition)


def get_all_subtasks() -> list[MigrationSubtasksGroup]:
    """Load all subtasks from the data file."""
    data = (
        importlib.resources.files("openxr_ops")
        .joinpath("subtasks.toml")
        .read_text(encoding="utf-8")
    )
    parsed = tomllib.loads(data)
    return [
        MigrationSubtasksGroup.from_dict(subtasks) for subtasks in parsed["subtasks"]
    ]


if __name__ == "__main__":
    subtasks = get_all_subtasks()
    import pprint

    pprint.pprint(subtasks)
