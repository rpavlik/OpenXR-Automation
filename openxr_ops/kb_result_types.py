# Copyright 2025, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
from typing import Literal, TypedDict

IdOrFalse = int | Literal[False]


class TaskColor(TypedDict):
    """Type helper for nested map in return data from get_all_tasks."""

    name: str
    background: str
    border: str


class GetTaskResult(TypedDict):
    """
    Type helper for return data from getTask.

    Also return data list element from getAllTasks.
    """

    id: int
    title: str
    description: str
    date_creation: int
    color_id: str
    project_id: int
    column_id: int
    owner_id: int
    position: int
    is_active: int
    date_completed: int | None
    score: int
    date_due: int
    category_id: int | None
    creator_id: int
    date_modification: int
    reference: str
    date_started: int | None
    time_spent: int
    time_estimated: int
    swimlane_id: int
    date_moved: int
    recurrence_status: int
    recurrence_trigger: int
    recurrence_factor: int
    recurrence_timeframe: int
    recurrence_basedate: int
    recurrence_parent: int | None
    recurrence_child: int | None
    priority: int
    external_provider: str | None
    external_uri: str | None
    url: str

    color: TaskColor


GetAllTasksResult = Literal[False] | list[GetTaskResult]


class GetAllExternalTaskLinksResultElt(TypedDict):
    """Type helper for return data list element from getAllExternalTaskLinks."""

    id: int
    link_type: str
    dependency: str
    title: str
    url: str
    date_creation: int
    date_modification: int
    task_id: int
    creator_id: int
    creator_name: str | None
    creator_username: str | None
    dependency_label: str
    type: str


class InternalTaskLinkResult(TypedDict):
    """Type helper for return data from getTaskLinkById."""

    id: int
    link_id: int
    task_id: int
    opposite_task_id: int
    opposite_link_id: int
    label: str


class GetAllTaskLinksResultElt(TypedDict):
    """Type helper for return data list element from getAllTaskLinks."""

    id: int
    task_id: int
    label: str
    title: str
    is_active: int
    project_id: int
    column_id: int
    color_id: str
    date_completed: int | None
    date_started: int | None
    date_due: int
    task_time_spent: int | None
    task_time_estimated: int | None
    task_assignee_id: int
    task_assignee_username: str
    task_assignee_name: str
    column_title: str
    project_name: str


class GetColumnsResultElt(TypedDict):
    """Type helper for return data list element from getColumns."""

    id: int
    title: str
    position: int
    project_id: int
    task_limit: int
    description: str
    hide_in_dashboard: int  # acts like bool


class GetAllSwimlanesResultElt(TypedDict):
    """Type helper for return data list element from getAllSwimlanes."""

    id: int
    name: str
    position: int
    is_active: int
    project_id: int
    description: str
    task_limit: int


class GetAllCategoriesResultElt(TypedDict):
    """Type helper for return data list element from getAllCategories."""

    id: int
    name: str
    project_id: int
    description: str | None
    color_id: str


class GetAllUsersResultElt(TypedDict):
    """Type helper for return data list element from getAllUsers."""

    id: int
    username: str
    password: str | None
    is_ldap_user: int
    name: str
    email: str
    google_id: str | None
    github_id: str | None
    notifications_enabled: int
    timezone: str | None
    language: str | None
    disable_login_form: int
    twofactor_activated: int
    twofactor_secret: str | None
    token: str
    notifications_filter: int
    nb_failed_login: int
    lock_expiration_date: int
    gitlab_id: str | None
    role: str
    is_active: int
    avatar_path: str | None
    api_access_token: str | None
    filter: str | None
    theme: str
    oauth2_user_id: str  # int as str


class GetAllLinksResultElt(TypedDict):
    """Type helper for return data list element from getAllLinks."""

    id: int
    label: str
    opposite_id: int


class NameIdResultElt(TypedDict):
    """Generic type helper for things with a name and ID."""

    name: str
    id: int


class TitleIdResultElt(TypedDict):
    """Generic type helper for things with a title and ID."""

    title: str
    id: int


class ProjectUrlResult(TypedDict):
    board: str
    list: str


class ProjectResult(TypedDict):
    """
    Type helper for return data from getProject methods.

    More data is available than this.
    """

    name: str
    id: int
    url: ProjectUrlResult


GetProjectByIdResult = ProjectResult

GetProjectByNameResult = Literal[False] | ProjectResult
