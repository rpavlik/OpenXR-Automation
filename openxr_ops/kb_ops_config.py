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

from .kb_enums import AutoActionEvents
from .kb_ops_stages import TaskCategory, TaskColumn, TaskSwimlane


@dataclass
class ConfigSubtaskEntry:
    """A single subtask."""

    name: str
    """Subtask name/string."""

    migration_prefix: str
    """String to search for in old checklist to determine the subtask state."""

    @classmethod
    def from_dict(cls, d: dict):
        name = d["name"]
        migration_prefix = d.get("migration_prefix", name)
        return cls(name=name, migration_prefix=migration_prefix)

    def get_full_subtask_name(self, group):
        if group.prefix:
            return f"{group.prefix} {self.name}"
        return self.name


def parse_into(enum_type, s: Optional[str]):
    if s is None:
        return None
    return enum_type(s)


@dataclass
class ConfigSubtasksGroupCondition:
    """
    Conditions to automatically add a group of subtasks.

    All populated condition fields must match to be true.
    """

    swimlane: Optional[TaskSwimlane]
    column: Optional[TaskColumn]
    category: Optional[TaskCategory]
    exclude_categories: bool = False

    allow_duplicate_subtasks: bool = False
    """Whether to add these subtasks even if they already exist."""

    @classmethod
    def from_dict(cls, d: dict):
        swimlane = parse_into(TaskSwimlane, d.get("swimlane"))

        column = parse_into(TaskColumn, d.get("column"))

        category = parse_into(TaskCategory, d.get("category"))

        return cls(
            swimlane=swimlane,
            column=column,
            category=category,
            exclude_categories=d.get("exclude_categories", False),
            allow_duplicate_subtasks=d.get("allow_duplicate_subtasks", False),
        )

    def has_category_predicate(self):
        return (self.category is not None and not self.exclude_categories) or (
            self.category is None and self.exclude_categories
        )

    def get_category_predicate(self) -> Optional[TaskCategory]:
        if self.exclude_categories:
            return None
        return self.category

    def test_category(self, category: Optional[TaskCategory]):
        """Determine if the category provided matches this condition."""
        if not self.has_category_predicate():
            return True
        return self.get_category_predicate() == category


@dataclass
class ConfigSubtaskGroup:
    """A collection of subtasks, often with a related trigger."""

    group_name: str
    """Arbitrary name."""

    subtasks: list[ConfigSubtaskEntry]
    """List of subtasks in the group."""

    prefix: Optional[str]
    """A name prefix to apply to all these subtasks."""

    condition: Optional[ConfigSubtasksGroupCondition] = None
    """Condition to evaluate to auto-create the subtasks in the group."""

    events: Optional[list[AutoActionEvents]] = None
    """Events to create an auto action for."""

    @classmethod
    def from_dict(cls, d: dict):
        """Contruct a group from a dict (generally from TOML)."""
        group_name = d["group_name"]
        subtasks = [ConfigSubtaskEntry.from_dict(subtask) for subtask in d["subtask"]]
        prefix = d.get("prefix")
        condition = None
        cond_dict = d.get("condition")
        if cond_dict:
            condition = ConfigSubtasksGroupCondition.from_dict(cond_dict)

        events = None
        events_raw = d.get("events")
        if events_raw:
            events = [AutoActionEvents[event] for event in events_raw]
        return cls(
            group_name=group_name,
            subtasks=subtasks,
            prefix=prefix,
            condition=condition,
            events=events,
        )


@dataclass
class ConfigAutoTag:
    tag: str
    condition: ConfigSubtasksGroupCondition

    events: Optional[list[AutoActionEvents]] = None
    """Events to create an auto action for."""

    @classmethod
    def from_dict(cls, d: dict):
        """Contruct an auto-tag entry from a dict (generally from TOML)."""
        tag = d["tag"]

        condition = ConfigSubtasksGroupCondition.from_dict(d["condition"])

        events = None
        events_raw = d.get("events")
        if events_raw:
            events = [AutoActionEvents[event] for event in events_raw]

        return cls(
            tag=tag,
            condition=condition,
            events=events,
        )


@dataclass
class ConfigData:
    auto_tags: list[ConfigAutoTag]
    subtask_groups: list[ConfigSubtaskGroup]


def get_config_data() -> ConfigData:
    """Load the integrated data file."""
    data = (
        importlib.resources.files("openxr_ops")
        .joinpath("kb_config.toml")
        .read_text(encoding="utf-8")
    )
    parsed = tomllib.loads(data)
    return ConfigData(
        auto_tags=[
            ConfigAutoTag.from_dict(tag_dict) for tag_dict in parsed.get("auto_tag", [])
        ],
        subtask_groups=[
            ConfigSubtaskGroup.from_dict(subtask_group)
            for subtask_group in parsed["subtask_group"]
        ],
    )


if __name__ == "__main__":
    subtasks = get_config_data()
    import pprint

    pprint.pprint(subtasks)
