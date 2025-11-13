#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


import importlib
import importlib.resources
import logging
from typing import Optional

import gitlab
import gitlab.v4.objects
import kanboard

from kb_ops_migrate import load_kb_ops
from openxr_ops.checklists import (
    ChecklistData,
    ReleaseChecklistCollection,
    ReleaseChecklistFactory,
    ReleaseChecklistTemplate,
    get_extension_names_for_mr,
)
from openxr_ops.ext_author_kind import CanonicalExtensionAuthorKind
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardProject
from openxr_ops.kb_defaults import (
    REAL_HUMAN_BOARD_URL,
    REAL_HUMAN_OVERVIEW_URL,
    REAL_PROJ_NAME,
)
from openxr_ops.kb_ops_collection import TaskCollection
from openxr_ops.kb_ops_config import get_config_data
from openxr_ops.kb_ops_stages import TaskCategory, TaskColumn, TaskSwimlane
from openxr_ops.kb_ops_task import (
    OperationsTask,
    OperationsTaskCreationData,
    OperationsTaskFlags,
)
from openxr_ops.vendors import VendorNames


def get_gitlab_comment(
    data: OperationsTaskCreationData, task_link: str, username: str
) -> str:

    may_or_must = "may also want to"
    reviews_suffix = ""
    if data.category != TaskCategory.OUTSIDE_IPR_POLICY:
        may_or_must = "must also"
        reviews_suffix = " as well as discussion in weekly calls"

    return (
        f"A release tracking task for this extension has been opened at {task_link}. "
        f"@{username} please update it to reflect the "
        "current state of this extension merge request and request review, "
        "if applicable.\n\n"
        "You should also update the [OpenXR Extensions Workboard]"
        f"({REAL_HUMAN_BOARD_URL}) "
        "according to the status of your extension: most likely this means "
        "moving it to 'NeedsReview' once you complete the self-review steps in "
        "the checklist.\n\n"
        "See the [OpenXRExtensions Overview]("
        f"{REAL_HUMAN_OVERVIEW_URL}"
        ") for a flowchart showing the extension workboard process, "
        "and hover over the 'Info' icons on the board for specific details.\n\n"
        f"You {may_or_must} request feedback from other WG members through our "
        f"chat at <https://chat.khronos.org>{reviews_suffix}."
    )


class ExtensionTaskCreator:
    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        vendor_names: VendorNames,
        # gl_collection: ReleaseChecklistCollection,
    ):
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        # self.gl_collection: ReleaseChecklistCollection = gl_collection
        self.kb_project_name: str = REAL_PROJ_NAME
        # self.update_options: UpdateOptions = update_options
        self.vendor_names = vendor_names

        self.config = get_config_data()

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.mr_num_to_mr: dict[int, gitlab.v4.objects.ProjectMergeRequest] = {}
        self.update_subtask_futures: list = []

        # these are populated later in prepare
        self.kb_project: KanboardProject
        self.task_collection: TaskCollection
        self.kb: kanboard.Client

    async def prepare(self):
        self.kb_project, self.task_collection = await load_kb_ops(
            self.kb_project_name, only_open=False
        )
        self.kb = self.kb_project.kb

    def _get_template(
        self, author_kind: CanonicalExtensionAuthorKind
    ) -> ReleaseChecklistTemplate:
        if author_kind == CanonicalExtensionAuthorKind.KHR:
            fn = "khr_extension_desc.md"
        elif author_kind == CanonicalExtensionAuthorKind.EXT:
            fn = "ext_extension_desc.md"
        else:
            fn = "vendor_extension_desc.md"
        data = (
            importlib.resources.files("openxr_ops")
            .joinpath(f"templates/{fn}")
            .read_text(encoding="utf-8")
        )
        return ReleaseChecklistTemplate(data)

    def populate_data(
        self,
        checklist_data: ChecklistData,
        mr_num: int,
        mr: gitlab.v4.objects.ProjectMergeRequest,
    ) -> OperationsTaskCreationData:

        author_kind = self.vendor_names.canonicalize_and_categorize(
            checklist_data.vendor_id
        )

        canonical_vendor_tag = self.vendor_names.canonicalize_vendor_tag(
            checklist_data.vendor_id
        )

        vendor_name = self.vendor_names.get_vendor_name(checklist_data.vendor_id)
        if not vendor_name:
            raise RuntimeError(f"Could not find vendor {checklist_data.vendor_id}")

        template = self._get_template(author_kind)
        if self.vendor_names.is_runtime_vendor(canonical_vendor_tag):
            template.fill_in_vendor(vendor_name)

        template.fill_in_mr(mr_num)
        template.fill_in_champion(mr.author["name"], mr.author["username"])

        return OperationsTaskCreationData(
            main_mr=mr_num,
            column=TaskColumn.IN_PREPARATION,
            swimlane=TaskSwimlane.DESIGN_REVIEW_PHASE,
            title=checklist_data.ext_names,
            description=str(template),
            flags=OperationsTaskFlags.from_author_kind(author_kind),
        )

    async def handle_mr_if_needed(
        self,
        mr_num,
        # ext_name: Optional[str] = None,
        # vendor_ids: Optional[list[str]] = None,
        **kwargs,
    ):

        task = self.task_collection.get_task_by_mr(mr_num)
        if task is not None:
            self.log.warning("Already have a task for !%d: %s", mr_num, task.url)
            return

        mr = self.oxr_gitlab.main_proj.mergerequests.get(mr_num)
        checklist_data = ChecklistData.lookup(
            self.oxr_gitlab.main_proj, mr_num, **kwargs
        )
        data = self.populate_data(checklist_data, mr_num=mr_num, mr=mr)

        # if checklist_data.vendor_id == ("KHR")
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mr",
        type=int,
        nargs="+",
        help="MR number to generate a kanboard task for",
    )
    parser.add_argument(
        "--extname",
        type=str,
        help="Manually specify the extension name",
    )
    parser.add_argument(
        "-i",
        "--vendorid",
        type=str,
        action="append",
        help="Specify the vendor ID",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr = OpenXRGitlab.create()

    log.info("Performing startup queries")
    vendor_names = VendorNames.from_git(oxr.main_proj)
    # collection = ReleaseChecklistCollection(
    #     oxr.main_proj,
    #     oxr.operations_proj,
    #     checklist_factory=ReleaseChecklistFactory(oxr.operations_proj),
    #     vendor_names=,
    # )

    # collection.load_initial_data()
    async def async_main():
        kb_project, task_collection = await load_kb_ops(only_open=False)
        kwargs = {}
        if "extname" in args and args.extname:
            kwargs["ext_names"] = [args.extname]
        if "vendorid" in args and args.vendorid:
            kwargs["vendor_ids"] = args.vendorid
        for num in args.mr:
            collection.handle_mr_if_needed(num, **kwargs)
