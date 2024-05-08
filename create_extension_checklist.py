#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>


import logging

from openxr_ops.checklists import ReleaseChecklistCollection, ReleaseChecklistFactory
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.vendors import VendorNames

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mr",
        type=int,
        nargs="+",
        help="MR number to generate an extension checklist for",
    )
    parser.add_argument(
        "--extname", type=str, help="Manually specify the extension name"
    )
    parser.add_argument(
        "-i", "--vendorid", type=str, action="append", help="Specify the vendor ID"
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr = OpenXRGitlab.create()

    log.info("Performing startup queries")
    collection = ReleaseChecklistCollection(
        oxr.main_proj,
        oxr.operations_proj,
        checklist_factory=ReleaseChecklistFactory(oxr.operations_proj),
        vendor_names=VendorNames.from_git(oxr.main_proj),
    )

    kwargs = {}
    if "extname" in args and args.extname:
        kwargs["ext_names"] = [args.extname]
    if "vendorid" in args and args.vendorid:
        kwargs["vendor_ids"] = args.vendorid
    for num in args.mr:
        collection.handle_mr_if_needed(num, **kwargs)
