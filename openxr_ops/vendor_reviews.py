#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging
from typing import Iterable, List, Optional, Tuple, cast

from .checklists import ColumnName, ReleaseChecklistCollection
from .custom_sort import SorterBase
from .gitlab import OpenXRGitlab
from .priority_results import NOW, PriorityResults, ReleaseChecklistIssue
from .review_priority import ReviewPriorityConfig
from .vendors import VendorNames


def load_in_flight(
    collection: ReleaseChecklistCollection,
) -> Tuple[
    List[ReleaseChecklistIssue],
    dict[str, List[ReleaseChecklistIssue]],
]:
    log.info("Loading items that are in progress")
    items = []
    needs_review = []
    needs_revision = []
    needs_approval = []

    columns = [
        ColumnName.NEEDS_REVIEW.value,
        ColumnName.NEEDS_REVISION.value,
        ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION.value,
    ]
    for issue in collection.issue_to_mr.keys():
        issue_obj = collection.issue_str_to_cached_issue_object(issue)
        if not issue_obj:
            continue

        labels: Iterable[str] = issue_obj.labels
        if all(col not in labels for col in columns):
            continue

        # print(issue_obj.attributes["title"])

        mr_num = collection.issue_to_mr[issue]
        mr = collection.proj.mergerequests.get(mr_num)

        rci = ReleaseChecklistIssue.create(issue_obj, mr, collection.vendor_names)

        items.append(rci)
        if ColumnName.NEEDS_REVIEW.value in labels:
            needs_review.append(rci)
        elif ColumnName.NEEDS_REVISION.value in labels:
            needs_revision.append(rci)
        elif ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION.value in labels:
            needs_approval.append(rci)
    return items, {
        "needs_review": needs_review,
        "needs_revision": needs_revision,
        "needs_approval": needs_approval,
    }


def make_html(
    vendor: str,
    categories: dict[str, List[ReleaseChecklistIssue]],
    results: PriorityResults,
    sort_desc: Iterable[str],
    fn: str,
    extra: Optional[str],
    extra_safe: Optional[str],
):
    from jinja2 import Environment, PackageLoader, select_autoescape

    env = Environment(
        loader=PackageLoader("openxr_ops"),
        autoescape=select_autoescape(),
    )
    template = env.get_template("vendor_ext_list.html")
    with open(fn, "w", encoding="utf-8") as fp:
        fp.write(
            template.render(
                results=results,
                now=NOW,
                sort_description=sort_desc,
                extra=extra,
                extra_safe=extra_safe,
                vendor=vendor,
                categories=categories,
            )
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

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

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()

    log.info("Performing startup queries")
    vendor_names = VendorNames.from_git(oxr_gitlab.main_proj)
    collection = ReleaseChecklistCollection(
        oxr_gitlab.main_proj,
        oxr_gitlab.operations_proj,
        checklist_factory=None,
        vendor_names=vendor_names,
    )

    collection.load_initial_data()

    items, categories = load_in_flight(collection)

    config = ReviewPriorityConfig(args.config)
    config.apply_offsets(items)
    sorter: SorterBase = config.get_sorter(vendor_names)

    sorted = sorter.get_sorted(categories["needs_review"])
    for vendor_tag, vendor_data in config.vendor_config.items():
        vendor_name = vendor_names.get_vendor_name(vendor_tag)
        if not vendor_name:
            log.warning("Could not look up vendor name for %s", vendor_tag)
            continue

        log.info("Considering %s", vendor_name)
        outfilename = cast(Optional[str], vendor_data.get("output_filename"))
        if not outfilename:
            log.info("No vendor output file requested for %s", vendor_name)
            continue

        def filter_items(
            data: List[ReleaseChecklistIssue],
        ) -> List[ReleaseChecklistIssue]:
            return [x for x in data if x.vendor_name == vendor_name]

        vendor_results = PriorityResults.from_sorted_items(filter_items(sorted))
        vendor_categories = {
            "needs_review": filter_items(categories["needs_review"]),
            "needs_revision": filter_items(categories["needs_revision"]),
            "needs_approval": filter_items(categories["needs_approval"]),
        }

        log.info("Outputting to HTML: %s", outfilename)
        make_html(
            vendor_name,
            vendor_categories,
            vendor_results,
            sorter.get_sort_description(),
            outfilename,
            args.extra,
            args.extra_safe,
        )
