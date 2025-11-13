# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
from .kb_ops_stages import TaskColumn, TaskSwimlane
from .labels import ColumnName

COLUMN_CONVERSION = {
    ColumnName.INACTIVE: TaskColumn.INACTIVE,
    #
    # Design review stages
    ColumnName.INITIAL_DESIGN: TaskColumn.IN_PREPARATION,
    ColumnName.AWAITING_DESIGN_REVIEW: TaskColumn.AWAITING_REVIEW,
    ColumnName.NEEDS_DESIGN_REVISION: TaskColumn.NEEDS_REVISIONS,
    #
    # Spec review steps
    ColumnName.COMPOSITION_OR_ELABORATION: TaskColumn.IN_PREPARATION,
    ColumnName.AWAITING_SPEC_REVIEW: TaskColumn.AWAITING_REVIEW,
    ColumnName.NEEDS_SPEC_REVISION: TaskColumn.NEEDS_REVISIONS,
    ColumnName.FROZEN_NEEDS_IMPL_OR_CTS: TaskColumn.PENDING_APPROVALS_AND_MERGE,
    ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION: TaskColumn.PENDING_APPROVALS_AND_MERGE,
    ColumnName.NEEDS_OTHER: TaskColumn.PENDING_APPROVALS_AND_MERGE,
    ColumnName.AWAITING_MERGE: TaskColumn.PENDING_APPROVALS_AND_MERGE,
    ColumnName.RELEASE_PENDING: TaskColumn.PENDING_APPROVALS_AND_MERGE,
}
COLUMN_TO_SWIMLANE = {
    #
    # Assume these all have some design done or skipped.
    ColumnName.INACTIVE: TaskSwimlane.SPEC_REVIEW_PHASE,
    #
    # Design review stages
    ColumnName.INITIAL_DESIGN: TaskSwimlane.DESIGN_REVIEW_PHASE,
    ColumnName.AWAITING_DESIGN_REVIEW: TaskSwimlane.DESIGN_REVIEW_PHASE,
    ColumnName.NEEDS_DESIGN_REVISION: TaskSwimlane.DESIGN_REVIEW_PHASE,
    #
    # Spec review steps
    ColumnName.COMPOSITION_OR_ELABORATION: TaskSwimlane.SPEC_REVIEW_PHASE,
    ColumnName.AWAITING_SPEC_REVIEW: TaskSwimlane.SPEC_REVIEW_PHASE,
    ColumnName.NEEDS_SPEC_REVISION: TaskSwimlane.SPEC_REVIEW_PHASE,
    ColumnName.FROZEN_NEEDS_IMPL_OR_CTS: TaskSwimlane.SPEC_REVIEW_PHASE,
    ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION: TaskSwimlane.SPEC_REVIEW_PHASE,
    ColumnName.NEEDS_OTHER: TaskSwimlane.SPEC_REVIEW_PHASE,
    ColumnName.AWAITING_MERGE: TaskSwimlane.SPEC_REVIEW_PHASE,
    ColumnName.RELEASE_PENDING: TaskSwimlane.SPEC_REVIEW_PHASE,
}
