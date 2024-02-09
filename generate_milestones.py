#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import datetime
from typing import Optional

from openxr import OpenXRGitlab


def generate_milestones(
    oxr: OpenXRGitlab,
    major: int,
    minor: int,
    patch: int,
    freeze: Optional[datetime.date] = None,
):
    ver = f"{major}.{minor}.{patch}"
    release_milestone_title = f"{ver} release"
    cts_release_milestone_title = f"Conformance {ver}.0 release"

    desired_release_title = release_milestone_title
    due_date = None
    if freeze:
        desired_release_title = (
            f"{release_milestone_title} - freeze {freeze.strftime('%d-%b')}"
        )
        due_date = (freeze + datetime.timedelta(days=7)).isoformat()

    print(f"Looking for milestones mentioning '{release_milestone_title}'")
    milestones = oxr.group.milestones.list(search=release_milestone_title, all=True)

    spec_release_milestone = [
        m for m in milestones if m.title.startswith(release_milestone_title)
    ]

    cts_release_milestone = [
        m for m in milestones if m.title.startswith(cts_release_milestone_title)
    ]

    if spec_release_milestone:
        milestone = spec_release_milestone[0]
        print(f"Found spec milestone: {milestone.title}")
        if freeze and due_date and milestone.title != desired_release_title:
            # We should add the freeze date
            print("Adding freeze date to title")
            new_data = {"due_date": due_date, "title": desired_release_title}
            oxr.group.milestones.update(id=milestone.get_id(), new_data=new_data)
    else:
        print("Creating spec release milestone")
        data = {
            "title": desired_release_title,
            "description": f"Spec patch release {ver}",
        }
        if freeze and due_date:
            data["due_date"] = due_date
        oxr.group.milestones.create(data=data)

    if cts_release_milestone:
        print(f"Found CTS milestone: {cts_release_milestone[0].title}")
    else:
        print("Creating CTS release milestone")
        oxr.group.milestones.create(
            data={
                "title": cts_release_milestone_title,
                "description": f"Conformance test suite release {ver}.0",
            }
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
        "--minor", type=int, default=0, help="Manually specify the minor version"
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
