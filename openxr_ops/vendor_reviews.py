#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging
from pathlib import Path
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

    columns = [
        ColumnName.INITIAL_COMPOSITION.value,
        ColumnName.NEEDS_REVIEW.value,
        ColumnName.NEEDS_REVISION.value,
        ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION.value,
    ]
    col_data: dict[str, List[ReleaseChecklistIssue]] = {k: [] for k in columns}
    for issue in collection.issue_to_mr.keys():
        issue_obj = collection.issue_str_to_cached_issue_object(issue)
        if not issue_obj:
            continue

        labels: Iterable[str] = issue_obj.labels
        if all(col not in labels for col in columns):
            # not in one of the columns we care about
            continue

        mr_num = collection.issue_to_mr[issue]
        mr = collection.proj.mergerequests.get(mr_num)

        rci = ReleaseChecklistIssue.create(issue_obj, mr, collection.vendor_names)

        items.append(rci)
        for col in columns:
            if col in labels:
                col_data[col].append(rci)
                break

    return items, {
        "initial_composition": col_data[ColumnName.INITIAL_COMPOSITION.value],
        "needs_review": col_data[ColumnName.NEEDS_REVIEW.value],
        "needs_revision": col_data[ColumnName.NEEDS_REVISION.value],
        "needs_approval": [
            item
            for item in col_data[
                ColumnName.NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION.value
            ]
            if "champion-approved" not in item.issue_obj.labels
        ],
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


def make_vendor_name_to_fn_map(
    items: Iterable[ReleaseChecklistIssue], vendor_names_obj: VendorNames
) -> dict[str, str]:
    active_vendor_tags: set[str] = set()
    for item in items:
        tag = item.vendor_tag
        if tag is None:
            continue
        canonicalized = vendor_names_obj.canonicalize_vendor_tag(tag)
        if canonicalized is not None:
            active_vendor_tags.add(canonicalized)
    fn_to_vendorname = {
        f"vendor_{vendor_tag}.html": vendor_names_obj.get_vendor_name(vendor_tag)
        for vendor_tag in active_vendor_tags
    }
    return {
        vendor_name: filename
        for filename, vendor_name in fn_to_vendorname.items()
        if vendor_name is not None
    }


def filter_and_generate_vendor_page(
    vendor_name: str,
    filename: str,
    sorted: Iterable[ReleaseChecklistIssue],
    categories: dict[str, List[ReleaseChecklistIssue]],
    extra: Optional[str] = None,
    extra_safe: Optional[str] = None,
):
    log.info("Considering %s", vendor_name)

    def filter_items(
        data: Iterable[ReleaseChecklistIssue],
    ) -> List[ReleaseChecklistIssue]:
        return [x for x in data if x.vendor_name == vendor_name]

    vendor_results = PriorityResults.from_sorted_items(filter_items(sorted))
    vendor_categories = {
        "needs_review": filter_items(categories["needs_review"]),
        "needs_revision": filter_items(categories["needs_revision"]),
        "needs_approval": filter_items(categories["needs_approval"]),
    }

    log.info("Outputting to HTML: %s", filename)
    make_html(
        vendor_name,
        vendor_categories,
        vendor_results,
        sorter.get_sort_description(),
        filename,
        extra,
        extra_safe,
    )


def generate_vendor_index(
    vendor_names_to_filenames: dict[str, str],
    filename: str,
    extra: Optional[str] = None,
    extra_safe: Optional[str] = None,
):

    from jinja2 import Environment, PackageLoader, select_autoescape

    env = Environment(
        loader=PackageLoader("openxr_ops"),
        autoescape=select_autoescape(),
    )
    template = env.get_template("vendor_list.html")
    with open(filename, "w", encoding="utf-8") as fp:
        fp.write(
            template.render(
                vendor_names_to_filenames=vendor_names_to_filenames,
                now=NOW,
                extra=extra,
                extra_safe=extra_safe,
            )
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument("--html-dir", type=str, help="Output HTML to directory")
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

    outdir = Path(".")
    if args.html_dir:
        outdir = Path(args.html_dir)

    vendor_names_to_filenames = make_vendor_name_to_fn_map(items, vendor_names)

    log.info("Generating vendor index")
    generate_vendor_index(vendor_names_to_filenames, str(outdir / "vendors.html"))

    for vendor_name, filename in vendor_names_to_filenames.items():
        filter_and_generate_vendor_page(
            vendor_name,
            str(outdir / filename),
            sorted,
            categories,
            extra=args.extra,
            extra_safe=args.extra_safe,
        )
