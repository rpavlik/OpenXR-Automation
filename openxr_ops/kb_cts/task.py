import datetime
import logging
from dataclasses import dataclass
from typing import Any, Optional

import kanboard

from ..gitlab import ISSUE_URL_BASE, MR_URL_BASE
from ..kanboard_helpers import KanboardProject, LinkIdMapping
from ..kb_enums import InternalLinkRelation
from ..kb_links import InternalLinkData
from ..parse import extract_issue_number, extract_mr_number
from .stages import TaskCategory, TaskColumn, TaskSwimlane, TaskTags


@dataclass
class CTSTaskFlags:
    """Booleans that come from presence/absence of tags."""

    blocked_on_spec: bool = False
    contractor_reviewed: bool = False

    @classmethod
    def from_task_tags_result(cls, task_tags: dict[str, str]) -> "CTSTaskFlags":
        tags = set(task_tags.values())

        return cls(
            blocked_on_spec=(TaskTags.BLOCKED_ON_SPEC.value in tags),
            contractor_reviewed=(TaskTags.CONTRACTOR_REVIEWED.value in tags),
        )

    @classmethod
    async def fetch_tags_list(cls, kb: kanboard.Client, task_id: int) -> "CTSTaskFlags":
        tags_future = kb.get_task_tags_async(task_id=task_id)
        return cls.from_task_tags_result(await tags_future)

    def to_enum_list(self) -> list[TaskTags]:
        ret = []
        if self.blocked_on_spec:
            ret.append(TaskTags.BLOCKED_ON_SPEC)
        if self.contractor_reviewed:
            ret.append(TaskTags.CONTRACTOR_REVIEWED)
        return ret

    def to_string_list(self) -> list[str]:
        return [tag.value for tag in self.to_enum_list()]


@dataclass
class CTSTaskBase:
    task_id: int
    column: TaskColumn
    swimlane: TaskSwimlane
    category: Optional[TaskCategory]
    title: str
    description: str
    task_dict: Optional[dict]

    @property
    def url(self) -> Optional[str]:
        if self.task_dict:
            return self.task_dict["url"]
        return None

    @classmethod
    def from_task_dict(
        cls, kb_project: KanboardProject, task: dict[str, Any]
    ) -> "CTSTaskBase":
        """
        Interpret a task dictionary from e.g. get_all_tasks.

        Needs the kb_project to decode the column and swimlane.

        Unable to populate internal or external links, or any more advanced properties.
        """

        task_id = int(task["id"])
        column_id = int(task["column_id"])
        column: TaskColumn = TaskColumn.from_column_id(kb_project, col_id=column_id)
        title: str = task["title"]
        description: str = task["description"]

        swimlane_id = int(task["swimlane_id"])
        swimlane: TaskSwimlane = TaskSwimlane.from_swimlane_id(
            kb_project, swimlane_id=int(swimlane_id)
        )
        category_id: Optional[int] = None
        category: Optional[TaskCategory] = None
        if task["category_id"] is not None:
            category_id = int(task["category_id"])
            category = TaskCategory.from_category_id_maybe_none(kb_project, category_id)
        return cls(
            task_id=task_id,
            column=column,
            swimlane=swimlane,
            category=category,
            title=title,
            description=description,
            task_dict=task,
        )


