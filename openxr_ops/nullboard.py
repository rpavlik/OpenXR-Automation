#!/usr/bin/env python3
# Copyright 2022-2024, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
import logging
from collections.abc import Generator
from dataclasses import dataclass
from typing import Union


@dataclass
class NoteData:
    list_title: str
    subhead: str | None
    note_text: str

    @classmethod
    def iterate_notes(cls, board) -> Generator["NoteData", None, None]:
        log = logging.getLogger(f"{__name__}.{cls.__name__}.iterate_notes")
        for notelist in board["lists"]:
            list_title = notelist["title"]
            log.info("In list %s", list_title)
            subhead: str | None = None
            for note in notelist["notes"]:
                if note.get("raw"):
                    subhead = note["text"]
                    log.info("Subhead: %s : %s", list_title, subhead)
                    continue
                yield NoteData(
                    list_title=list_title,
                    subhead=subhead,
                    note_text=note["text"],
                )


NBNote = dict[str, Union[str, bool]]
NBNotes = list[NBNote]
