#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import datetime
import re
from collections.abc import Iterable
from typing import Any, Optional

from openxr_ops.gitlab import OpenXRGitlab


def generate_milestone(
    oxr: OpenXRGitlab,
    title_base: str,
    title_re: re.Pattern,
    description: str,
    milestones: Iterable[Any],
    freeze: datetime.date | None = None,
    due_date: datetime.date | None = None,
    force_title: bool = False,
    dry_run: bool = False,
):
    if not oxr.group:
        raise RuntimeError(
            "Access to the gitlab group is required for generating milestones"
        )

    desired_title = title_base
    if freeze:
        desired_title = f"{title_base} - freeze {freeze.strftime('%d-%b')}"

    matching_milestone = [m for m in milestones if title_re.search(m.title)]

    if matching_milestone:
        milestone = matching_milestone[0]
        current_title = milestone.title.strip()
        print(f"Found milestone: {current_title}")
        if freeze and due_date and current_title != desired_title:
            # We should add the freeze date and due date
            print(f"Adding freeze date to title: {desired_title}")
            new_data = {"due_date": due_date.isoformat(), "title": desired_title}
            if dry_run:
                print("Dry run: would apply this data:", new_data)
            else:
                oxr.group.milestones.update(id=milestone.get_id(), new_data=new_data)
        elif force_title and current_title != desired_title:
            print(f"Replacing outdated format of title: {desired_title}")
            new_data = {"title": desired_title}
            if dry_run:
                print("Dry run: would apply this data:", new_data)
            else:
                oxr.group.milestones.update(id=milestone.get_id(), new_data=new_data)

    else:
        print("Creating milestone:", desired_title)
        data = {
            "title": desired_title,
            "description": description,
        }
        if due_date:
            data["due_date"] = due_date.isoformat()
        if dry_run:
            print("Dry run: would use this data:", data)
        else:
            oxr.group.milestones.create(data=data)


def generate_milestones(
    oxr: OpenXRGitlab,
    major: int,
    minor: int,
    patch: int,
    freeze: datetime.date | None = None,
    force_title: bool = False,
    dry_run: bool = False,
):
    if not oxr.group:
        raise RuntimeError(
            "Access to the gitlab group is required for generating milestones"
        )

    ver = f"{major}.{minor}.{patch}"
    # Titles without freeze date
    release_milestone_title = f"{ver} - Spec Release"
    cts_release_milestone_title = f"{ver}.0 - CTS"

    # Regexes to find existing milestones
    ver_escaped = re.escape(ver)
    release_re = re.compile(rf"({ver_escaped} release|{ver_escaped} - Spec)")
    cts_re = re.compile(
        rf"(Conformance {ver_escaped}.0 release|{ver_escaped}(.0)? - CTS)"
    )

    due_date: datetime.date | None = None
    cts_freeze: datetime.date | None = None
    if freeze:
        due_date = freeze + datetime.timedelta(days=7)

        cts_freeze = freeze + datetime.timedelta(days=14)

    print(f"Looking for milestones mentioning '{ver}'")
    milestones = oxr.group.milestones.list(search=ver, all=True)

    generate_milestone(
        oxr,
        release_milestone_title,
        release_re,
        f"Spec patch release {ver}",
        milestones,
        freeze,
        due_date,
        force_title=force_title,
        dry_run=dry_run,
    )
    generate_milestone(
        oxr,
        cts_release_milestone_title,
        cts_re,
        f"Conformance test suite release {ver}.0",
        milestones,
        freeze=cts_freeze,
        due_date=cts_freeze,
        force_title=force_title,
        dry_run=dry_run,
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force replacing the title.",
        default=False,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not actually make changes.",
        default=False,
    )

    args = parser.parse_args()

    oxr = OpenXRGitlab.create()

    freeze = None
    if "month" in args and "day" in args:
        today = datetime.date.today()
        m = args.month
        d = args.day
        if m and d:
            freeze = datetime.date(today.year, args.month, args.day)
            if freeze < today:
                # Wrap the year!
                freeze = datetime.date(today.year + 1, args.month, args.day)
    for patch in args.patch:
        generate_milestones(
            oxr,
            args.major,
            args.minor,
            patch,
            freeze=freeze,
            force_title=args.force,
            dry_run=args.dry_run,
        )

        # reset so that only the first one gets a freeze
        freeze = None

    # kwargs = {}
    # if "extname" in args and args.extname:
    #     kwargs["ext_names"] = [args.extname]
    # if "vendorid" in args and args.vendorid:
    #     kwargs["vendor_ids"] = args.vendorid
    # for num in args.mr:
    #     collection.handle_mr_if_needed(num, **kwargs)
