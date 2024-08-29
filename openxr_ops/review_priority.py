#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging
from typing import List, Optional
import tomllib

from .checklists import ReleaseChecklistCollection
from .gitlab import OpenXRGitlab
from .vendors import VendorNames
from .priority_results import NOW, ReleaseChecklistIssue, PriorityResults, apply_offsets

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
    results: PriorityResults, fn: str, extra: Optional[str], extra_safe: Optional[str]
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
                sort_description=ReleaseChecklistIssue.get_sort_description(),
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
    collection = ReleaseChecklistCollection(
        oxr_gitlab.main_proj,
        oxr_gitlab.operations_proj,
        checklist_factory=None,
        vendor_names=VendorNames.from_git(oxr_gitlab.main_proj),
    )

    items = load_needs_review(collection)

    if args.offsets:
        with open(args.offsets, "rb") as fp:
            offsets = tomllib.load(fp)
        apply_offsets(offsets, items)

    results = PriorityResults.from_items(items)

    if args.html:
        log.info("Outputting to HTML: %s", args.html)
        make_html(results, args.html, args.extra, args.extra_safe)
    else:
        print(results.list_markdown)
        print("\n")

        for vendor, slots in results.vendor_name_to_slots.items():
            print(f"* {vendor} - slots {slots}")
        print(f"* Unknown: {results.unknown_slots}")
