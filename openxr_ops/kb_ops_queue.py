# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
from typing import Optional
import kanboard
import logging

from dataclasses import dataclass
import gitlab
import gitlab.v4.objects

from .checklists import get_extension_names_for_mr

_log = logging.getLogger(__name__)

from .extensions import ExtensionNameGuesser
from .labels import ColumnName, GroupLabels, MainProjectLabels
from .vendors import VendorNames
from .kb_ops_stages import CardColumn, CardTags

COLUMN_CONVERSION = {
    ColumnName.INACTIVE: CardColumn.INACTIVE,
    ColumnName.INITIAL_DESIGN: CardColumn.INITIAL_DESIGN,
    ColumnName.AWAITING_DESIGN_REVIEW: CardColumn.AWAITING_DESIGN_REVIEW,
    # ColumnName.IN_DESIGN_REVIEW: CardColumn.IN_DESIGN_REVIEW,
    ColumnName.NEEDS_DESIGN_REVISION: CardColumn.NEEDS_DESIGN_REVISIONS,
    ColumnName.COMPOSITION_OR_ELABORATION: CardColumn.SPEC_ELABORATION,
    ColumnName.AWAITING_SPEC_REVIEW: CardColumn.AWAITING_SPEC_REVIEW,
    # ColumnName.IN_SPEC_REVIEW: CardColumn.IN_SPEC_REVIEW,
    ColumnName.NEEDS_SPEC_REVISION: CardColumn.NEEDS_SPEC_REVISIONS,
    ColumnName.FROZEN_NEEDS_IMPL_OR_CTS: CardColumn.PENDING_APPROVALS_AND_MERGE,
    ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION: CardColumn.PENDING_APPROVALS_AND_MERGE,
    ColumnName.NEEDS_OTHER: CardColumn.PENDING_APPROVALS_AND_MERGE,
    ColumnName.AWAITING_MERGE: CardColumn.PENDING_APPROVALS_AND_MERGE,
    ColumnName.RELEASE_PENDING: CardColumn.PENDING_APPROVALS_AND_MERGE,
}


@dataclass
class InitialCardData:
    """
    Data used to create an initial card.

    May be imported from GitLab or created fresh from the templates.
    """

    ext_names: list[str]
    vendor_id: str
    mr_num: int
    merge_request: gitlab.v4.objects.ProjectMergeRequest
    column: CardColumn = CardColumn.INITIAL_DESIGN

    # checklist_issue: Optional[gitlab.v4.objects.ProjectIssue] = None
    # checklist_issue_ref: Optional[str] = None

    # def make_issue_params(
    #     self, vendor_names: VendorNames, checklist_factory: ReleaseChecklistFactory
    # ):
    #     """Produce the dict used for the checklist template"""

    #     vendor_name = vendor_names.get_vendor_name(self.vendor_id)
    #     if not vendor_name:
    #         raise RuntimeError(f"Could not find vendor {self.vendor_id}")

    #     template = checklist_factory.make_checklist_by_vendor(self.vendor_id)

    #     if vendor_names.is_runtime_vendor(self.vendor_id):
    #         template.fill_in_vendor(vendor_name)

    #     template.fill_in_mr(self.mr_num)
    #     template.fill_in_champion(
    #         self.merge_request.author["name"], self.merge_request.author["username"]
    #     )
    #     if not self.ext_names:
    #         raise RuntimeError("ext names not detected")
    #     return {
    #         "title": f"{self.ext_names}",
    #         "description": str(template),
    #         "assignee_ids": [self.merge_request.author["id"]],
    #         "labels": [ColumnName.INITIAL_DESIGN.value] + get_labels(self.vendor_id),
    #     }

    @classmethod
    def lookup_mr(
        cls,
        proj: gitlab.v4.objects.Project,
        mr_num,
        **kwargs,
    ) -> "InitialCardData":
        """Create a ChecklistData based on a merge request number."""

        mr = proj.mergerequests.get(mr_num)

        ext_names: Optional[list[str]] = kwargs.get("ext_names")
        vendor_ids: Optional[list[str]] = kwargs.get("vendor_ids")
        if not ext_names or not vendor_ids:
            ext_name_data = list(get_extension_names_for_mr(mr))
            if not ext_names:
                ext_names = [x.non_experimental_name for x in ext_name_data]
            if not vendor_ids:
                vendor_ids = list({x.vendor_without_suffix for x in ext_name_data})


        if len(vendor_ids) != 1:
            _log.error(
                "wrong number of vendors for %s : %d : %s",
                ext_names,
                mr_num,
                str(vendor_ids),
            )
            raise RuntimeError(f"wrong number of vendors for {ext_names} : {mr_num}")
        vendor_id = list(vendor_ids)[0]
        return InitialCardData(
            ext_names=ext_names,
            vendor_id=vendor_id,
            mr_num=mr_num,
            merge_request=mr,
            column=CardColumn.INITIAL_DESIGN,
        )

    def add_mr_labels(self):
        changed = False
        for label in get_labels(self.vendor_id):
            if label not in self.merge_request.labels:
                self.merge_request.labels.append(label)
                changed = True
        self.merge_request.save()
        return changed

    def handle_mr(
        self,
        ops_proj: gitlab.v4.objects.Project,
        vendor_names: VendorNames,
        checklist_factory: ReleaseChecklistFactory,
    ):
        """Create a release checklist issue for an MR."""
        issue_params = self.make_issue_params(vendor_names, checklist_factory)
        issue = ops_proj.issues.create(issue_params)
        self.checklist_issue = cast(gitlab.v4.objects.ProjectIssue, issue)
        # issue_data  = typing.cast(gitlab.v4.objects.ProjectIssue,  issue_data)
        issue_link = issue.attributes["references"]["full"]
        self.checklist_issue_ref = issue_link
        _log.info("%d: %s %s", self.mr_num, issue_link, issue.attributes["web_url"])

        may_or_must = "may also want to"
        reviews_suffix = ""
        if self.vendor_id == "KHR":
            may_or_must = "must"
            reviews_suffix = " as well as discussion in weekly calls"

        message = (
            f"A release checklist for this extension has been opened at {issue_link}. "
            f"@{self.merge_request.author['username']} please update it to reflect the "
            "current state of this extension merge request and request review, "
            "if applicable.\n\n"
            "You should also update the [OpenXR Operations Workboard]"
            "(https://gitlab.khronos.org/openxr/openxr-operations/-/boards) "
            "according to the status of your extension: most likely this means "
            "moving it to 'NeedsReview' once you complete the self-review steps in "
            "the checklist.\n\n"
            "See the [OpenXR Operations Readme]("
            "https://gitlab.khronos.org/openxr/openxr-operations/-/blob/main/README.md"
            ") for the flowchart showing the extension workboard process.\n\n"
            f"You {may_or_must} request feedback from other WG members through our "
            f"chat at <https://chat.khronos.org>{reviews_suffix}."
        )
        self.merge_request.notes.create({"body": message})

        self.merge_request.description = (
            f"Release checklist: {issue_link}\n\n{self.merge_request.description}"
        )
        self.add_mr_labels()
