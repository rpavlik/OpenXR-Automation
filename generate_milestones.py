#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


from openxr import OpenXRGitlab


def generate_milestones(oxr: OpenXRGitlab, major: int, minor: int, patch: int):
    ver = f"{major}.{minor}.{patch}"
    release_milestone_title = f"{ver} release"
    cts_release_milestone_title = f"Conformance {ver}.0 release"

    print(f"Looking for milestones mentioning '{release_milestone_title}'")
    milestones = oxr.group.milestones.list(search=release_milestone_title, all=True)

    spec_release_milestone = [
        m for m in milestones if m.title.startswith(release_milestone_title)
    ]

    cts_release_milestone = [
        m for m in milestones if m.title.startswith(cts_release_milestone_title)
    ]

    if spec_release_milestone:
        print(f"Found spec milestone: {spec_release_milestone[0].title}")
    else:
        print("Creating spec release milestone")
        oxr.group.milestones.create(
            data={
                "title": release_milestone_title,
                "description": f"Spec patch release {ver}",
            }
        )

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

    args = parser.parse_args()

    oxr = OpenXRGitlab.create()

    for patch in args.patch:
        generate_milestones(oxr, args.major, args.minor, patch)
    # kwargs = {}
    # if "extname" in args and args.extname:
    #     kwargs["ext_names"] = [args.extname]
    # if "vendorid" in args and args.vendorid:
    #     kwargs["vendor_ids"] = args.vendorid
    # for num in args.mr:
    #     collection.handle_mr_if_needed(num, **kwargs)
