#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging
import tomllib
from typing import Iterable, List, Optional, Tuple

from .checklists import ColumnName, ReleaseChecklistCollection
from .custom_sort import SORTERS, BasicSort, SorterBase
from .gitlab import OpenXRGitlab
from .priority_results import NOW, PriorityResults, ReleaseChecklistIssue, apply_offsets
from .vendors import VendorNames


def load_in_flight(
    vendor_tag: str,
    collection: ReleaseChecklistCollection,
) -> Tuple[
    List[ReleaseChecklistIssue],
    List[ReleaseChecklistIssue],
    List[ReleaseChecklistIssue],
    List[ReleaseChecklistIssue],
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
        if rci.vendor_name != vendor_tag:
            log.info("Skipping %s - %s", rci.title, rci.vendor_name)
            continue

        items.append(rci)
        if ColumnName.NEEDS_REVIEW.value in labels:
            needs_review.append(rci)
        elif ColumnName.NEEDS_REVISION.value in labels:
            needs_revision.append(rci)
        elif ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION.value in labels:
            needs_approval.append(rci)
    return items, needs_review, needs_revision, needs_approval


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

    parser.add_argument("vendor", type=str, help="Vendor tag")
    parser.add_argument("--html", type=str, help="Output HTML to filename")
    parser.add_argument("--extra", type=str, help="Extra text to add to HTML footer")
    parser.add_argument(
        "--config",
        type=str,
        help="TOML file to read config from, including latency offsets and custom sorts",
    )
    parser.add_argument(
        "--offsets",
        type=str,
        help="TOML file to read latency offsets from",
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

    items, needs_review, needs_revision, needs_approval = load_in_flight(
        args.vendor, collection
    )

    categories = {
        "needs_review": needs_review,
        "needs_revision": needs_revision,
        "needs_approval": needs_approval,
    }

    if args.offsets:
        with open(args.offsets, "rb") as fp:
            offsets = tomllib.load(fp)
        apply_offsets(offsets, needs_review)

    config: Optional[dict] = None
    if args.config:
        log.info("Opening config %s", args.config)
        with open(args.config, "rb") as fp:
            config = tomllib.load(fp)
        if "offsets" in config:
            log.info("Applying offsets from config")
            apply_offsets(config["offsets"], needs_review)

    vendor_config = dict()
    sorter: SorterBase = BasicSort(vendor_names, vendor_config)

    if config:
        vendor_config = config.get("vendor", dict())

        sorter_name = config.get("sorter")
        if sorter_name:
            sorter_factory = SORTERS.get(sorter_name)
            assert sorter_factory

            log.info("Using specified sorter: %s", sorter_name)
            sorter = sorter_factory(vendor_names, vendor_config)

    sorted = sorter.get_sorted(needs_review)

    results = PriorityResults.from_sorted_items(sorted)

    if args.html:
        log.info("Outputting to HTML: %s", args.html)
        make_html(
            args.vendor,
            categories,
            results,
            sorter.get_sort_description(),
            args.html,
            args.extra,
            args.extra_safe,
        )
    else:
        print(results.list_markdown)
        print("\n")

        for vendor, slots in results.vendor_name_to_slots.items():
            print(f"* {vendor} - slots {slots}")
        print(f"* Unknown: {results.unknown_slots}")