@dataclass
class CTSTask(CTSTaskBase):
    """Like CTSTaskBase but this requires additional queries"""

    mr_num: Optional[int]
    """MR number. If None, then issue_num must not be None."""

    issue_num: Optional[int]
    """Issue number. If None, then mr_num must not be None."""

    internal_links: list[InternalLinkData]
    """Parsed internal link data"""

    ext_links_list: list[dict[str, Any]]
    """Raw external links data from API"""

    internal_links_list: list[dict[str, Any]]
    """Raw internal links data from API"""

    flags: Optional[CTSTaskFlags]

    tags_dict: dict[str, Any]
    """Raw tags data from API."""

    def is_mr(self):
        return self.mr_num is not None

    def is_issue(self):
        return self.issue_num is not None

    @property
    def gitlab_link(self) -> Optional[str]:
        if self.is_mr():
            return f"{MR_URL_BASE}{self.mr_num}"
        if self.is_issue():
            return f"{ISSUE_URL_BASE}{self.issue_num}"
        return None

    @property
    def gitlab_link_title(self) -> Optional[str]:
        if self.is_mr():
            return f"MR !{self.mr_num}"
        if self.is_issue():
            return f"Issue #{self.issue_num}"
        return None

    async def refresh_internal_links(self, kb: kanboard.Client):
        int_links_future = kb.get_all_task_links_async(task_id=self.task_id)
        self.internal_links_list = await int_links_future
        self.internal_links = InternalLinkData.parse_internal_links(
            self.task_id, self.internal_links_list
        )

    @classmethod
    async def from_base_with_more_data(
        cls, base: CTSTaskBase, kb: kanboard.Client
    ) -> "CTSTask":
        ext_links_future = kb.get_all_external_task_links_async(task_id=base.task_id)
        tags_future = kb.get_task_tags_async(task_id=base.task_id)
        int_links_future = kb.get_all_task_links_async(task_id=base.task_id)

        mr_num: Optional[int] = None
        issue_num: Optional[int] = None
        ext_links = await ext_links_future
        for ext_link in ext_links:
            mr_num = extract_mr_number(ext_link["url"])
            if mr_num is not None:
                break
            issue_num = extract_issue_number(ext_link["url"])
            if issue_num is not None:
                break

        if mr_num is None and issue_num is None:
            raise RuntimeError(
                "No external links are an issue or MR! "
                + " ".join((ext_link["url"] for ext_link in ext_links))
            )
        tags = await tags_future
        flags = CTSTaskFlags.from_task_tags_result(tags)

        int_links = await int_links_future

        return cls(
            task_id=base.task_id,
            column=base.column,
            swimlane=base.swimlane,
            category=base.category,
            title=base.title,
            description=base.description,
            task_dict=base.task_dict,
            mr_num=mr_num,
            issue_num=issue_num,
            internal_links=InternalLinkData.parse_internal_links(
                base.task_id, int_links
            ),
            ext_links_list=ext_links,
            internal_links_list=int_links,
            flags=flags,
            tags_dict=tags,
        )

    @classmethod
    async def from_task_dict_with_more_data(
        cls, kb_project: KanboardProject, task: dict[str, Any]
    ) -> "CTSTask":
        base = CTSTaskBase.from_task_dict(kb_project, task)
        return await cls.from_base_with_more_data(base=base, kb=kb_project.kb)

    @classmethod
    async def from_task_id(cls, kb_project: KanboardProject, task_id: int) -> "CTSTask":
        task_dict = await kb_project.kb.get_task_async(task_id=task_id)
        return await cls.from_task_dict_with_more_data(
            task=task_dict, kb_project=kb_project
        )


@dataclass
class CTSTaskCreationData:
    mr_num: Optional[int]
    issue_num: Optional[int]

    column: TaskColumn
    swimlane: TaskSwimlane
    title: str
    description: str

    flags: Optional[CTSTaskFlags]

    category: Optional[TaskCategory] = None

    date_started: Optional[datetime.datetime] = None

    @property
    def gitlab_link(self) -> Optional[str]:
        if self.mr_num is not None:
            return f"{MR_URL_BASE}{self.mr_num}"
        if self.issue_num is not None:
            return f"{ISSUE_URL_BASE}{self.issue_num}"
        return None

    @property
    def gitlab_link_title(self) -> Optional[str]:
        if self.mr_num is not None:
            return f"MR !{self.mr_num}"
        if self.issue_num is not None:
            return f"Issue #{self.issue_num}"
        return None

    async def create_task(self, kb_project: KanboardProject) -> Optional[int]:
        log = logging.getLogger(f"{__name__}.{self.__class__.__name__}.create_task")
        swimlane_id = self.swimlane.to_swimlane_id(kb_project)
        if swimlane_id is None:
            log.error("Could not find ID for swimlane %s", self.swimlane.value)
            return None

        column_id = self.column.to_column_id(kb_project)
        if column_id is None:
            log.error("Could not find ID for column %s", self.column.value)
            return None

        category_id: Optional[int] = None
        if self.category is not None:
            category_id = self.category.to_category_id(kb_project)

        tags: Optional[list[str]] = None
        if self.flags is not None:
            tags = self.flags.to_string_list()

        date_started: Optional[str] = None
        if self.date_started is not None:
            date_started = self.date_started.strftime("%Y-%m-%d %H:%M")

        kb = kb_project.kb

        task_id = await kb.create_task_async(
            title=self.title,
            project_id=kb_project.project_id,
            description=self.description,
            swimlane_id=swimlane_id,
            column_id=column_id,
            color_id="white",
            category_id=category_id,
            tags=tags,
            date_started=date_started,
        )
        if not task_id:
            raise RuntimeError("Failed to create task!")

        main_url = self.gitlab_link
        if main_url is not None:
            url_title = self.gitlab_link_title
            assert url_title is not None
            await kb.create_external_task_link_async(
                task_id=task_id,
                url=main_url,
                type="weblink",
                dependency="related",
                title=url_title,
            )

        return task_id


async def create_internal_task_link_by_task_id(
    kb: kanboard.Client,
    link_mapping: LinkIdMapping,
    task_id: int,
    relation: InternalLinkRelation,
    opposite_task_id: int,
):
    await kb.create_task_link_async(
        task_id=task_id,
        opposite_task_id=opposite_task_id,
        link_id=relation.to_link_id(link_mapping),
    )
