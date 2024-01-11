#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import os
import sys

import gitlab
import gitlab.v4.objects

from create_extension_checklist import (
    ReleaseChecklistCollection,
    ReleaseChecklistFactory,
    VendorNames,
)

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-l", "--update-labels", action="store_true", help="Update labels on MRs"
    )
    parser.add_argument(
        "-d",
        "--update-descriptions",
        action="store_true",
        help="Update descriptions on MRs",
    )

    args = parser.parse_args()

    if not any((args.update_descriptions, args.update_labels)):
        print("Pass at least one command!\n")
        parser.print_help()
        sys.exit(1)

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )

    main_proj = gl.projects.get("openxr/openxr")
    operations_proj = gl.projects.get("openxr/openxr-operations")

    print("Performing startup queries")
    collection = ReleaseChecklistCollection(
        main_proj,
        operations_proj,
        checklist_factory=ReleaseChecklistFactory(operations_proj),
        vendor_names=VendorNames(main_proj),
    )

    if args.update_labels:
        collection.update_mr_labels()
    if args.update_descriptions:
        collection.update_mr_descriptions()
