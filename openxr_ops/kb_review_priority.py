#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import datetime
import logging
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import List, Optional, Union

import gitlab
import gitlab.v4.objects

from .checklists import ColumnName, ReleaseChecklistCollection
from .custom_sort import SORTERS, BasicDesignReviewSort, BasicSpecReviewSort, SorterBase
from .extensions import compute_vendor_name_and_tag
from .gitlab import OpenXRGitlab
from .kanboard_helpers import KanboardProject
from .kb_defaults import connect_and_get_project
from .kb_ops_collection import TaskCollection
from .kb_ops_stages import TaskCategory, TaskColumn, TaskSwimlane
from .kb_ops_task import OperationsTask, OperationsTaskBase
from .labels import OpsProjectLabels
from .priority_results import (
    NOW,
    PriorityResults,
    ReleaseChecklistIssue,
    ReleaseChecklistMRData,
    apply_offsets,
)
from .review_priority import ReviewPriorityConfig
from .vendors import VendorNames


@dataclass
class KBChecklistItem(ReleaseChecklistMRData):
    task: OperationsTask

    mr: gitlab.v4.objects.ProjectMergeRequest

    vendor_name: str | None = None
    vendor_tag: str | None = None

    offset: int = 0
    """Corrective latency offset"""

    @property
    def initial_design_review_complete(self) -> bool:
        if not self.task.flags:
            raise RuntimeError("Somehow did not load flags for this one?")
        return self.task.flags.initial_design_review_complete

    @property
    def initial_spec_review_complete(self) -> bool:
        if not self.task.flags:
            raise RuntimeError("Somehow did not load flags for this one?")
        return self.task.flags.initial_spec_review_complete

    @property
    def editor_review_requested(self) -> bool:
        if not self.task.flags:
            raise RuntimeError("Somehow did not load flags for this one?")
        return self.task.flags.editor_review_requested

    @property
    def is_outside_ipr_framework(self) -> bool:
        return self.task.category == TaskCategory.OUTSIDE_IPR_POLICY

    @property
    def is_khr(self) -> bool:
        if not self.task.flags:
            raise RuntimeError("Somehow did not load flags for this one?")
        return self.task.flags.khr_extension

    @property
    def is_multivendor(self) -> bool:
        if not self.task.flags:
            raise RuntimeError("Somehow did not load flags for this one?")
        return self.task.flags.multivendor_extension

    @property
    def is_vendor(self) -> bool:
        if not self.task.flags:
            raise RuntimeError("Somehow did not load flags for this one?")
        return self.task.flags.single_vendor_extension

    @cached_property
    def latency(self):
        """Time since last status change in days"""
        if not self.task.task_dict:
            raise RuntimeError("No task dict?")
        date_moved = datetime.datetime.fromtimestamp(
            self.task.task_dict["date_moved"], datetime.UTC
        )
        date_started = datetime.datetime.fromtimestamp(
            self.task.task_dict["date_started"], datetime.UTC
        )
        # TODO choose the more recent of this date or the MR update date?
        # or latest push to MR?
        pending_since = max(date_moved, date_started)
        age = NOW - pending_since
        return age.days + self.offset

    @cached_property
    def task_issue_age(self):
        """Time since task creation in days"""
        if not self.task.task_dict:
            raise RuntimeError("No task dict?")
        date_creation = datetime.datetime.fromtimestamp(
            self.task.task_dict["date_creation"], datetime.UTC
        )
        age = NOW - date_creation
        return age.days

    @property
    def title(self) -> str:
        return self.task.title

    @property
    def url(self) -> str:
        if not self.task.url:
            raise RuntimeError("Why is URL missing?")
        return self.task.url

    @property
    def unchangeable(self):
        if not self.task.flags:
            raise RuntimeError("Somehow did not load flags for this one?")
        return self.task.flags.api_frozen

    @property
    def author_category_priority(self):
        author_category = 0
        if self.is_khr:
            author_category = -5
        elif self.is_multivendor:
            author_category = -3
        elif self.is_vendor:
            author_category = -1
        else:
            log.warning("Could not guess vendor category for %s", self.title)

        if not self.is_outside_ipr_framework:
            # bump up ratification-track EXT
            author_category -= 1
        return author_category

    def to_markdown(self, slot):
        # stub
        return ""

    @classmethod
    def create(
        cls,
        task: OperationsTask,
        main_mr: gitlab.v4.objects.ProjectMergeRequest,
        vendors: VendorNames,
    ):

        vendor, tag = compute_vendor_name_and_tag(task.title, vendors)
        return cls(
            task=task,
            mr=main_mr,
            vendor_name=vendor,
            vendor_tag=tag,
        )


