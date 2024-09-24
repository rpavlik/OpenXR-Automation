#!/bin/sh
# Copyright 2024, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

# Takes markdown links and just puts both the text and URL instead.
# Good for copy/paste of nullboard_to_markdown.py output into Zoom meeting chat.

sed -i -E 's/\[([^]]+)\]\(([^)]+)\):/\1 \2/g' "$@"
