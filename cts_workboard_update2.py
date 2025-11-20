#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""This updates a CTS workboard, but starting with the board, rather than GitLab."""

import itertools
import json
import logging
from typing import cast

import gitlab
import gitlab.v4.objects
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from nullboard_gitlab import ListName, parse_board, update_board
from openxr_ops.cts_board_utils import (
    DO_NOT_MERGE,
    FILTER_OUT,
    REQUIRED_LABEL_SET,
    compute_api_item_state_and_suffix,
)
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.labels import MainProjectLabels
from work_item_and_collection import WorkUnit, WorkUnitCollection, get_short_ref


def _make_api_item_text(
    api_item: ProjectIssue | ProjectMergeRequest,
) -> str:
    state, suffix = compute_api_item_state_and_suffix(api_item)
    state_str = " ".join(state)

    return "[{ref}]({url}): {state}{title}{suffix}".format(
        ref=api_item.references["short"],
        state=state_str,
        title=api_item.title,
        url=api_item.web_url,
        suffix=suffix,
    )


def make_note_text(item: WorkUnit, item_formatter) -> str:
    return "{key_item}\n{rest}".format(
        key_item=item_formatter(
            item.key_item,
        ),
        rest="\n".join(
            "• {}".format(
                item_formatter(
                    api_item,
                )
            )
            for api_item in item.non_key_issues_and_mrs()
        ),
    )


class WorkboardUpdate:
    def __init__(self, oxr_gitlab: OpenXRGitlab):
        self.work = WorkUnitCollection()
        self.work.do_not_merge = DO_NOT_MERGE
        self.oxr_gitlab = oxr_gitlab
        self.proj = oxr_gitlab.main_proj
        self._log = logging.getLogger("WorkboardUpdate")
        self.board: dict[str, str | dict | list] = dict()

    def load_board(self, in_filename):
        self._log.info("Reading %s", in_filename)
        with open(in_filename, encoding="utf-8") as fp:
            self.board = json.load(fp)

        self._log.info("Parsing board loaded from %s", in_filename)
        parse_board(self.oxr_gitlab.main_proj, self.work, self.board)

    def search_issues(self, filter_out_refs: set[str]):
        # Grab all "Contractor:Approved" issues that are CTS related

        self._log.info("Handling GitLab issues")
        for issue in self.proj.issues.list(
            labels=[MainProjectLabels.CONTRACTOR_APPROVED],
            state="opened",
            iterator=True,
        ):
            self._handle_approved_issue(
                cast(gitlab.v4.objects.ProjectIssue, issue), filter_out_refs
            )

    def search_mrs(self, filter_out_refs: set[str]):
        # Grab all "Contractor:Approved" MRs as well as all
        # CTS ones (whether or not written
        # by contractor, as part of maintaining the cts)
        for mr in itertools.chain(
            *[
                self.proj.mergerequests.list(
                    labels=[label], state="opened", iterator=True
                )
                for label in (
                    MainProjectLabels.CONTRACTOR_APPROVED,
                    MainProjectLabels.CONFORMANCE_IMPLEMENTATION,
                )
            ]
        ):
            proj_mr = cast(gitlab.v4.objects.ProjectMergeRequest, mr)
            ref = get_short_ref(proj_mr)
            if ref in filter_out_refs:
                self._log.info(
                    "Skipping filtered out MR: %s: %s",
                    ref,
                    proj_mr.title,
                )
                continue

            labels = set(proj_mr.attributes["labels"])
            if not labels.intersection(REQUIRED_LABEL_SET):
                self._log.info(
                    "Skipping contractor approved but non-CTS MR: %s: %s  %s",
                    ref,
                    proj_mr.title,
                    proj_mr.attributes["web_url"],
                )
                continue

            if "candidate" in proj_mr.title.casefold():
                self._log.info(
                    "Skipping release candidate MR %s: %s", ref, proj_mr.title
                )
                continue

            self._log.info("GitLab MR Search: %s: %s", ref, proj_mr.title)
            self.work.add_refs(self.proj, [ref])

    def _handle_approved_issue(
        self, proj_issue: gitlab.v4.objects.ProjectIssue, filter_out_refs: set[str]
    ):
        ref = get_short_ref(proj_issue)
        if ref in filter_out_refs:
            self._log.info(
                "Skipping related MRs for: %s: %s",
                ref,
                proj_issue.title,
            )
            return

        labels = set(proj_issue.attributes["labels"])
        if not labels.intersection(REQUIRED_LABEL_SET):
            self._log.info(
                "Skipping contractor approved but non-CTS issue: %s: %s  %s",
                ref,
                proj_issue.title,
                proj_issue.attributes["web_url"],
            )
            return

        if ref in FILTER_OUT:
            self._log.info(
                "Skipping related MRs for: %s: %s",
                ref,
                proj_issue.title,
            )
            return

        refs = [ref]
        refs.extend(
            mr["references"]["short"]  # type: ignore
            for mr in proj_issue.related_merge_requests()
            if "candidate" not in mr["title"].casefold()
        )
        filtered_refs = [ref for ref in refs if ref not in filter_out_refs]
        if not filtered_refs:
            self._log.info(
                "No refs to consider left after filtering of: %s: %s",
                ref,
                proj_issue.title,
            )
            return

        self._log.info(
            "GitLab Issue Search: %s: %s  (refs: %s)",
            ref,
            proj_issue.title,
            ",".join(filtered_refs),
        )
        self.work.add_refs(self.proj, filtered_refs)

    def update_board(self) -> bool:
        self._log.info("Updating board with the latest data")
        return update_board(
            self.work,
            self.board,
            list_titles_to_skip_adding_to=[ListName.DONE],
            note_text_maker=lambda x: make_note_text(x, _make_api_item_text),
        )

    def write_board(self, out_filename):
        self._log.info("Writing output file %s", out_filename)
        with open(out_filename, "w", encoding="utf-8") as fp:
            json.dump(self.board, fp, indent=4)


def main(in_filename, out_filename):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()

    wbu = WorkboardUpdate(oxr_gitlab)
    wbu.load_board(in_filename)

    wbu.search_issues(FILTER_OUT)
    wbu.search_mrs(FILTER_OUT)

    updated = wbu.update_board()
    wbu.write_board(out_filename)

    if updated:
        log.info("Board contents have been changed.")
    else:
        log.info("No changes to board, output is the same data as input.")


if __name__ == "__main__":
    main(
        "Nullboard-1661530413298-OpenXR-CTS.nbx",
        "Nullboard-1661530413298-OpenXR-CTS-updated.nbx",
    )
