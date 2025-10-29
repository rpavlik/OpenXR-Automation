# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


from enum import Enum
from typing import Iterable, Optional

from .kanboard_helpers import KanboardBoard

# class QueueStage(Enum):
#     PREPARATION = "In Preparation"
#     AWAITING_REVIEW = "Awaiting Review"
#     REVIEW_IN_PROGRESS = "Review In Progress"
#     NEEDS_REVISIONS = "Needs Revisions"
#     REVISIONS_IN_PROGRESS = "Revisions In Progress"


class CardColumn(Enum):
    """Columns in the KanBoard operations project"""

    INACTIVE = "Inactive"  # not visible on dashboard
    IN_PREPARATION = "In Preparation"
    AWAITING_REVIEW = "Awaiting Review"
    IN_REVIEW = "In Review"
    NEEDS_REVISIONS = "Needs Revisions"
    REVISIONS_IN_PROGRESS = "Revisions in Progress"
    PENDING_APPROVALS_AND_MERGE = "Pending Approvals And Merge"

    def to_column_id(self, kb_board) -> Optional[int]:
        # depends on data cached by kb_board
        return kb_board.col_titles.get(self.value)

    @classmethod
    def from_column_id(cls, kb_board: KanboardBoard, col_id: int) -> "CardColumn":
        # depends on data cached by kb_board
        return cls(kb_board.col_ids_to_titles[col_id])


COLUMN_DESCRIPTIONS = {
    CardColumn.INACTIVE: "Not currently being moved toward release.",
    CardColumn.IN_PREPARATION: "Champion moves item to the next step, 'Awaiting Review'",
    CardColumn.AWAITING_REVIEW: "Spec support team or spec editor will move to 'In Review' when applicable.",
    CardColumn.IN_REVIEW: "Next step is either 'Needs Revisions' or 'Review Cycle Complete', moved by spec support or spec editor.",
    CardColumn.NEEDS_REVISIONS: "Champion moves items from here to 'Revisions in Progress' when they start.",
    CardColumn.REVISIONS_IN_PROGRESS: "When complete, next step is return to 'Awaiting Review'",
    CardColumn.PENDING_APPROVALS_AND_MERGE: "This column can be skipped during the Design Review phase, extensions can move directly on to 'In Preparation' for the Spec Review phase. In the Spec Review phase, this column is for waiting on approvals, CTS, ratification, or other details.",
}


class CardTags(Enum):
    """Tags in the KanBoard operations project."""

    INITIAL_DESIGN_REVIEW_COMPLETE = "Initial Design Review Complete"
    INITIAL_SPEC_REVIEW_COMPLETE = "Initial Spec Review Complete"
    SPEC_SUPPORT_REVIEW_COMMENTS_PENDING = "Spec Support Review Comments Pending"
    API_FROZEN = "API Frozen"


TAG_COLORS = {
    CardTags.INITIAL_DESIGN_REVIEW_COMPLETE: "purple",
    CardTags.INITIAL_SPEC_REVIEW_COMPLETE: "purple",
    CardTags.SPEC_SUPPORT_REVIEW_COMMENTS_PENDING: "cyan",
    CardTags.API_FROZEN: "blue",
}


class CardCategory(Enum):
    OUTSIDE_IPR_POLICY = "Not Subject to IPR Policy"

    def to_category_id(self, kb_board: KanboardBoard) -> Optional[int]:
        # depends on data cached by kb_board
        return kb_board.category_title_to_id.get(self.value)

    @classmethod
    def from_category_id(
        cls, kb_board: KanboardBoard, category_id: int
    ) -> "CardCategory":
        # depends on data cached by kb_board
        return cls(kb_board.category_ids_to_titles[category_id])


CATEGORY_COLORS = {CardCategory.OUTSIDE_IPR_POLICY: "red"}

# No API?
CATEGORY_DESCRIPTIONS = {
    CardCategory.OUTSIDE_IPR_POLICY: "Vendor and multi-vendor extensions, developed outside the Khronos IPR Policy. Not ratified before release, subject only to the approval of the contributors/champion and the spec editor."
    # In IPR Policy:
    # KHR and EXT extensions that will be ratified before release. Contributions made under the Khronos IPR policy.
}


class CardSwimlane(Enum):
    """Swimlane titles for the review queue/phase."""

    DESIGN_REVIEW_PHASE = "Design Review phase"
    SPEC_REVIEW_PHASE = "Spec Review phase"

    def to_swimlane_id(self, kb_board: KanboardBoard) -> Optional[int]:
        # depends on data cached by kb_board
        return kb_board.swimlane_titles.get(self.value)

    @classmethod
    def from_swimlane_id(
        cls, kb_board: KanboardBoard, swimlane_id: int
    ) -> "CardSwimlane":
        # depends on data cached by kb_board
        return cls(kb_board.swimlane_ids_to_titles[swimlane_id])


SWIMLANE_DESCRIPTIONS = {
    CardSwimlane.DESIGN_REVIEW_PHASE: """An optional low-latency, high-level design review cycle, before ADOC completion.

Prerequisites to enter "Awaiting Review" with the intent of moving onward:

- XML changes must be complete (defining the API shape)
- ADOC must contain at least the boilerplate for all XML-defined entities, as well as member/parameter descriptions where it is not self explanatory.""",
    CardSwimlane.SPEC_REVIEW_PHASE: """The main, final review cycle. Ideally all major issues were fixed in the design review phase, and only fine details of the spec language remain to find and resolve. Typically the API is considered frozen or nearly so.""",
}


class CardDefnOfDoneKeys(Enum):
    """
    Titles for 'Definition of Done' entries.

    Not sure we can add these programmatically, may need to be subtasks instead.
    """

    # These two get cleared on pushes.
    SPEC_EDITOR_APPROVAL = "Spec Editor Approval"
    CHAMPION_APPROVAL = "Champion Approval"

    # These two only for "in IPR policy"
    WG_VOTE = "Working Group Vote to Submit for Ratification"
    BOARD_RATIFICATION = "Board Ratification"
