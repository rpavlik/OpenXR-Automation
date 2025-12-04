#!/bin/sh
# Copyright 2024-2025, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

# Takes markdown links and just puts both the text and URL instead.
# Good for copy/paste of `python3 -m openxr_ops.kb_cts.export` output into Zoom meeting chat.

sed -i -E 's/\[([^]]+)\]\(([^)]+)\)/\1 \2/g' "$@"
