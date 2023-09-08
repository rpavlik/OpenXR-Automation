#!/usr/bin/env python3
# Copyright 2022-2023, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>
"""Process the operations board."""

from enum import Enum
import logging
import os
from typing import Iterable, Optional, cast
import re

import gitlab
import gitlab.v4.objects

_FIND_MR_RE = re.compile(
    r"Main extension MR:\s*((?P<proj>openxr|openxr/openxr)!|https://gitlab.khronos.org/openxr/openxr/-/merge_requests/)(?P<num>[0-9]+)"
)

_ISSUE_TITLE_FIXING = re.compile(r"Release [Cc]hecklist for ")


class ColumnName(Enum):
    """Board columns and their associated labels."""

    INACTIVE = "status:Inactive"
    INITIAL_COMPOSITION = "status:InitialComposition"
    NEEDS_CHAMPION_APPROVAL_OR_RATIFICATION = (
        "status:NeedsChampionApprovalOrRatification"
    )
    NEEDS_OTHER = "status:NeedsOther"
    NEEDS_REVIEW = "status:NeedsReview"
    NEEDS_REVISION = "status:NeedsRevision"
    RELEASE_PENDING = "status:ReleasePending"

    @classmethod
    def from_labels(cls, labels: Iterable[str]) -> Optional["ColumnName"]:
        result = None
        label_set = set(labels)
        for column in cls:
            if column.value in label_set:
                # only keep the "highest"
                result = column
        return result

    def compute_new_labels(self, labels: list[str]) -> list[str]:
        column_labels = {x.value for x in ColumnName}

        # Remove all column labels except the one we want.
        new_labels = [x for x in labels if x == self.value or x not in column_labels]
        if self.value not in new_labels:
            # Add the one we want if it wasn't already there
            new_labels.append(self.value)
        return new_labels


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
                issue.state = "closed"
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
        match_iter = _FIND_MR_RE.finditer(issue.description)
        match = next(match_iter, None)
        if match:
            mr_num = int(match.group("num"))
            mr = self.main_proj.mergerequests.get(mr_num)
            self.title = (
                self.title + f": main MR: {mr.references['short']} aka <{mr.web_url}>"
            )

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
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )
    ops_proj = gl.projects.get("openxr/openxr-operations")
    main_proj = gl.projects.get("openxr/openxr")

    app = OpsBoardProcessing(ops_proj, main_proj)
    app.process_all()
