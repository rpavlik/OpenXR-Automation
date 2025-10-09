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

from openxr_ops.kb_ops_card import OperationsCard

from .checklists import ReleaseChecklistFactory
from .extensions import ExtensionNameGuesser
from .kanboard_helpers import KanboardBoard
from .labels import MainProjectLabels
from .vendors import VendorNames

class CardCollection:
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
        self.mr_to_card: Dict[int, int] = dict()
        # self.card_to_mr: Dict[int, int] = dict()
        self.cards: Dict[int, OperationsCard] = dict()

    async def _load_card(self, task: dict[str, Any]):
        card_id = int(task["id"])
        card = await OperationsCard.from_task_dict_with_more_data(self.kb_board, task)
        self.cards[card_id] = card
        if card.main_mr is not None:
            self.mr_to_card[card.main_mr] = card_id

    async def load_board(self, only_open: bool = True):
        tasks = await self.kb_board.get_all_tasks(only_open=only_open)
        await asyncio.gather(*[self._load_card(task) for task in tasks])
        # for task in tasks:
        # self.mr_to_card[card.main_mr] = card_id

    def get_card_by_mr(self, mr_num) -> Optional[OperationsCard]:
        card_id = self.mr_to_card.get(mr_num)
        if card_id is not None:
            return self.get_card_by_id(card_id)
        return None

    def get_card_by_id(self, card_id) -> Optional[OperationsCard]:
        return self.cards.get(card_id)
