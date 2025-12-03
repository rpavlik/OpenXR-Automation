#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


import asyncio
import datetime
import importlib
import importlib.resources
import logging
from typing import Awaitable

import kanboard
from gitlab.v4.objects import ProjectMergeRequest

from kb_ops_migrate import load_kb_ops
from openxr_ops.checklists import ChecklistData, ReleaseChecklistTemplate
from openxr_ops.ext_author_kind import CanonicalExtensionAuthorKind
from openxr_ops.gitlab import STATES_CLOSED_MERGED, OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardProject
from openxr_ops.kb_defaults import REAL_PROJ_NAME
from openxr_ops.kb_ops.collection import TaskCollection
from openxr_ops.kb_ops.config import get_config_data
from openxr_ops.kb_ops.gitlab import note_contains_sentinel, update_mr_desc
from openxr_ops.kb_ops.stages import TaskCategory, TaskColumn, TaskSwimlane
from openxr_ops.kb_ops.task import (
    OperationsTask,
    OperationsTaskCreationData,
    OperationsTaskFlags,
)
from openxr_ops.labels import GroupLabels, MainProjectLabels
from openxr_ops.vendors import VendorNames


def task_to_labels(task: OperationsTask):
    labels = {MainProjectLabels.EXTENSION}
    if task.flags and task.flags.single_vendor_extension:
        labels.add(GroupLabels.VENDOR_EXT)
        labels.add(GroupLabels.OUTSIDE_IPR_FRAMEWORK)

    if task.flags and task.flags.khr_extension:
        labels.add(GroupLabels.KHR_EXT)

    if task.category == TaskCategory.OUTSIDE_IPR_POLICY:
        labels.add(GroupLabels.OUTSIDE_IPR_FRAMEWORK)

    if task.column == TaskColumn.NEEDS_REVISIONS:
        labels.add(MainProjectLabels.NEEDS_AUTHOR_ACTION)

    return labels


def get_gitlab_comment(
    task_link: str,
    author_kind: CanonicalExtensionAuthorKind,
    category: TaskCategory | None,
    username: str,
):

    from jinja2 import Environment, PackageLoader, select_autoescape

    env = Environment(
        loader=PackageLoader("openxr_ops"),
        autoescape=select_autoescape(),
    )

    template = env.get_template("new_ext_comment.md")

    review_required = author_kind in (
        CanonicalExtensionAuthorKind.KHR,
        CanonicalExtensionAuthorKind.EXT,
    )

    return template.render(
        outside_ipr_policy=category == TaskCategory.OUTSIDE_IPR_POLICY,
        review_required=review_required,
        task_link=task_link,
        username=username,
    )


class ExtensionTaskCreator:
    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        vendor_names: VendorNames,
    ):
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        self.kb_project_name: str = REAL_PROJ_NAME
        self.vendor_names = vendor_names

        self.config = get_config_data()

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.mr_num_to_mr: dict[int, ProjectMergeRequest] = {}
        self.update_subtask_futures: list[Awaitable[None]] = []

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
        mr: ProjectMergeRequest,
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

        category: TaskCategory | None = None
        if author_kind == CanonicalExtensionAuthorKind.SINGLE_VENDOR:
            category = TaskCategory.OUTSIDE_IPR_POLICY
        elif (
            author_kind == CanonicalExtensionAuthorKind.EXT
            and GroupLabels.OUTSIDE_IPR_FRAMEWORK in mr.attributes["labels"]
        ):
            category = TaskCategory.OUTSIDE_IPR_POLICY

        return OperationsTaskCreationData(
            main_mr=mr_num,
            column=TaskColumn.IN_PREPARATION,
            swimlane=TaskSwimlane.DESIGN_REVIEW_PHASE,
            title=checklist_data.ext_names,
            description=str(template),
            flags=OperationsTaskFlags.from_author_kind(author_kind),
            category=category,
            date_started=datetime.datetime.fromisoformat(mr.attributes["created_at"]),
        )

    def handle_gitlab_mr_sync(self, mr_num: int) -> None:
        task = self.task_collection.get_task_by_mr(mr_num)
        if not task:
            raise RuntimeError("We should know this MR by now")

        mr: ProjectMergeRequest = self.mr_num_to_mr[mr_num]
        update_mr_desc(
            merge_request=mr,
            task_id=task.task_id,
            save_changes=True,
        )

        desired_labels = task_to_labels(task)
        labels = set(mr.attributes["labels"])

        missing_labels = desired_labels - labels
        if missing_labels:
            self.log.info(
                "%s : Adding missing labels %s",
                mr.attributes["web_url"],
                str(missing_labels),
            )
            mr.labels.extend(missing_labels)
            mr.save()

        flagged = [
            note_contains_sentinel(note) for note in mr.notes.list(iterator=True)
        ]
        if not any(flagged):
            # we need our initial comment.
            username = mr.attributes["author"]["username"]
            task_link = task.url

            assert task_link
            assert task.flags
            author_kind = task.flags.get_author_kind()

            message = get_gitlab_comment(
                username=username,
                author_kind=author_kind,
                task_link=task_link,
                category=task.category,
            )
            self.log.info("Posting comment on %s", mr.attributes["web_url"])
            mr.notes.create({"body": message})

    def prefetch(self, mr_num: int):
        self.mr_num_to_mr[mr_num] = self.oxr_gitlab.main_proj.mergerequests.get(mr_num)

    async def handle_mr_if_needed(
        self,
        mr_num: int,
        **kwargs,
    ) -> None:

        task = self.task_collection.get_task_by_mr(mr_num)
        if task is not None:
            self.log.warning("Already have a task for !%d: %s", mr_num, task.url)
            return

        mr: ProjectMergeRequest = self.mr_num_to_mr[mr_num]
        if mr.attributes["state"] in STATES_CLOSED_MERGED:
            self.log.warning("Closed/merged already: !%d", mr_num)
            return

        checklist_data = ChecklistData.lookup(
            self.oxr_gitlab.main_proj, mr_num, **kwargs
        )
        data = self.populate_data(checklist_data, mr_num=mr_num, mr=mr)

        new_task_id = await data.create_task(kb_project=self.kb_project)

        if new_task_id is not None:
            self.log.info(
                "Created new task ID %d: %s",
                new_task_id,
                data.title,
            )
            await self.task_collection.load_task_id(new_task_id)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_help = True
    parser.add_argument(
        "mr",
        type=int,
        nargs="+",
        help="MR number(s) to generate a kanboard task for",
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
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Higher log level",
        default=False,
    )

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr = OpenXRGitlab.create()

    log.info("Performing startup queries")
    vendor_names = VendorNames.from_git(oxr.main_proj)

    async def async_main():
        kwargs = {}
        if "extname" in args and args.extname:
            kwargs["ext_names"] = [args.extname]
        if "vendorid" in args and args.vendorid:
            kwargs["vendor_ids"] = args.vendorid

        creator = ExtensionTaskCreator(oxr_gitlab=oxr, vendor_names=vendor_names)
        await creator.prepare()

        # Serialized: Gitlab access
        log.info("Fetch specified MRs from Gitlab")
        for num in args.mr:
            creator.prefetch(num)

        log.info("Process Kanboard changes for MRs")
        for num in args.mr:
            await creator.handle_mr_if_needed(num, **kwargs)

        # Serialized: Gitlab access
        log.info("Update description and/or comment, if applicable, on MRs")
        for num in args.mr:
            creator.handle_gitlab_mr_sync(num)

    asyncio.run(async_main())
