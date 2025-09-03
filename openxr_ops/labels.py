#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


from enum import Enum
from typing import Iterable, Optional


class GroupLabels:
    """Labels defined in the openxr GitLab group"""

    OUTSIDE_IPR_FRAMEWORK = "Outside IPR Framework"
    KHR_EXT = "KHR_Extension"
    VENDOR_EXT = "Vendor_Extension"


class MainProjectLabels:
    """Labels defined in the openxr/openxr GitLab project"""

    EXTENSION = "Extension"
    CONFORMANCE_IMPLEMENTATION = "CTS:conformance"
    CONFORMANCE_IN_THE_WILD = "CTS:in-the-wild"
    CONFORMANCE_QUESTION = "CTS:question"
    NEEDS_AUTHOR_ACTION = "Needs Author Action"
    CONTRACTOR_APPROVED = "Contractor:Approved"


class OpsProjectLabels:
    """Labels defined in the openxr/openxr-operations GitLab project"""

    INITIAL_REVIEW_COMPLETE = "initial-review-complete"
    INITIAL_DESIGN_REVIEW_COMPLETE = "initial-design-review-complete"
    CHAMPION_APPROVED = "champion-approved"

    UNCHANGEABLE = "API Shipped publicly (unchangable)"


class ColumnName(Enum):
    """Board columns and their associated labels, from the Operations project."""

    INACTIVE = "status:Inactive"
    INITIAL_DESIGN = "status:InitialDesign"
    AWAITING_DESIGN_REVIEW = "status:AwaitingDesignReview"
    NEEDS_DESIGN_REVISION = "status:NeedsDesignRevision"

    COMPOSITION_OR_ELABORATION = "status:CompositionOrElaboration"
    AWAITING_SPEC_REVIEW = "status:AwaitingSpecReview"
    NEEDS_SPEC_REVISION = "status:NeedsSpecRevision"
    FROZEN_NEEDS_IMPL_OR_CTS = "status:FrozenNeedsImplOrCTS"
    NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION = (
        "status:NeedsChampionApprovalOrRatification"
    )
    NEEDS_OTHER = "status:NeedsOther"
    AWAITING_MERGE = "status:AwaitingMerge"
    RELEASE_PENDING = "status:ReleasePending"

    @classmethod
    def from_labels(cls, labels: Iterable[str]) -> Optional["ColumnName"]:
        result = None
        label_set = set(labels)
        for column in cls:
            if column.value in label_set:
                # only keep the "highest"
                result = column
        return result

    def compute_new_labels(self, labels: Iterable[str]) -> set[str]:
        column_labels = {x.value for x in ColumnName}

        # Remove all column labels except the one we want.
        new_labels = set(x for x in labels if x == self.value or x not in column_labels)

        # Add the one we want if it wasn't already there
        new_labels.update([self.value])

        if (
            self == ColumnName.NEEDS_SPEC_REVISION
            and OpsProjectLabels.INITIAL_REVIEW_COMPLETE not in new_labels
        ):
            # If it's in needs-revision, that means it got reviewed.
            new_labels.update([OpsProjectLabels.INITIAL_REVIEW_COMPLETE])

        if (
            self == ColumnName.NEEDS_DESIGN_REVISION
            and OpsProjectLabels.INITIAL_DESIGN_REVIEW_COMPLETE not in new_labels
        ):
            # If it's in needs-design-revision, that means it got reviewed.
            new_labels.update([OpsProjectLabels.INITIAL_DESIGN_REVIEW_COMPLETE])

        return new_labels
