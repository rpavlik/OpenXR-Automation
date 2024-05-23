#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""
Process the operations board, auto-updating where applicable.

* Ensures that each issue has exactly one column status label.
* Applies any missing labels it knows about
  * mainly that needs-revision implies initial-review-complete
* Moves issues to "release pending" once the MR is merged
* Closes "release pending" issues once the release occurs
  * This part does not always work right.
"""

import logging
import re
from typing import Optional, cast

import gitlab
import gitlab.v4.objects

from openxr_ops.checklists import ColumnName
from openxr_ops.gitlab import OpenXRGitlab

_FIND_MR_RE = re.compile(
    r"Main extension MR:\s*((?P<proj>openxr|openxr/openxr)!|https://gitlab.khronos.org/openxr/openxr/-/merge_requests/)(?P<num>[0-9]+)"
)

_ISSUE_TITLE_FIXING = re.compile(r"Release [Cc]hecklist for ")


class OpsBoardProcessing:
    def __init__(
        self,
        ops_project: gitlab.v4.objects.Project,
        main_project: gitlab.v4.objects.Project,
    ):
        self.ops_proj = ops_project
        self.main_proj = main_project
        tags = list(
            self.main_proj.tags.list(
                search="^release-1", order_by="version", iterator=True
            )
        )
        self.latest_release_ref = tags[0].attributes["name"]
        self.previous_release_ref = tags[1].attributes["name"]
        self.commits_in_last_release = [
            commit.id
            for commit in self.main_proj.commits.list(
                ref_name=f"{self.previous_release_ref}..{self.latest_release_ref}",
                iterator=True,
            )
        ]
        self.title: Optional[str] = None

    def log_title(self):
        if self.title is not None:
            log = logging.getLogger(__name__)

            log.info("%s", self.title)
            self.title = None

    def process_issue_with_mr(
        self,
        issue: gitlab.v4.objects.ProjectIssue,
        mr: gitlab.v4.objects.ProjectMergeRequest,
        column: ColumnName,
    ) -> ColumnName:
        log = logging.getLogger(__name__)

        # Auto move to release pending upon merge.
        if mr.state == "merged" and column not in (
            ColumnName.NEEDS_OTHER,
            ColumnName.INACTIVE,
        ):
            sha = mr.attributes["merge_commit_sha"]

            if sha in self.commits_in_last_release:
                self.log_title()
                log.info("Closing - found in release.")
                issue.state_event = "close"
                issue.save()

            elif column != ColumnName.RELEASE_PENDING:
                self.log_title()
                log.info("Marking as release pending")
                column = ColumnName.RELEASE_PENDING

            else:
                log.info(
                    "%s - Commit is merged in %s, column is %s",
                    mr.attributes["web_url"],
                    sha,
                    str(column),
                )

        return column

    def process_open_issue(self, issue: gitlab.v4.objects.ProjectIssue):
        log = logging.getLogger(__name__)
        title = issue.attributes["title"]

        self.title = (
            f"Issue: {issue.references['short']} aka <{issue.web_url}>: {title}"
        )

        # Find MR
        mr = None
        desc = issue.description
        if desc:
            match_iter = _FIND_MR_RE.finditer(desc)
            match = next(match_iter, None)
            if match:
                mr_num = int(match.group("num"))
                mr = self.main_proj.mergerequests.get(mr_num)
                self.title = f"{self.title}: main MR: {mr.references['short']} aka <{mr.web_url}>"
        else:
            self.log_title()
            log.warning("No description in this issue")

        # Tidy up the title.
        new_title = _ISSUE_TITLE_FIXING.sub("", title)
        if new_title != title:
            self.log_title()
            log.info("Updating title: %s", new_title)
            issue.title = new_title
            issue.save()

        # Figure out the furthest-along column
        labels = issue.attributes["labels"]
        column = ColumnName.from_labels(labels)
        if column is None:
            column = ColumnName.INITIAL_COMPOSITION

        if mr is not None:
            column = self.process_issue_with_mr(issue, mr, column)
        else:
            self.log_title()
            log.warning("No main MR found?")

        new_labels = column.compute_new_labels(labels)

        if new_labels != labels:
            self.log_title()
            log.info("%s", repr(new_labels))
            issue.labels = new_labels
            issue.save()

    def process_all(self):
        for issue in self.ops_proj.issues.list(state="opened", iterator=True):
            self.process_open_issue(cast(gitlab.v4.objects.ProjectIssue, issue))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    oxr_gitlab = OpenXRGitlab.create()

    app = OpsBoardProcessing(oxr_gitlab.operations_proj, oxr_gitlab.main_proj)
    app.process_all()
