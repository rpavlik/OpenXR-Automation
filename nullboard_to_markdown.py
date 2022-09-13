#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

from dataclasses import dataclass, field
import json
import logging
from typing import Dict, List, cast


def _list_to_md(nb_list: Dict):
    lines = [f"* {nb_list['title']}"]
    _INDENT_WIDTH = 2
    current_indent = _INDENT_WIDTH
    for note in nb_list["notes"]:
        if note.get("raw"):
            lines.append(f"{' ' * _INDENT_WIDTH}* {note['text']}")
            current_indent = 2 * _INDENT_WIDTH
        else:
            lines.append(f"{' ' * current_indent}* {note['text']}")
    return "\n".join(lines)


def _nb_to_md(nb_board: Dict):
    chunks = [f"# {nb_board['title']}", ""]
    chunks.extend(_list_to_md(nb_list) for nb_list in nb_board["lists"])
    return "\n".join(chunks)


def main(in_filename, out_md_filename):
    logging.basicConfig(level=logging.INFO)

    log = logging.getLogger(__name__)

    log.info("Reading %s", in_filename)
    with open(in_filename, "r") as fp:
        existing_board = json.load(fp)

    log.info("Converting to Markdown/CommonMark outline")
    md_data = _nb_to_md(existing_board)

    log.info("Writing to %s", out_md_filename)
    with open(out_md_filename, "w", encoding="utf-8") as fp:
        fp.write(md_data)
        fp.write("\n")


if __name__ == "__main__":
    main(
        "Nullboard-1661545038-OpenXR-Release-Checklists.nbx",
        "Release-Checklists.md",
    )
