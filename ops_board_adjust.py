#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""
Process the extension tracking topic, auto-updating where applicable.

* Syncs some labels from GitLab
  * "Binary Strings Released" on GitLab implies "Strings Released" on Kanboard
* Moves tasks to "PENDING_APPROVALS_AND_MERGE" once the MR is merged
* Closes "PENDING_APPROVALS_AND_MERGE" tasks once the release occurs
  * This part did not always work right in the old code.
"""

import asyncio
import logging
from collections.abc import Awaitable
from copy import deepcopy
from typing import Any

import gitlab
import gitlab.v4.objects
import kanboard

from kb_ops_migrate import load_kb_ops
from openxr_ops.gitlab import OpenXRGitlab
from openxr_ops.kanboard_helpers import KanboardProject
from openxr_ops.kb_defaults import REAL_PROJ_NAME, USERNAME
from openxr_ops.kb_ops.collection import TaskCollection
from openxr_ops.kb_ops.gitlab import update_flags
from openxr_ops.kb_ops.stages import TaskColumn
from openxr_ops.kb_ops.task import OperationsTask


class OpsBoardProcessing:
    def __init__(
        self,
        main_project: gitlab.v4.objects.Project,
        kb_project_name: str,
        dry_run: bool,
    ):
        self.main_proj = main_project
        self.kb_project_name: str = kb_project_name
        self.dry_run: bool = dry_run

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
        self.title: str | None = None

        self.username = USERNAME
        self.futures: list[Awaitable[Any]] = []

        # these are populated later in prepare
        self.kb_project: KanboardProject
        self.task_collection: TaskCollection
        self.kb: kanboard.Client

    async def prepare(self):
        self.kb_project, self.task_collection = await load_kb_ops(self.kb_project_name)
        self.kb = self.kb_project.kb

    def log_title(self):
        if self.title is not None:
            log = logging.getLogger(__name__)

            log.info("%s", self.title)
            self.title = None

    def handle_merges(
        self,
        task: OperationsTask,
        mr: gitlab.v4.objects.ProjectMergeRequest,
    ):
        log = logging.getLogger(__name__)

        # Auto move to release pending upon merge.
        if mr.state == "merged" and task.column != TaskColumn.INACTIVE:
            sha = mr.attributes["merge_commit_sha"]

            if sha in self.commits_in_last_release:
                self.log_title()
                log.info("Closing - found in release.")

                async def close_released():
                    user_id = self.kb_project.username_to_id[self.username]
                    comment = f"Closing this task: merge commit {sha} found in changes preceding {self.latest_release_ref}."
                    if self.dry_run:
                        log.info(
                            "Would add this comment: '%s' and close task.", comment
                        )
                        return
                    await self.kb.create_comment_async(
                        task_id=task.task_id, user_id=user_id, content=comment
                    )

                    await self.kb.close_task_async(task_id=task.task_id)

                self.futures.append(close_released())

            elif task.column != TaskColumn.PENDING_APPROVALS_AND_MERGE:
                self.log_title()
                log.info("Moving to pending, has been merged")

                async def move_to_pending():
                    if self.dry_run:
                        log.info(
                            "Would move from column '%s' to '%s'.",
                            str(task.column),
                            str(TaskColumn.PENDING_APPROVALS_AND_MERGE),
                        )
                        return
                    await self.kb.move_task_position_async(
                        project_id=self.kb_project.project_id,
                        task_id=task.task_id,
                        column_id=TaskColumn.PENDING_APPROVALS_AND_MERGE.to_required_column_id(
                            self.kb_project
                        ),
                        position=0,
                        swimlane_id=task.swimlane.to_required_swimlane_id(
                            self.kb_project
                        ),
                    )

                self.futures.append(move_to_pending())

            else:
                log.info(
                    "%s - Commit is merged in %s, column is %s",
                    mr.attributes["web_url"],
                    sha,
                    str(task.column),
                )

    def process_task(self, task: OperationsTask, mr_num: int):
        log = logging.getLogger(__name__)

        self.title = f"Task: {task.task_id} aka <{task.url}>: {task.title}"

        # Find MR
        mr = self.main_proj.mergerequests.get(mr_num)
        self.title = (
            f"{self.title}: main MR: {mr.references['short']} aka <{mr.web_url}>"
        )

        self.handle_merges(task, mr)
        assert task.flags
        flags = deepcopy(task.flags)
        update_flags(flags, mr)
        if flags != task.flags:
            self.log_title()
            new_tags = flags.to_string_list()
            log.info("%s", repr(new_tags))

            async def update_tags():
                if self.dry_run:
                    log.info(
                        "Would update tags from '%s' to '%s'.",
                        str(list(sorted(task.tags_dict.values()))),
                        str(list(sorted(new_tags))),
                    )
                    return

                await self.kb.update_task_async(id=task.task_id, tags=new_tags)

            self.futures.append(update_tags())

    def process_all(self):
        for mr_num, task_id in self.task_collection.mr_to_task_id.items():
            task = self.task_collection.get_task_by_id(task_id)
            assert task
            self.process_task(task, mr_num)

    async def finish_processing(self):
        await asyncio.gather(*self.futures)
        self.futures = []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    from dotenv import load_dotenv

    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser(add_help=True)

    parser.add_argument(
        "--project",
        type=str,
        help="Update the named project",
        default=REAL_PROJ_NAME,
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Do not actually make any changes",
        default=False,
    )

    args = parser.parse_args()

    oxr_gitlab = OpenXRGitlab.create()

    app = OpsBoardProcessing(oxr_gitlab.main_proj, args.project, dry_run=args.dry_run)

    async def wrapper():
        await app.prepare()
        app.process_all()
        await app.finish_processing()

    asyncio.run(wrapper())
