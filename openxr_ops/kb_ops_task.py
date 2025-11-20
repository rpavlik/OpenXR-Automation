import datetime
from dataclasses import dataclass
from typing import Any, Optional

import kanboard

from .ext_author_kind import CanonicalExtensionAuthorKind
from .gitlab import MR_URL_BASE
from .kanboard_helpers import KanboardProject
from .kb_ops_stages import TaskCategory, TaskColumn, TaskSwimlane, TaskTags
from .parse import extract_mr_number


@dataclass
class OperationsTaskFlags:
    """Booleans that come from presence/absence of tags."""

    api_frozen: bool
    initial_design_review_complete: bool
    initial_spec_review_complete: bool
    spec_support_review_comments_pending: bool
    editor_review_requested: bool

    khr_extension: bool
    multivendor_extension: bool
    single_vendor_extension: bool

    @classmethod
    def from_author_kind(
        cls,
        author_kind: CanonicalExtensionAuthorKind,
    ) -> "OperationsTaskFlags":

        return OperationsTaskFlags(
            api_frozen=False,
            initial_design_review_complete=False,
            initial_spec_review_complete=False,
            spec_support_review_comments_pending=False,
            editor_review_requested=(
                author_kind != CanonicalExtensionAuthorKind.SINGLE_VENDOR
            ),
            khr_extension=author_kind == CanonicalExtensionAuthorKind.KHR,
            multivendor_extension=author_kind == CanonicalExtensionAuthorKind.EXT,
            single_vendor_extension=author_kind
            == CanonicalExtensionAuthorKind.SINGLE_VENDOR,
        )

    @classmethod
    def from_task_tags_result(cls, task_tags: dict[str, str]) -> "OperationsTaskFlags":
        tags = set(task_tags.values())

        return cls(
            api_frozen=(TaskTags.API_FROZEN.value in tags),
            initial_design_review_complete=(
                TaskTags.INITIAL_DESIGN_REVIEW_COMPLETE.value in tags
            ),
            initial_spec_review_complete=(
                TaskTags.INITIAL_SPEC_REVIEW_COMPLETE.value in tags
            ),
            spec_support_review_comments_pending=(
                TaskTags.SPEC_SUPPORT_REVIEW_COMMENTS_PENDING.value in tags
            ),
            editor_review_requested=(TaskTags.EDITOR_REVIEW_REQUESTED.value in tags),
            khr_extension=(TaskTags.KHR_EXTENSION.value in tags),
            multivendor_extension=(TaskTags.MULTIVENDOR_EXTENSION.value in tags),
            single_vendor_extension=(TaskTags.SINGLE_VENDOR_EXTENSION.value in tags),
        )

    @classmethod
    async def fetch_tags_list(
        cls, kb: kanboard.Client, task_id: int
    ) -> "OperationsTaskFlags":
        tags_future = kb.get_task_tags_async(task_id=task_id)
        return cls.from_task_tags_result(await tags_future)

    def to_enum_list(self) -> list[TaskTags]:
        ret = []
        if self.api_frozen:
            ret.append(TaskTags.API_FROZEN)
        if self.initial_design_review_complete:
            ret.append(TaskTags.INITIAL_DESIGN_REVIEW_COMPLETE)
        if self.initial_spec_review_complete:
            ret.append(TaskTags.INITIAL_SPEC_REVIEW_COMPLETE)
        if self.spec_support_review_comments_pending:
            ret.append(TaskTags.SPEC_SUPPORT_REVIEW_COMMENTS_PENDING)
        if self.editor_review_requested:
            ret.append(TaskTags.EDITOR_REVIEW_REQUESTED)
        if self.khr_extension:
            ret.append(TaskTags.KHR_EXTENSION)
        if self.multivendor_extension:
            ret.append(TaskTags.MULTIVENDOR_EXTENSION)
        if self.single_vendor_extension:
            ret.append(TaskTags.SINGLE_VENDOR_EXTENSION)
        return ret

    def to_string_list(self) -> list[str]:
        return [tag.value for tag in self.to_enum_list()]


@dataclass
class OperationsTaskBase:
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
    ) -> "OperationsTaskBase":
        """
        Interpret a task dictionary from e.g. get_all_tasks.

        Needs the kb_project to decode the column and swimlane.

        Unable to populate the main MR or any more advanced properties.
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
class OperationsTask(OperationsTaskBase):
    """Like OperationsTaskBase but this requires additional queries"""

    main_mr: Optional[int]

    ext_links_list: list[dict[str, Any]]

    flags: Optional[OperationsTaskFlags]

    tags_dict: dict[str, Any]

    @classmethod
    async def from_base_with_more_data(
        cls, base: OperationsTaskBase, kb: kanboard.Client
    ) -> "OperationsTask":
        ext_links_future = kb.get_all_external_task_links_async(task_id=base.task_id)
        tags_future = kb.get_task_tags_async(task_id=base.task_id)

        main_mr: Optional[int] = None
        ext_links = await ext_links_future
        for ext_link in ext_links:
            main_mr = extract_mr_number(ext_link["url"])
            if main_mr is not None:
                break

        tags = await tags_future
        flags = OperationsTaskFlags.from_task_tags_result(tags)

        return cls(
            task_id=base.task_id,
            column=base.column,
            swimlane=base.swimlane,
            category=base.category,
            title=base.title,
            description=base.description,
            task_dict=base.task_dict,
            main_mr=main_mr,
            ext_links_list=ext_links,
            flags=flags,
            tags_dict=tags,
        )

    @classmethod
    async def from_task_dict_with_more_data(
        cls, kb_project: KanboardProject, task: dict[str, Any]
    ) -> "OperationsTask":
        base = OperationsTaskBase.from_task_dict(kb_project, task)
        return await cls.from_base_with_more_data(base=base, kb=kb_project.kb)

    @classmethod
    async def from_task_id(
        cls, kb_project: KanboardProject, task_id: int
    ) -> "OperationsTask":
        task_dict = await kb_project.kb.get_task(task_id=task_id)
        return await cls.from_task_dict_with_more_data(
            task=task_dict, kb_project=kb_project
        )


@dataclass
class OperationsTaskCreationData:
    main_mr: int
    column: TaskColumn
    swimlane: TaskSwimlane
    title: str
    description: str

    flags: Optional[OperationsTaskFlags]
    issue_url: Optional[str] = None

    category: Optional[TaskCategory] = None

    date_started: Optional[datetime.datetime] = None

    async def create_task(self, kb_project: KanboardProject) -> Optional[int]:
        swimlane_id = self.swimlane.to_swimlane_id(kb_project)
        if swimlane_id is None:
            return None

        column_id = self.column.to_column_id(kb_project)
        if column_id is None:
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

        mr_url = f"{MR_URL_BASE}{self.main_mr}"
        kb = kb_project.kb

        task_id = await kb.create_task_async(
            title=self.title,
            project_id=kb_project.project_id,
            description=self.description,
            swimlane_id=swimlane_id,
            column_id=column_id,
            color_id="grey",
            # gl_url=mr_url,
            category_id=category_id,
            tags=tags,
            date_started=date_started,
        )

        await kb.create_external_task_link_async(
            task_id=task_id,
            url=mr_url,
            type="weblink",
            dependency="related",
            title=f"Merge Request !{self.main_mr}",
        )

        if self.issue_url is not None:
            await kb.create_external_task_link_async(
                task_id=task_id,
                url=self.issue_url,
                type="weblink",
                dependency="related",
                title=f"Original Operations Issue",
            )

        return task_id
