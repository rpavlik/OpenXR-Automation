#!/usr/bin/env python3
# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import os
from dataclasses import dataclass

import gitlab
import gitlab.v4.objects
from requests_cache import Optional

KHR_EXT_LABEL = "KHR_Extension"
VENDOR_EXT_LABEL = "Vendor_Extension"
EXT_LABEL = "Extension"
OUTSIDE_IP_ZONE_LABEL = "Outside IP-Zone"

MAIN_PROJECT_NAME = "openxr/openxr"

OPERATIONS_PROJECT_NAME = "openxr/openxr-operations"

GROUP_NAME = "openxr"


@dataclass
class OpenXRGitlab:
    """Objects for interacting with the private OpenXR Gitlab repos."""

    gl: gitlab.Gitlab

    group: Optional[gitlab.v4.objects.Group]
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

        group: Optional[gitlab.v4.objects.Group] = None

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
