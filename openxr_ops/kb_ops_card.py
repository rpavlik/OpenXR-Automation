import re
from openxr_ops.kanboard_helpers import KanboardBoard
from openxr_ops.kb_ops_stages import CardColumn, CardSwimlane


from dataclasses import dataclass
from typing import Any, Optional

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
class OperationsCard:
    card_id: int
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

        Needs the kb_board to decode the column and swimlane.

        Unable to populate the main MR or any more advanced properties.
        """

        card_id = int(task['id'])
        column_id = int(task["column_id"])
        column_title = kb_board.col_ids_to_titles[column_id]
        column: CardColumn = CardColumn(column_title)
        title: str = task["title"]
        description: str = task["description"]
        # external_uri = task.get("external_uri")
        main_mr: Optional[int] = None
        # TODO how to handle multiple? Docs don't help
        # This appears to always be null and we use a different API for it.
        # if external_uri:
        #     m = _MR_URL_RE.match(external_uri)
        #     if m:
        #         main_mr = int(m.group("mrnum"))
        swimlane_id = task["swimlane_id"]
        swimlane_title = kb_board.swimlane_ids_to_titles[swimlane_id]
        swimlane: CardSwimlane = CardSwimlane(swimlane_title)
        return cls(
            card_id=card_id,
            main_mr=main_mr,
            column=column,
            swimlane=swimlane,
            title=title,
            description=description,
            task_dict=task,
        )

    @classmethod
    async def from_task_dict_with_more_data(
        cls, kb_board: KanboardBoard, task: dict[str, Any]
    ) -> "OperationsCard":
        ret = cls.from_task_dict(kb_board, task)
        card_id = int(task["id"])
        ext_links_future = kb_board.kb.get_all_external_task_links_async(
            task_id=card_id
        )
        # tags_future = kb_board.kb.get_task_tags_async(
        #     project_id=kb_board.project_id, task_id=card_id
        # )

        for ext_link in await ext_links_future:
            main_mr = extract_mr_number(ext_link['url'])
            if main_mr is not None:
                ret.main_mr = main_mr
                break

        # TODO handle tags
        return ret