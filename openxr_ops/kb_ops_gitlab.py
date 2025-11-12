# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""Connecting Kanboard and GitLab for operations tracking."""

import logging
import re

import gitlab
import gitlab.v4.objects

from .checklists import CHECKLIST_RE

_TASK_BASE_URL = "https://openxr-boards.khronos.org/task/"


_OPS_BOARD_LINK = re.compile(
    r"Operations Tracking Task: " + re.escape(_TASK_BASE_URL) + r"(?P<task_id>[0-9]+)"
)


def _make_ops_board_link(task_id):
    return f"Operations Tracking Task: {_TASK_BASE_URL}{task_id}"


def update_mr_desc(
    merge_request: gitlab.v4.objects.ProjectMergeRequest,
    task_id: int,
    *,
    save_changes: bool,
    mark_old_as_obsolete: bool,
):
    log = logging.getLogger(f"{__name__}.update_mr_desc")
    new_front = _make_ops_board_link(task_id)
    prepend = f"{new_front}\n\n"

    if merge_request.description.strip() == new_front:
        # minimal MR desc
        return
    desc: str = merge_request.description
    new_desc: str = desc
    m = _OPS_BOARD_LINK.search(desc)
    if m:

        replaced_desc = prepend + _OPS_BOARD_LINK.sub("", desc, 1).strip()
        if not m.group(0).startswith(new_front):
            log.info(
                f"MR {merge_request.get_id()} description starts with the wrong link"
            )
            new_desc = replaced_desc
    else:

        new_desc = prepend + desc
        log.info("MR %s needs task link", str(merge_request.get_id()))

    checklist_link_match = CHECKLIST_RE.search(new_desc)
    if checklist_link_match:
        matching_text = checklist_link_match.group(0)
        if "Obsolete" not in matching_text:
            obsolete_desc = new_desc.replace(
                matching_text, f"Obsolete {matching_text}", count=1
            )
            if mark_old_as_obsolete:
                log.info(
                    "Old checklist link in MR %s needs to be marked as obsolete.",
                    str(merge_request.get_id()),
                )
                new_desc = obsolete_desc

    if new_desc != desc:
        if save_changes:
            log.info("Saving change to MR %s", str(merge_request.get_id()))
            merge_request.description = new_desc
            merge_request.save()
        else:
            log.info(
                "Would have made changes to MR %s description but skipping that by request.",
                str(merge_request.get_id()),
            )
            log.debug(
                "Updated description would have been:\n%s",
                new_desc,
            )
