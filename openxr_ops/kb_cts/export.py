#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
"""This exports the needs-review column to Markdown."""

import asyncio
import itertools
import logging

import kanboard

from ..gitlab import OpenXRGitlab
from ..kanboard_helpers import KanboardProject
from ..kb_defaults import CTS_PROJ_NAME
from ..kb_enums import InternalLinkRelation
from .collection import TaskCollection
from .stages import TaskColumn, TaskSwimlane
from .task import CTSTask
from .update import load_kb_cts

# Link types to omit from the exported text
_OMIT_LINK_TYPES = {
    InternalLinkRelation.IS_BLOCKED_BY,
    InternalLinkRelation.IS_FIXED_BY,
}


class CTSBoardExporter:

    def __init__(
        self,
        oxr_gitlab: OpenXRGitlab,
        kb_project_name: str,
    ):
        # self.base = CTSBoardUpdater(oxr_gitlab, kb_project_name, options=options)
        self.oxr_gitlab: OpenXRGitlab = oxr_gitlab
        self.kb_project_name: str = kb_project_name

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # these are populated later in prepare
        self.kb_project: KanboardProject
        self.task_collection: TaskCollection
        self.kb: kanboard.Client

    async def prepare(self):
        self.kb_project, self.task_collection = await load_kb_cts(
            self.kb_project_name, only_open=True
        )
        self.kb = self.kb_project.kb

    def process(self) -> str:
        contractor: list[CTSTask] = []
        noncontractor: list[CTSTask] = []
        for task_id in self.task_collection.mr_to_task_id.values():
            task = self.task_collection.tasks[task_id]
            if task.column == TaskColumn.NEEDS_REVIEW:
                if task.swimlane == TaskSwimlane.CTS_CONTRACTOR:
                    contractor.append(task)
                else:
                    noncontractor.append(task)

        def key_func(task: CTSTask):
            if task.task_dict is None:
                return 0
            return int(task.task_dict.get("position", 0))

        contractor.sort(key=key_func)
        noncontractor.sort(key=key_func)

        lines = ["* Needs Review: Contractor-Authored"]
        lines.extend(itertools.chain(*(self.mr_to_lines(mr) for mr in contractor)))
        lines.append("* Needs Review: Non-Contractor-Authored")
        lines.extend(itertools.chain(*(self.mr_to_lines(mr) for mr in noncontractor)))
        return "\n".join(lines)

    def mr_to_lines(self, mr_task: CTSTask, indent: str = "  ") -> list[str]:
        lines = [
            f"{indent}* [{mr_task.gitlab_link_title}]({mr_task.gitlab_link}) - {mr_task.title}"
        ]
        for link in mr_task.internal_links:
            if link.link_type in _OMIT_LINK_TYPES:
                continue
            other_task = self.task_collection.tasks[link.other_task_id]
            lines.append(
                f"{indent}  * {link.link_type.value} [{other_task.gitlab_link_title}]({other_task.gitlab_link}) - {other_task.title}"
            )
        return lines


async def main(
    project_name: str,
):
    logging.basicConfig(level=logging.INFO)

    oxr_gitlab = OpenXRGitlab.create()

    obj = CTSBoardExporter(
        oxr_gitlab=oxr_gitlab,
        kb_project_name=project_name,
    )

    await obj.prepare()
    output = obj.process()
    print(output)


if __name__ == "__main__":

    from dotenv import load_dotenv

    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_help = True
    parser.add_argument(
        "--project",
        type=str,
        help="Use the named project",
        default=CTS_PROJ_NAME,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Higher log level",
        default=False,
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(
        main(
            project_name=args.project,
        )
    )
