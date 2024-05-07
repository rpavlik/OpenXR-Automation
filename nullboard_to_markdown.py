#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CommonMarkOutline:
    current_indent_level: int = 0
    lines: List[str] = field(default_factory=list)
    indent_size: int = 2

    def _indentation(self, level: Optional[int] = None) -> str:
        if level is None:
            level = self.current_indent_level
        return " " * (self.indent_size * level)

    def add_item(self, s: str, override_indent_level: Optional[int] = None):
        self.lines.append(f"{self._indentation(override_indent_level)}* {s}")

    def __str__(self):
        return "{}\n".format("\n".join(self.lines))


def _list_to_md(nb_list: Dict):
    outline = CommonMarkOutline()
    outline.add_item(nb_list["title"])
    outline.current_indent_level = 1

    for note in nb_list["notes"]:
        note_text: str = note["text"]
        if note.get("raw"):
            # Override indent level, to reliably "out-dent"
            outline.add_item(note_text, 1)

            # Bump up indent for following lines
            outline.current_indent_level = 2
            continue
        # Just a regular note. Split up the parts, though.
        parts = [part.strip("•").strip() for part in note_text.split("\n")]
        main_part = parts[0]
        outline.add_item(main_part)

        sub_parts = parts[1:]
        if sub_parts:
            outline.current_indent_level += 1
            for part in sub_parts:
                if part.strip():
                    outline.add_item(part)
            outline.current_indent_level -= 1

    return str(outline)


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
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input",
        type=str,
        nargs=1,
        default="Nullboard-1661545038-OpenXR-Release-Checklists.nbx",
        help="Input nullboard JSON file",
    )
    parser.add_argument(
        "output",
        type=str,
        nargs="?",
        help="Output .md filename: auto-generated if not specified",
    )
    args = parser.parse_args()

    input = args.input[0]
    if args.output:
        output = args.output
    else:
        output = input.replace(".nbx", ".md")
    main(
        input,
        output,
    )
