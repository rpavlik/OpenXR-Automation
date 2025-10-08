# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


from enum import Enum
from typing import Iterable, Optional


# class QueueStage(Enum):
#     PREPARATION = "In Preparation"
#     AWAITING_REVIEW = "Awaiting Review"
#     REVIEW_IN_PROGRESS = "Review In Progress"
#     NEEDS_REVISIONS = "Needs Revisions"
#     REVISIONS_IN_PROGRESS = "Revisions In Progress"


class CardColumn(Enum):
    """Columns in the KanBoard project"""

    INACTIVE = "Inactive"
    INITIAL_DESIGN = "Initial Design"
    AWAITING_DESIGN_REVIEW = "Awaiting Design Review"
    IN_DESIGN_REVIEW = "In Design Review"
    NEEDS_DESIGN_REVISIONS = "Needs Design Revisions"
    SPEC_ELABORATION = "Spec Elaboration"
    AWAITING_SPEC_REVIEW = "Awaiting Spec Review"
    IN_SPEC_REVIEW = "In Spec Review"
    NEEDS_SPEC_REVISIONS = "Needs Spec Revisions"
    PENDING_APPROVALS_AND_MERGE = "Pending Approvals And Merge"

    # @classmethod
    # def all_from_labels(cls, labels: Iterable[str]) -> Iterable["CardColumn"]:
    #     """Get all columns"""
    #     label_set = set(labels)
    #     column_set = {column for column in cls if column.value in label_set}
    #     return column_set

    # @classmethod
    # def from_labels(cls, labels: Iterable[str]) -> Optional["CardColumn"]:
    #     result = None
    #     label_set = set(labels)
    #     for column in cls:
    #         if column.value in label_set:
    #             # only keep the "highest"
    #             result = column
    #     return result


class CardTags(Enum):
    """Tags in the KanBoard project."""

    INITIAL_DESIGN_REVIEW_COMPLETE = "InitialDesignReviewComplete"
    INITIAL_SPEC_REVIEW_COMPLETE = "InitialSpecReviewComplete"
    SPEC_SUPPORT_REVIEW_COMMENTS_PENDING = "SpecSupportReviewCommentsPending"
    API_FROZEN = "ApiFrozen"

class CardSwimlane(Enum):
    """Swimlane IDs for the relationship to the Khronos IPR policy."""
    SUBJECT_TO_IPR_POLICY = 0
    OUTSIDE_IPR_POLICY = 1