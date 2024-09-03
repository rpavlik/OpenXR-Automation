#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging
from typing import Iterable, List, Optional

import tomllib

from .checklists import ReleaseChecklistCollection
from .gitlab import OpenXRGitlab
from .priority_results import NOW, PriorityResults, ReleaseChecklistIssue, apply_offsets
from .vendors import VendorNames
from .custom_sort import BasicSort, SORTERS, SorterBase

_NEEDSREVIEW_LABEL = "status:NeedsReview"


def load_needs_review(
    collection: ReleaseChecklistCollection,
) -> List[ReleaseChecklistIssue]:
    log.info("Loading items that need review")
    items = []
    for issue in collection.issue_to_mr.keys():
        issue_obj = collection.issue_str_to_cached_issue_object(issue)
        if not issue_obj:
            continue

        if _NEEDSREVIEW_LABEL not in issue_obj.labels:
            continue

        # print(issue_obj.attributes["title"])

        mr_num = collection.issue_to_mr[issue]
        mr = collection.proj.mergerequests.get(mr_num)

        items.append(
            ReleaseChecklistIssue.create(issue_obj, mr, collection.vendor_names)
        )
    return items


def make_html(
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
    template = env.get_template("priority_list.html")
    with open(fn, "w", encoding="utf-8") as fp:
        fp.write(
            template.render(
                results=results,
                now=NOW,
                sort_description=sort_desc,
                extra=extra,
                extra_safe=extra_safe,
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

    items = load_needs_review(collection)

    if args.offsets:
        with open(args.offsets, "rb") as fp:
            offsets = tomllib.load(fp)
        apply_offsets(offsets, items)

    config: Optional[dict] = None
    if args.config:
        log.info("Opening config %s", args.config)
        with open(args.config, "rb") as fp:
            config = tomllib.load(fp)
        if "offsets" in config:
            log.info("Applying offsets from config")
            apply_offsets(config["offsets"], items)

    results = PriorityResults.from_items(items)

    vendor_config = dict()
    sorter: SorterBase = BasicSort(vendor_names, vendor_config)

    if config:
        vendor_config = config.get("vendor", dict())

        sorter_name = config.get("sorter")
        if sorter_name:
            (sorter_factory) = SORTERS.get(sorter_name)
            assert sorter_factory
            log.info("Using specified sorter: %s", sorter_name)
            sorter = sorter_factory(vendor_names, vendor_config)
    sorted = sorter.get_sorted(items)

    results = PriorityResults.from_sorted_items(sorted)

    if args.html:
        log.info("Outputting to HTML: %s", args.html)
        make_html(
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
