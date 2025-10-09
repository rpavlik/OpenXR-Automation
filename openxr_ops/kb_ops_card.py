import re
from dataclasses import dataclass
from typing import Any, Optional

import kanboard

from openxr_ops.kanboard_helpers import KanboardBoard
from openxr_ops.kb_ops_stages import CardColumn, CardSwimlane, CardTags

_MR_URL_RE = re.compile(
    r"https://gitlab.khronos.org/openxr/openxr/-/merge_requests/(?P<mrnum>[0-9]+)"
)


def extract_mr_number(uri: Optional[str]) -> Optional[int]:
    """Pull out the merge request number from a URI."""
    if not uri:
        return None

    m = _MR_URL_RE.match(uri)
    if not m:
        return None

    return int(m.group("mrnum"))


@dataclass
class OperationsCardCreationData:
    main_mr: int
    column: CardColumn
    swimlane: CardSwimlane
    title: str
    description: str


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
        column_title = kb_board.col_ids_to_titles[column_id]
        column: CardColumn = CardColumn(column_title)
        title: str = task["title"]
        description: str = task["description"]

        swimlane_id = task["swimlane_id"]
        swimlane_title = kb_board.swimlane_ids_to_titles[swimlane_id]
        swimlane: CardSwimlane = CardSwimlane(swimlane_title)
        return cls(
            card_id=card_id,
            column=column,
            swimlane=swimlane,
            title=title,
            description=description,
            task_dict=task,
        )


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


@dataclass
class OperationsCard(OperationsCardBase):
    """Like OperationsCardBase but this requires additional queries"""

    # card_id: int
    # column: CardColumn
    # swimlane: CardSwimlane
    # title: str
    # description: str

    main_mr: Optional[int]

    flags: Optional[OperationsCardFlags]

    # api_frozen: bool
    # initial_design_review_complete: bool
    # initial_spec_review_complete: bool
    # spec_support_review_comments_pending: bool

    # task_dict: Optional[dict] = None

    @classmethod
    async def from_task_dict_with_more_data(
        cls, kb_board: KanboardBoard, task: dict[str, Any]
    ) -> "OperationsCard":
        base = OperationsCardBase.from_task_dict(kb_board, task)
        ext_links_future = kb_board.kb.get_all_external_task_links_async(
            task_id=base.card_id
        )
        tags_future = kb_board.kb.get_task_tags_async(task_id=base.card_id)

        main_mr: Optional[int] = None
        for ext_link in await ext_links_future:
            main_mr = extract_mr_number(ext_link["url"])
            if main_mr is not None:
                break

        flags = OperationsCardFlags.from_task_tags_result(await tags_future)
        return cls(
            card_id=base.card_id,
            column=base.column,
            swimlane=base.swimlane,
            title=base.title,
            description=base.description,
            task_dict=base.task_dict,
            main_mr=main_mr,
            flags=flags,
        )
