#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import os
from dataclasses import dataclass
from enum import Enum

import gitlab
import gitlab.v4.objects
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

GITLAB_SERVER = "https://gitlab.khronos.org"

MAIN_PROJECT_NAME = "openxr/openxr"
MR_URL_BASE = f"{GITLAB_SERVER}/{MAIN_PROJECT_NAME}/-/merge_requests/"
ISSUE_URL_BASE = f"{GITLAB_SERVER}/{MAIN_PROJECT_NAME}/-/issues/"

OPERATIONS_PROJECT_NAME = "openxr/openxr-operations"

GROUP_NAME = "openxr"


@dataclass
class OpenXRGitlab:
    """Objects for interacting with the private OpenXR Gitlab repos."""

    gl: gitlab.Gitlab

    group: gitlab.v4.objects.Group | None
    main_proj: gitlab.v4.objects.Project
    operations_proj: gitlab.v4.objects.Project

    @classmethod
    def create(cls) -> "OpenXRGitlab":
        from dotenv import load_dotenv

        load_dotenv()

        url = os.environ.get("CI_API_V4_URL")
        if not url:
            url = os.environ.get("GL_URL")
        if url and "v4" in url:
            url = url.removesuffix("/api/v4")

        job_token = os.environ.get("CI_JOB_TOKEN")
        private_token = os.environ.get("GL_ACCESS_TOKEN")

        group: gitlab.v4.objects.Group | None = None

        if private_token:
            gl = gitlab.Gitlab(url=url, private_token=private_token)
            group = gl.groups.get(GROUP_NAME)
        else:
            gl = gitlab.Gitlab(url=url, job_token=job_token)

        main_proj = gl.projects.get(MAIN_PROJECT_NAME)
        operations_proj = gl.projects.get(OPERATIONS_PROJECT_NAME)
        return cls(
            gl=gl, group=group, main_proj=main_proj, operations_proj=operations_proj
        )


class ReferenceType(Enum):
    ISSUE = "#"
    MERGE_REQUEST = "!"

    @classmethod
    def parse_short_reference(cls, short_ref: str) -> "ReferenceType":
        return cls(short_ref[0])

    @classmethod
    def short_reference_to_type_and_num(
        cls, short_ref: str
    ) -> tuple["ReferenceType", int]:
        return cls.parse_short_reference(short_ref), int(short_ref[1:])


def get_short_ref(api_item: ProjectIssue | ProjectMergeRequest) -> str:
    return api_item.references["short"]
