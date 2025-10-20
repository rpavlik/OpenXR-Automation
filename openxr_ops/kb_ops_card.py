import datetime
import re
from dataclasses import dataclass
from typing import Any, Optional

import kanboard

from .kanboard_helpers import KanboardBoard
from .kb_ops_stages import CardCategory, CardColumn, CardSwimlane, CardTags

_MR_URL_BASE = "https://gitlab.khronos.org/openxr/openxr/-/merge_requests/"

_MR_URL_RE = re.compile(_MR_URL_BASE + r"(?P<mrnum>[0-9]+)")


def extract_mr_number(uri: Optional[str]) -> Optional[int]:
    """Pull out the merge request number from a URI."""
    if not uri:
        return None

    m = _MR_URL_RE.match(uri)
    if not m:
        return None

    return int(m.group("mrnum"))


@dataclass
class OperationsCardFlags:
    """Booleans that come from presence/absence of tags."""

    api_frozen: bool
    initial_design_review_complete: bool
    initial_spec_review_complete: bool
    spec_support_review_comments_pending: bool

    @classmethod
    def from_task_tags_result(cls, task_tags: dict[str, str]) -> "OperationsCardFlags":
        tags = set(task_tags.values())

        return cls(
            api_frozen=(CardTags.API_FROZEN.value in tags),
            initial_design_review_complete=(
                CardTags.INITIAL_DESIGN_REVIEW_COMPLETE.value in tags
            ),
            initial_spec_review_complete=(
                CardTags.INITIAL_SPEC_REVIEW_COMPLETE.value in tags
            ),
            spec_support_review_comments_pending=(
                CardTags.SPEC_SUPPORT_REVIEW_COMMENTS_PENDING.value in tags
            ),
        )

    @classmethod
    async def fetch_tags_list(
        cls, kb: kanboard.Client, task_id: int
    ) -> "OperationsCardFlags":
        tags_future = kb.get_task_tags_async(task_id=task_id)
        return cls.from_task_tags_result(await tags_future)

    def to_enum_list(self) -> list[CardTags]:
        ret = []
        if self.api_frozen:
            ret.append(CardTags.API_FROZEN)
        if self.initial_design_review_complete:
            ret.append(CardTags.INITIAL_DESIGN_REVIEW_COMPLETE)
        if self.initial_spec_review_complete:
            ret.append(CardTags.INITIAL_SPEC_REVIEW_COMPLETE)
        if self.spec_support_review_comments_pending:
            ret.append(CardTags.SPEC_SUPPORT_REVIEW_COMMENTS_PENDING)
        return ret

    def to_string_list(self) -> list[str]:
        return [tag.value for tag in self.to_enum_list()]


@dataclass
class OperationsCardBase:
    card_id: int
    column: CardColumn
    swimlane: CardSwimlane
    title: str
    description: str
    task_dict: Optional[dict]

    @classmethod
    def from_task_dict(
        cls, kb_board: KanboardBoard, task: dict[str, Any]
    ) -> "OperationsCardBase":
        """
        Interpret a task dictionary from e.g. get_all_tasks.

        Needs the kb_board to decode the column and swimlane.

        Unable to populate the main MR or any more advanced properties.
        """

        card_id = int(task["id"])
        column_id = int(task["column_id"])
        column: CardColumn = CardColumn.from_column_id(kb_board, col_id=column_id)
        title: str = task["title"]
        description: str = task["description"]

        swimlane_id = int(task["swimlane_id"])
        swimlane: CardSwimlane = CardSwimlane.from_swimlane_id(
            kb_board, swimlane_id=int(swimlane_id)
        )
        return cls(
            card_id=card_id,
            column=column,
            swimlane=swimlane,
            title=title,
            description=description,
            task_dict=task,
        )


@dataclass
class OperationsCard(OperationsCardBase):
    """Like OperationsCardBase but this requires additional queries"""

    main_mr: Optional[int]

    ext_links_list: list[dict[str, Any]]

    flags: Optional[OperationsCardFlags]

    tags_dict: dict[str, Any]

    @classmethod
    async def from_base_with_more_data(
        cls, base: OperationsCardBase, kb: kanboard.Client
    ) -> "OperationsCard":
        ext_links_future = kb.get_all_external_task_links_async(task_id=base.card_id)
        tags_future = kb.get_task_tags_async(task_id=base.card_id)

        main_mr: Optional[int] = None
        ext_links = await ext_links_future
        for ext_link in ext_links:
            main_mr = extract_mr_number(ext_link["url"])
            if main_mr is not None:
                break

        tags = await tags_future
        flags = OperationsCardFlags.from_task_tags_result(tags)

        return cls(
            card_id=base.card_id,
            column=base.column,
            swimlane=base.swimlane,
            title=base.title,
            description=base.description,
            task_dict=base.task_dict,
            main_mr=main_mr,
            ext_links_list=ext_links,
            flags=flags,
            tags_dict=tags,
        )

    @classmethod
    async def from_task_dict_with_more_data(
        cls, kb_board: KanboardBoard, task: dict[str, Any]
    ) -> "OperationsCard":
        base = OperationsCardBase.from_task_dict(kb_board, task)
        return await cls.from_base_with_more_data(base=base, kb=kb_board.kb)

    @classmethod
    async def from_task_id(
        cls, kb_board: KanboardBoard, task_id: int
    ) -> "OperationsCard":
        task_dict = await kb_board.kb.get_task(task_id=task_id)
        return await cls.from_task_dict_with_more_data(
            task=task_dict, kb_board=kb_board
        )


@dataclass
class OperationsCardCreationData:
    main_mr: int
    column: CardColumn
    swimlane: CardSwimlane
    title: str
    description: str

    flags: Optional[OperationsCardFlags]
    issue_url: Optional[str] = None

    category: Optional[CardCategory] = None

    date_started: Optional[datetime.datetime] = None

    async def create_card(self, kb_board: KanboardBoard) -> Optional[int]:
        swimlane_id = self.swimlane.to_swimlane_id(kb_board)
        if swimlane_id is None:
            return None
        column_id = self.column.to_column_id(kb_board)
        if column_id is None:
            return None
        extras = dict()
        if self.category is not None:
            category_id = self.category.to_category_id(kb_board)
            if category_id is not None:
                extras["category_id"] = category_id

        if self.flags is not None:
            extras["tags"] = self.flags.to_string_list()

        if self.date_started is not None:
            extras["date_started"] = self.date_started.strftime("%Y-%m-%d %H:%M")

        mr_url = f"{_MR_URL_BASE}{self.main_mr}"
        kb = kb_board.kb

        task_id = await kb.create_task_async(
            title=self.title,
            project_id=kb_board.project_id,
            description=self.description,
            swimlane_id=swimlane_id,
            column_id=column_id,
            # gl_url=mr_url,
            **extras,
        )

        await kb.create_external_task_link_async(
            task_id=task_id,
            url=mr_url,
            type="weblink",
            dependency="related",
            title=f"Merge Request !{self.main_mr}",
        )

        if self.issue_url is not None:
            await kb.create_external_task_link_async(
                task_id=task_id,
                url=self.issue_url,
                type="weblink",
                dependency="related",
                title=f"Original Operations Issue",
            )

        return task_id
