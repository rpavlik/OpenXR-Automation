#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging
import tomllib
from typing import Iterable, List, Optional, Union

from .checklists import ColumnName, ReleaseChecklistCollection
from .custom_sort import SORTERS, BasicDesignReviewSort, BasicSpecReviewSort, SorterBase
from .gitlab import OpenXRGitlab
from .priority_results import NOW, PriorityResults, ReleaseChecklistIssue, apply_offsets
from .vendors import VendorNames


class ReviewPriorityConfig:
    def __init__(self, fn: Optional[str]):
        self.config: Optional[dict] = None
        """The actual config initially loaded from TOML."""

        self.vendor_config: dict[str, dict[str, Union[str, List[str]]]] = dict()
        """Customization per vendor tag."""

        self.log = logging.getLogger(__name__ + ".ReviewPriorityConfig")

        if fn:
            self.log.info("Opening config %s", fn)
            with open(fn, "rb") as fp:
                self.config = tomllib.load(fp)
            self.vendor_config = self.config.get("vendor", dict())

    def apply_offsets(self, items: Iterable[ReleaseChecklistIssue]):
        """Offset the latency as directed by the config."""
        offsets = None
        if self.config:
            offsets = self.config.get("offsets")
        if offsets:
            apply_offsets(offsets, items)

    def get_sorter(self, vendor_names: VendorNames) -> SorterBase:
        """Create either a basic sorter or desired customized sorter."""
        if not self.config:
            return BasicSpecReviewSort(vendor_names, self.vendor_config)

        sorter_name = self.config.get("sorter")
        if not sorter_name:
            return BasicSpecReviewSort(vendor_names, self.vendor_config)

        sorter_factory = SORTERS.get(sorter_name)
        assert sorter_factory

        self.log.info("Using specified sorter: %s", sorter_name)
        return sorter_factory(vendor_names, self.vendor_config)


def load_needs_review(
    collection: ReleaseChecklistCollection,
    column: ColumnName = ColumnName.AWAITING_SPEC_REVIEW,
) -> List[ReleaseChecklistIssue]:
    log.info("Loading items that need review")
    items = []
    for issue in collection.issue_to_mr.keys():
        issue_obj = collection.issue_str_to_cached_issue_object(issue)
        if not issue_obj:
            continue

        if column.value not in issue_obj.labels:
            continue

        # print(issue_obj.attributes["title"])

        mr_num = collection.issue_to_mr[issue]
        mr = collection.proj.mergerequests.get(mr_num)

        items.append(
            ReleaseChecklistIssue.create(issue_obj, mr, collection.vendor_names)
        )
    return items


def make_html(
    design_results: PriorityResults,
    spec_results: PriorityResults,
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

    spec_review_items = load_needs_review(collection)

    config.apply_offsets(spec_review_items)
    spec_review_sorter: SorterBase = config.get_sorter(vendor_names)
    sorted_spec_review = spec_review_sorter.get_sorted(spec_review_items)

    design_review_items = load_needs_review(
        collection, ColumnName.AWAITING_DESIGN_REVIEW
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
    else:
        print(spec_review_results.list_markdown)
        print("\n")

        for vendor, slots in spec_review_results.vendor_name_to_slots.items():
            print(f"* {vendor} - slots {slots}")
        print(f"* Unknown: {spec_review_results.unknown_slots}")
