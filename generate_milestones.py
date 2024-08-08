#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import datetime
from typing import Any, Iterable, Optional

from openxr_ops.gitlab import OpenXRGitlab


def generate_milestone(
    oxr: OpenXRGitlab,
    title_prefix: str,
    description: str,
    milestones: Iterable[Any],
    freeze: Optional[datetime.date] = None,
    due_date: Optional[datetime.date] = None,
):
    if not oxr.group:
        raise RuntimeError(
            "Access to the gitlab group is required for generating milestones"
        )

    if freeze:
        desired_title = f"{title_prefix} - freeze {freeze.strftime('%d-%b')}"
    else:
        desired_title = title_prefix

    matching_milestone = [m for m in milestones if m.title.startswith(title_prefix)]

    if matching_milestone:
        milestone = matching_milestone[0]
        print(f"Found milestone: {milestone.title}")
        if freeze and due_date and milestone.title != desired_title:
            # We should add the freeze date and due date
            print(f"Adding freeze date to title: {desired_title}")
            new_data = {"due_date": due_date.isoformat(), "title": desired_title}
            oxr.group.milestones.update(id=milestone.get_id(), new_data=new_data)
    else:
        print("Creating milestone:", desired_title)
        data = {
            "title": desired_title,
            "description": description,
        }
        if due_date:
            data["due_date"] = due_date.isoformat()
        oxr.group.milestones.create(data=data)


def generate_milestones(
    oxr: OpenXRGitlab,
    major: int,
    minor: int,
    patch: int,
    freeze: Optional[datetime.date] = None,
):
    if not oxr.group:
        raise RuntimeError(
            "Access to the gitlab group is required for generating milestones"
        )

    ver = f"{major}.{minor}.{patch}"
    # Titles without freeze date
    release_milestone_title = f"{ver} release"
    cts_release_milestone_title = f"Conformance {ver}.0 release"

    due_date: Optional[datetime.date] = None
    cts_freeze: Optional[datetime.date] = None
    if freeze:
        due_date = freeze + datetime.timedelta(days=7)

        cts_freeze = freeze + datetime.timedelta(days=14)

    print(f"Looking for milestones mentioning '{release_milestone_title}'")
    milestones = oxr.group.milestones.list(search=release_milestone_title, all=True)

    generate_milestone(
        oxr,
        release_milestone_title,
        f"Spec patch release {ver}",
        milestones,
        freeze,
        due_date,
    )
    generate_milestone(
        oxr,
        cts_release_milestone_title,
        f"Conformance test suite release {ver}.0",
        milestones,
        freeze=cts_freeze,
        due_date=cts_freeze,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "patch",
        type=int,
        nargs="+",
        help="Patch version number to generate milestones for",
    )
    parser.add_argument(
        "--major", type=int, default=1, help="Manually specify the major version"
    )
    parser.add_argument(
        "--minor", type=int, default=1, help="Manually specify the minor version"
    )

    parser.add_argument(
        "--month",
        type=int,
        help="Specify a month number (1-12) for the freeze, for the first patch",
    )
    parser.add_argument(
        "--day",
        type=int,
        help="Specify a day of the month (1-31) for the freeze, for the first patch",
    )

    args = parser.parse_args()

    oxr = OpenXRGitlab.create()

    freeze = None
    if "month" in args and "day" in args:
        today = datetime.date.today()
        freeze = datetime.date(today.year, args.month, args.day)
    for patch in args.patch:
        generate_milestones(oxr, args.major, args.minor, patch, freeze=freeze)

        # reset so that only the first one gets a freeze
        freeze = None

    # kwargs = {}
    # if "extname" in args and args.extname:
    #     kwargs["ext_names"] = [args.extname]
    # if "vendorid" in args and args.vendorid:
    #     kwargs["vendor_ids"] = args.vendorid
    # for num in args.mr:
    #     collection.handle_mr_if_needed(num, **kwargs)
