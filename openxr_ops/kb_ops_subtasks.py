#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

from dataclasses import dataclass

import importlib
import importlib.resources
import tomllib


@dataclass
class MigrationSubtaskEntry:

    task: str
    migration_prefix: str

    @classmethod
    def from_dict(cls, d: dict):
        task = d["task"]
        migration_prefix = d.get("migration_prefix", task)
        return cls(task=task, migration_prefix=migration_prefix)


@dataclass
class MigrationSubtasksGroup:
    category: str

    tasks: list[MigrationSubtaskEntry]

    @classmethod
    def from_dict(cls, d: dict):
        category = d["category"]
        tasks = [MigrationSubtaskEntry.from_dict(task) for task in d["task"]]
        return cls(category=category, tasks=tasks)


def get_all_subtasks() -> list[MigrationSubtasksGroup]:
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
