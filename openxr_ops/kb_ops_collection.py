# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import itertools
import logging
import re
import tomllib
from functools import cached_property
from typing import Any, Dict, Iterable, List, Optional, Set, cast

import gitlab
import gitlab.v4.objects
import kanboard

from openxr_ops.kb_ops_task import OperationsTask

from .checklists import ReleaseChecklistFactory
from .extensions import ExtensionNameGuesser
from .kanboard_helpers import KanboardBoard
from .labels import MainProjectLabels
from .vendors import VendorNames


class TaskCollection:
    """The object containing the loaded data of the KanBoard ops project."""

    def __init__(
        self,
        kb_board: KanboardBoard,
        # proj: gitlab.v4.objects.Project,
        # vendor_names: VendorNames,
        # ops_proj: Optional[gitlab.v4.objects.Project] = None,
        # checklist_factory: Optional[ReleaseChecklistFactory] = None,
        # data: Optional[dict] = None,
    ):
        self.kb_board = kb_board
        """Object referencing an KanBoard project/board."""

        # self.proj: gitlab.v4.objects.Project = proj
        # """Main project"""

        # self.ops_proj: Optional[gitlab.v4.objects.Project] = ops_proj
        """Operations project containing (some) release checklists"""

        # self.checklist_factory: Optional[ReleaseChecklistFactory] = checklist_factory
        # self.vendor_names: VendorNames = vendor_names

        # self.issue_to_mr: Dict[str, int] = {}
        # self.mr_to_issue_object: Dict[int, gitlab.v4.objects.ProjectIssue] = {}
        # self.mr_to_issue: Dict[int, str] = {}
        # self.ignore_issues: Set[str] = set()
        # self.include_issues: List[int] = []
        self.mr_to_task_id: Dict[int, int] = dict()
        self.tasks: Dict[int, OperationsTask] = dict()

    async def _load_task(self, task_data: dict[str, Any]):
        task_id = int(task_data["id"])
        task = await OperationsTask.from_task_dict_with_more_data(
            self.kb_board, task_data
        )
        self.tasks[task_id] = task
        if task.main_mr is not None:
            self.mr_to_task_id[task.main_mr] = task_id

    async def load_board(self, only_open: bool = True):
        tasks = await self.kb_board.get_all_tasks(only_open=only_open)
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
