#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import logging
import sys

from create_extension_checklist import (
    ReleaseChecklistCollection,
    ReleaseChecklistFactory,
    VendorNames,
)
from openxr import OpenXRGitlab

if __name__ == "__main__":
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
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    if not any((args.update_descriptions, args.update_labels)):
        log.error("Pass at least one command!\n")
        parser.print_help()
        sys.exit(1)

    oxr_gitlab = OpenXRGitlab.create()
    log.info("Performing startup queries")
    collection = ReleaseChecklistCollection(
        oxr_gitlab.main_proj,
        oxr_gitlab.operations_proj,
        checklist_factory=ReleaseChecklistFactory(oxr_gitlab.operations_proj),
        vendor_names=VendorNames.from_git(oxr_gitlab.main_proj),
    )

    if args.update_labels:
        collection.update_mr_labels()
    if args.update_descriptions:
        collection.update_mr_descriptions()
