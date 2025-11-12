# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


from enum import Enum
from typing import Optional

from .kanboard_helpers import KanboardProject

# class QueueStage(Enum):
#     PREPARATION = "In Preparation"
#     AWAITING_REVIEW = "Awaiting Review"
#     REVIEW_IN_PROGRESS = "Review In Progress"
#     NEEDS_REVISIONS = "Needs Revisions"
#     REVISIONS_IN_PROGRESS = "Revisions In Progress"


class TaskColumn(Enum):
    """Columns in the Kanboard operations project"""

    INACTIVE = "Inactive"  # not visible on dashboard
    IN_PREPARATION = "In Preparation"
    AWAITING_REVIEW = "Awaiting Review"
    IN_REVIEW = "In Review"
    NEEDS_REVISIONS = "Needs Revisions"
    REVISIONS_IN_PROGRESS = "Revisions in Progress"
    PENDING_APPROVALS_AND_MERGE = "Pending Approvals And Merge"

    def to_column_id(self, kb_project) -> Optional[int]:
        # depends on data cached by kb_project
        return kb_project.col_titles.get(self.value)

    @classmethod
    def from_column_id(cls, kb_project: KanboardProject, col_id: int) -> "TaskColumn":
        # depends on data cached by kb_project
        return cls(kb_project.col_ids_to_titles[col_id])


COLUMN_DESCRIPTIONS = {
    TaskColumn.INACTIVE: "Not currently being moved toward release.",
    TaskColumn.IN_PREPARATION: "Champion moves item to the next step, 'Awaiting Review'",
    TaskColumn.AWAITING_REVIEW: "Spec support team or spec editor will move to 'In Review' when applicable.",
    TaskColumn.IN_REVIEW: "Next step is either 'Needs Revisions' or 'Review Cycle Complete', moved by spec support or spec editor.",
    TaskColumn.NEEDS_REVISIONS: "Champion moves items from here to 'Revisions in Progress' when they start.",
    TaskColumn.REVISIONS_IN_PROGRESS: "When complete, next step is return to 'Awaiting Review'",
    TaskColumn.PENDING_APPROVALS_AND_MERGE: "This column can be skipped during the Design Review phase, extensions can move directly on to 'In Preparation' for the Spec Review phase. In the Spec Review phase, this column is for waiting on approvals, CTS, ratification, or other details.",
}


class TaskTags(Enum):
    """Tags in the Kanboard operations project."""

    INITIAL_DESIGN_REVIEW_COMPLETE = "Initial Design Review Complete"
    INITIAL_SPEC_REVIEW_COMPLETE = "Initial Spec Review Complete"
    SPEC_SUPPORT_REVIEW_COMMENTS_PENDING = "Spec Support Review Comments Pending"
    API_FROZEN = "API Frozen"
    EDITOR_REVIEW_REQUESTED = "Editor Review Requested"

    KHR_EXTENSION = "KHR Extension"
    MULTIVENDOR_EXTENSION = "Multivendor Extension"
    SINGLE_VENDOR_EXTENSION = "Single Vendor Extension"


TAG_COLORS = {
    TaskTags.INITIAL_DESIGN_REVIEW_COMPLETE: "purple",
    TaskTags.INITIAL_SPEC_REVIEW_COMPLETE: "purple",
    TaskTags.SPEC_SUPPORT_REVIEW_COMMENTS_PENDING: "cyan",
    TaskTags.API_FROZEN: "blue",
    # TaskTags.EDITOR_REVIEW_REQUESTED: "green",
    TaskTags.KHR_EXTENSION: "grey",
    TaskTags.MULTIVENDOR_EXTENSION: "grey",
    TaskTags.SINGLE_VENDOR_EXTENSION: "grey",
}


class TaskCategory(Enum):
    OUTSIDE_IPR_POLICY = "Not Subject to IPR Policy"

    def to_category_id(self, kb_project: KanboardProject) -> Optional[int]:
        # depends on data cached by kb_project
        return kb_project.category_title_to_id.get(self.value)

    @classmethod
    def optional_to_category_id(
        cls, kb_project: KanboardProject, category: Optional["TaskCategory"]
    ) -> Optional[int]:
        if category is None:
            return 0
        # depends on data cached by kb_project
        return category.to_category_id(kb_project)

    @classmethod
    def from_category_id(
        cls, kb_project: KanboardProject, category_id: int
    ) -> "TaskCategory":
        # depends on data cached by kb_project
        return cls(kb_project.category_ids_to_titles[category_id])

    @classmethod
    def from_category_id_maybe_none(
        cls, kb_project: KanboardProject, category_id: int
    ) -> Optional["TaskCategory"]:
        if category_id == 0:
            return None
        # depends on data cached by kb_project
        return cls(kb_project.category_ids_to_titles[category_id])


CATEGORY_COLORS = {TaskCategory.OUTSIDE_IPR_POLICY: "red"}

# No API?
CATEGORY_DESCRIPTIONS = {
    TaskCategory.OUTSIDE_IPR_POLICY: "Vendor and multi-vendor extensions, developed outside the Khronos IPR Policy. Not ratified before release, subject only to the approval of the contributors/champion and the spec editor."
    # In IPR Policy:
    # KHR and EXT extensions that will be ratified before release. Contributions made under the Khronos IPR policy.
}


class TaskSwimlane(Enum):
    """Swimlane titles for the review queue/phase."""

    DESIGN_REVIEW_PHASE = "Design Review phase"
    SPEC_REVIEW_PHASE = "Spec Review phase"

    def to_swimlane_id(self, kb_project: KanboardProject) -> Optional[int]:
        # depends on data cached by kb_project
        return kb_project.swimlane_titles.get(self.value)

    @classmethod
    def from_swimlane_id(
        cls, kb_project: KanboardProject, swimlane_id: int
    ) -> "TaskSwimlane":
        # depends on data cached by kb_project
        return cls(kb_project.swimlane_ids_to_titles[swimlane_id])


SWIMLANE_DESCRIPTIONS = {
    TaskSwimlane.DESIGN_REVIEW_PHASE: """An optional low-latency, high-level design review cycle, before ADOC completion.

Prerequisites to enter "Awaiting Review" with the intent of moving onward:

- XML changes must be complete (defining the API shape)
- ADOC must contain at least the boilerplate for all XML-defined entities, as well as member/parameter descriptions where it is not self explanatory.""",
    TaskSwimlane.SPEC_REVIEW_PHASE: """The main, final review cycle. Ideally all major issues were fixed in the design review phase, and only fine details of the spec language remain to find and resolve. Typically the API is considered frozen or nearly so.""",
}
