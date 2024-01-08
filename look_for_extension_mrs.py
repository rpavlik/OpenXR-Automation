#!/usr/bin/env python3
# Copyright 2022-2023, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import itertools
import logging
import os
from typing import cast
import gitlab
from create_extension_checklist import (
    KHR_EXT_LABEL,
    VENDOR_EXT_LABEL,
    VendorNames,
    ReleaseChecklistFactory,
    ReleaseChecklistCollection,
    get_extension_names_for_mr,
)
from work_item_and_collection import get_short_ref


def main():
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)
    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )

    main_proj = gl.projects.get("openxr/openxr")
    operations_proj = gl.projects.get("openxr/openxr-operations")

    log.info("Performing startup queries")
    collection = ReleaseChecklistCollection(
        main_proj,
        operations_proj,
        checklist_factory=ReleaseChecklistFactory(operations_proj),
        vendor_names=VendorNames(main_proj),
    )

    for mr in itertools.chain(
        *(
            main_proj.mergerequests.list(labels=[label], state="opened", iterator=True)
            for label in (KHR_EXT_LABEL, VENDOR_EXT_LABEL)
        )
    ):
        proj_mr = cast(gitlab.v4.objects.ProjectMergeRequest, mr)
        ref = get_short_ref(proj_mr)

        if collection.mr_has_checklist(proj_mr.iid):
            log.info(
                "GitLab MR Search: %s: %s - Already has checklist", ref, proj_mr.title
            )
            continue

        ext_name_data = list(get_extension_names_for_mr(proj_mr))
        if ext_name_data:
            log.info("GitLab MR Search: %s: %s", ref, proj_mr.title)
            log.info(
                "Extension name(s): %s",
                str([ext.full_name for ext in ext_name_data]),
            )
            try:
                collection.handle_mr_if_needed(proj_mr.iid)
            except Exception as e:
                log.warning("Failed trying to add/check for checklist: %s", str(e))
                continue

    collection.update_mr_descriptions()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    main()
