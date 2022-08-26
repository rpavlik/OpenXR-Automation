#!/usr/bin/env python3 -i
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

import re
import time
from typing import Any, Callable, Dict, List

from work_item_and_collection import WorkUnit, WorkUnitCollection

_REF_RE = re.compile(r"^([!#][0-9]+)\b.*")


class ListName:
    TODO = "TODO"
    DONE = "Done"
    DOING = "Coding"
    REVIEW = "Needs Review"


def guess_list(item: WorkUnit) -> str:
    if item.key_item.state in ("merged", "closed"):
        return ListName.DONE
    mr = item.get_key_item_as_mr()
    if mr:
        # merge request
        if mr.work_in_progress:
            return ListName.DOING
        if "Needs Action" in mr.labels:
            return ListName.DOING
    return ListName.TODO


def make_note_text(item: WorkUnit) -> str:
    return "{}: {} {}\n{}".format(
        item.ref,
        item.title,
        item.web_url,
        "\n".join(item.make_mr_url_list()),
    )


def make_empty_board(title):
    return {
        "format": 20190412,
        "title": title,
        "revision": 1,
        "id": int(time.time()),
        "lists": [],
        "history": [1],
    }


def update_board(
    work: WorkUnitCollection,
    board: Dict[str, Any],
    note_text_maker: Callable[[WorkUnit], str] = make_note_text,
    list_guesser: Callable[[WorkUnit], str] = guess_list,
):
    """Update the JSON data for a nullboard kanban board"""

    # the key item ref for all items used to update an existing note
    updated = set()

    # Go through all existing lists
    for notelist in board["lists"]:
        list_name = notelist["title"]
        print("In %s" % list_name)

        # For each item in those lists, extract the ref, and update the text if we can
        for note in notelist["notes"]:
            m = _REF_RE.match(note["text"])
            if not m:
                # Can't find a reference to an item at the start of the text
                print("Could not find an entry for '%s'" % note["text"])
                continue

            ref = m.group(1)
            print("Found note for item %s" % ref)
            item = work.items_by_ref.get(ref)
            if not item:
                # We don't know about this item
                continue

            new_text = note_text_maker(item)
            note["text"] = new_text
            print("Updated text")
            updated.add(item.ref)
            item.list_name = list_name

    # Decide what list to put the leftovers in
    all_new: Dict[str, List[Dict[str, str]]] = {}

    for item in work.items:
        if item.ref in updated:
            # we already did this
            continue
        print("New item for %s" % item.title)
        note = {"text": note_text_maker(item)}
        list_name = item.list_name or list_guesser(item)
        if list_name not in all_new:
            all_new[list_name] = []
        all_new[list_name].append(note)

    handled_lists = set()
    # Now go through the lists in the json and add the appropriate new items
    for notelist in board["lists"]:
        title = notelist["title"]
        if title in all_new:
            handled_lists.add(title)
            notelist["notes"].extend(all_new[title])
            print("Added new items to", title)

    # Add any missing lists
    missing_lists = set(all_new.keys()) - handled_lists
    for missing_title in missing_lists:
        print("Added new list", missing_title)
        board["lists"].append({"title": missing_title, "notes": all_new[missing_title]})

    board["revision"] = board["revision"] + 1
