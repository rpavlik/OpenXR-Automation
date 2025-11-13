# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
from typing import Any, Dict, Optional

from .kanboard_helpers import KanboardProject
from .kb_ops_task import OperationsTask


class TaskCollection:
    """The object containing the loaded data of the Kanboard ops project."""

    def __init__(
        self,
        kb_project: KanboardProject,
    ):
        self.kb_project = kb_project
        """Object referencing an Kanboard project."""

        # self.ignore_issues: Set[str] = set()
        # self.include_issues: List[int] = []
        self.mr_to_task_id: Dict[int, int] = dict()
        self.tasks: Dict[int, OperationsTask] = dict()

    def _update_task_maps(self, task: OperationsTask):
        self.tasks[task.task_id] = task

        if task.main_mr is not None:
            self.mr_to_task_id[task.main_mr] = task.task_id

    async def _load_task(self, task_data: dict[str, Any]):
        task = await OperationsTask.from_task_dict_with_more_data(
            self.kb_project, task_data
        )

        self._update_task_maps(task)

    async def load_task_id(self, task_id: int):
        """Load full data on only one task from Kanboard."""
        task = await OperationsTask.from_task_id(self.kb_project, task_id)
        self._update_task_maps(task)

    async def load_project(self, only_open: bool = True):
        """Load full data on all tasks from Kanboard."""
        tasks = await self.kb_project.get_all_tasks(only_open=only_open)
        await asyncio.gather(*[self._load_task(task) for task in tasks])

    def get_task_by_mr(self, mr_num: int) -> Optional[OperationsTask]:
        """Get task object associated with an OpenXR GitLab MR number, if any exists."""
        task_id = self.mr_to_task_id.get(mr_num)
        if task_id is not None:
            return self.get_task_by_id(task_id)
        return None

    def get_task_by_id(self, task_id: int) -> Optional[OperationsTask]:
        """Get task object from a task ID number."""
        return self.tasks.get(task_id)
