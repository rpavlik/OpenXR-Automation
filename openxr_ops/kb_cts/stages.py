# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


from enum import Enum
from typing import Optional

from ..kanboard_helpers import KanboardProject


class TaskColumn(Enum):
    """Columns in the Kanboard CTS project"""

    BACKLOG = "Backlog"
    ON_HOLD = "On Hold"
    WORK_IN_PROGRESS = "Work in Progress"
    NEEDS_REVIEW = "Needs Review"
    DONE = "Done"

    def to_column_id(self, kb_project) -> Optional[int]:
        # depends on data cached by kb_project
        return kb_project.col_titles.get(self.value)

    @classmethod
    def from_column_id(cls, kb_project: KanboardProject, col_id: int) -> "TaskColumn":
        # depends on data cached by kb_project
        return cls(kb_project.col_ids_to_titles[col_id])


COLUMN_DESCRIPTIONS = {
    TaskColumn.BACKLOG: "Champion moves item to the next step, 'Awaiting Review', once all required prerequisites have been completed",
    TaskColumn.ON_HOLD: "Not currently in progress, see tags for reason.",
    TaskColumn.WORK_IN_PROGRESS: "Currently in development or revision.",
    TaskColumn.NEEDS_REVIEW: "Needs review from the group and/or contractor.",
    TaskColumn.DONE: "Complete and merged. Will be closed when shipped in a release.",
}


class TaskTags(Enum):
    """Tags in the Kanboard operations project."""

    BLOCKED_ON_SPEC = "Blocked on Spec"
    CONTRACTOR_REVIEWED = "Reviewed by Contractor"
    # INITIAL_SPEC_REVIEW_COMPLETE = "Initial Spec Review Complete"
    # SPEC_SUPPORT_REVIEW_COMMENTS_PENDING = "Spec Support Review Comments Pending"
    # API_FROZEN = "API Frozen"
    # EDITOR_REVIEW_REQUESTED = "Editor Review Requested"

    # KHR_EXTENSION = "KHR Extension"
    # MULTIVENDOR_EXTENSION = "Multivendor Extension"
    # SINGLE_VENDOR_EXTENSION = "Single Vendor Extension"


TAG_COLORS = {
    TaskTags.BLOCKED_ON_SPEC: "purple",
    TaskTags.CONTRACTOR_REVIEWED: "purple",
    # TaskTags.SPEC_SUPPORT_REVIEW_COMMENTS_PENDING: "cyan",
    # TaskTags.API_FROZEN: "blue",
    # # TaskTags.EDITOR_REVIEW_REQUESTED: "green",
    # TaskTags.KHR_EXTENSION: "grey",
    # TaskTags.MULTIVENDOR_EXTENSION: "grey",
    # TaskTags.SINGLE_VENDOR_EXTENSION: "grey",
}


class TaskCategory(Enum):
    CONTRACTOR = "CTS Contractor"

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


CATEGORY_COLORS = {TaskCategory.CONTRACTOR: "green"}


class TaskSwimlane(Enum):
    """Swimlane titles for the contractor vs others."""

    CTS_CONTRACTOR = "Approved CTS Contractor Work"
    OTHER = "Other Contributions"

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
    TaskSwimlane.CTS_CONTRACTOR: """Items here have been approved by the WG (or CTS subgroup) for work by the CTS contractor.""",
    TaskSwimlane.OTHER: """Issues raised but not approved for contractor work, or non-contractor MR contributions.""",
}
