#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
import enum


class CanonicalExtensionAuthorKind(enum.Enum):
    KHR = "KHR"
    EXT = "EXT"
    SINGLE_VENDOR = "SINGLE_VENDOR"
