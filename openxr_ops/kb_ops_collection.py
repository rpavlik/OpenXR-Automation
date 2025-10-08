# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import itertools
import logging
import re
import tomllib
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Dict, Iterable, List, Optional, Set, cast

import gitlab
import gitlab.v4.objects
import kanboard

from .checklists import ReleaseChecklistFactory
from .extensions import ExtensionNameGuesser
from .kanboard_helpers import KanboardBoard
from .kb_ops_stages import CardColumn, CardSwimlane
from .labels import ColumnName, GroupLabels, MainProjectLabels
from .vendors import VendorNames

_MR_URL_RE = re.compile(
    r"https://gitlab.khronos.org/openxr/openxr/-/merge_requests/(?P<mrnum>[0-9]+)"
)


@dataclass
class OperationsCard:
    # card_id: int
    main_mr: Optional[int]
    column: CardColumn
    swimlane: CardSwimlane
    title: str
    description: str

    # api_frozen: bool
    # initial_design_review_complete: bool
    # initial_spec_review_complete: bool
    # spec_support_review_comments_pending: bool

    task_dict: Optional[dict] = None

    @classmethod
    def from_task_dict(
        cls, kb_board: KanboardBoard, task: dict[str, Any]
    ) -> "OperationsCard":
        """
        Interpret a task dictionary from e.g. get_all_tasks.

        Needs the kb_board to decode the column.
        """

        # card_id = int(task['id'])
        column_id = int(task["column_id"])
        column: CardColumn = CardColumn[kb_board.col_ids_to_titles[column_id]]
        title: str = task["title"]
        description: str = task["column_id"]
        swimlane_id = task["swimlane_id"]
        external_uri = task.get("external_uri")
        main_mr: Optional[int] = None
        # TODO how to handle multiple? Docs don't help
        if external_uri:
            m = _MR_URL_RE.match(external_uri)
            if m:
                main_mr = int(m.group("mrnum"))
        swimlane: CardSwimlane = CardSwimlane[swimlane_id]
        return cls(
            main_mr=main_mr,
            column=column,
            swimlane=swimlane,
            title=title,
            description=description,
            task_dict=task,
        )


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

    async def load_board(self, only_open: bool = True):
        tasks = await self.kb_board.get_all_tasks(only_open=only_open)
        for task in tasks:
            card_id = int(task["id"])
            card = OperationsCard.from_task_dict(self.kb_board, task)
            self.cards[card_id] = card
            if card.main_mr is not None:
                self.mr_to_card[card.main_mr] = card_id
                # self.mr_to_card[card.main_mr] = card_id
