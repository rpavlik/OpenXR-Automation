#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2024, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import os
from dataclasses import dataclass

import gitlab
import gitlab.v4.objects

KHR_EXT_LABEL = "KHR_Extension"
VENDOR_EXT_LABEL = "Vendor_Extension"

MAIN_PROJECT_NAME = "openxr/openxr"

OPERATIONS_PROJECT_NAME = "openxr/openxr-operations"

GROUP_NAME = "openxr"


@dataclass
class OpenXRGitlab:
    """Objects for interacting with the private OpenXR Gitlab repos."""

    gl: gitlab.Gitlab

    group: gitlab.v4.objects.Group
    main_proj: gitlab.v4.objects.Project
    operations_proj: gitlab.v4.objects.Project

    @classmethod
    def create(cls):
        from dotenv import load_dotenv

        load_dotenv()

        gl = gitlab.Gitlab(
            url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
        )

        group = gl.groups.get(GROUP_NAME)
        main_proj = gl.projects.get(MAIN_PROJECT_NAME)
        operations_proj = gl.projects.get(OPERATIONS_PROJECT_NAME)
        return cls(
            gl=gl, group=group, main_proj=main_proj, operations_proj=operations_proj
        )