def load_needs_review(
    tasks: Iterable[OperationsTask],
    proj: gitlab.v4.objects.Project,
    vendors: VendorNames,
    column: TaskColumn = TaskColumn.AWAITING_REVIEW,
    swimlane: TaskSwimlane = TaskSwimlane.SPEC_REVIEW_PHASE,
) -> list[ReleaseChecklistIssue]:
    log.info("Loading items that need review")
    items = []
    for task in tasks:

        if task.column != column:
            continue
        if task.swimlane != swimlane:
            continue
        if not task.flags:
            raise RuntimeError("Flags not populated?")
        if not task.flags.editor_review_requested:
            continue

        mr_num = task.main_mr
        if mr_num is None:
            raise RuntimeError("Main MR not populated?")

        mr = proj.mergerequests.get(mr_num)

        items.append(KBChecklistItem.create(task, mr, vendor_names))
    return items


def make_html(
    design_results: PriorityResults,
    spec_results: PriorityResults,
    sort_desc: Iterable[str],
    fn: str,
    extra: str | None,
    extra_safe: str | None,
):
    from jinja2 import Environment, PackageLoader, select_autoescape

    env = Environment(
        loader=PackageLoader("openxr_ops"),
        autoescape=select_autoescape(),
    )
    template = env.get_template("priority_list_kb.html")
    with open(fn, "w", encoding="utf-8") as fp:
        fp.write(
            template.render(
                design_results=design_results,
                spec_results=spec_results,
                now=NOW,
                sort_description=sort_desc,
                extra=extra,
                extra_safe=extra_safe,
            )
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_help = True
    parser.add_argument("--html", type=str, help="Output HTML to filename")
    parser.add_argument("--extra", type=str, help="Extra text to add to HTML footer")
    parser.add_argument(
        "--config",
        type=str,
        help="TOML file to read config from, including latency offsets and custom sorts",
    )

    parser.add_argument(
        "--extra-safe",
        type=str,
        help="Extra text to add to HTML footer without escaping special characters",
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

    oxr_gitlab = OpenXRGitlab.create()

    config = ReviewPriorityConfig(args.config)
    log.info("Performing startup queries")
    vendor_names = VendorNames.from_git(oxr_gitlab.main_proj)
    collection = ReleaseChecklistCollection(
        oxr_gitlab.main_proj,
        oxr_gitlab.operations_proj,
        checklist_factory=None,
        vendor_names=vendor_names,
    )

    collection.load_initial_data()

    # spec_review_items = load_needs_review(collection)

    async def async_main():
        kb, proj = await connect_and_get_project()

        kb_project = KanboardProject(kb, int(proj["id"]))
        log.info("Getting columns, swimlanes, and categories")
        await kb_project.fetch_all_id_maps()

        log.info("Loading all active KB tasks")
        task_collection = TaskCollection(kb_project)
        await task_collection.load_project()

        spec_review_items = load_needs_review(
            task_collection.tasks.values(), oxr_gitlab.main_proj, vendors=vendor_names
        )

        config.apply_offsets(spec_review_items)
        spec_review_sorter: SorterBase = config.get_sorter(vendor_names)
        sorted_spec_review = spec_review_sorter.get_sorted(spec_review_items)

        design_review_items = load_needs_review(
            task_collection.tasks.values(),
            oxr_gitlab.main_proj,
            vendors=vendor_names,
            swimlane=TaskSwimlane.DESIGN_REVIEW_PHASE,
        )
        sorted_design_review = BasicDesignReviewSort(vendor_names, {}).get_sorted(
            design_review_items
        )

        spec_review_results = PriorityResults.from_sorted_items(sorted_spec_review)
        design_review_results = PriorityResults.from_sorted_items(sorted_design_review)

        if args.html:
            log.info("Outputting to HTML: %s", args.html)
            make_html(
                design_review_results,
                spec_review_results,
                spec_review_sorter.get_sort_description(),
                args.html,
                args.extra,
                args.extra_safe,
            )
        # else:
        #     print(spec_review_results.list_markdown)
        #     print("\n")

        #     for vendor, slots in spec_review_results.vendor_name_to_slots.items():
        #         print(f"* {vendor} - slots {slots}")
        #     print(f"* Unknown: {spec_review_results.unknown_slots}")

    asyncio.run(async_main())
