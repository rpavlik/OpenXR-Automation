#!/usr/bin/env python3 -i
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

import logging
import re
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple, Union

import gitlab
import gitlab.v4.objects
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

from work_item_and_collection import WorkUnit, WorkUnitCollection

_REF_RE = re.compile(r"([!#][0-9]+)\b")


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


def _make_api_item_text(api_item: Union[ProjectIssue, ProjectMergeRequest]) -> str:
    state = ""
    if api_item.state == "closed":
        state = "(CLOSED) "
    elif api_item.state == "merged":
        state = "(MERGED) "
    return "[{ref}]({url}): {state}{title}".format(
        ref=api_item.references["short"],
        title=api_item.title,
        state=state,
        url=api_item.web_url,
    )


def make_item_bullet(api_item: Union[ProjectIssue, ProjectMergeRequest]) -> str:
    return "• {}".format(_make_api_item_text(api_item))


def make_note_text(item: WorkUnit) -> str:
    return "{key_item}\n{rest}".format(
        key_item=_make_api_item_text(item.key_item),
        rest="\n".join(
            make_item_bullet(api_item) for api_item in item.non_key_issues_and_mrs()
        ),
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


def _iterate_notes(board) -> Generator[Tuple[Dict, Dict], None, None]:
    log = logging.getLogger(__name__)
    # Go through all existing lists
    for notelist in board["lists"]:
        list_name = notelist["title"]
        log.info("In list %s" % list_name)

        # For each item in those lists, extract the ref, and update the text if we can
        for note in notelist["notes"]:
            yield notelist, note


def parse_board(
    proj: gitlab.v4.objects.Project,
    work: WorkUnitCollection,
    board: Dict[str, Any],
):
    """Populate a work item collection from a nullboard export."""
    log = logging.getLogger(__name__)

    for notelist, note in _iterate_notes(board):

        # For each item in those lists, extract the ref, and update the text if we can
        refs = _REF_RE.findall(note["text"])
        log.debug("Found these refs in a note: %s", str(refs))
        if not refs:
            log.debug("Could not find any refs in '%s'", note["text"])
            # Can't find a reference to an item in the text
            continue

        item = work.add_or_get_item_for_refs(proj, refs)
        if not item.list_name:
            # Set list
            item.list_name = notelist["title"]


_DELETION_MARKER = "delete"


def mark_note_for_deletion(note: Dict[str, Union[str, bool]]):
    note[_DELETION_MARKER] = True


def remove_marked_for_deletion(board: Dict[str, Any]):

    log = logging.getLogger(__name__)
    for notelist in board["lists"]:
        newlist = [note for note in notelist["notes"] if _DELETION_MARKER not in note]
        oldlen = len(notelist["notes"])
        if len(newlist) != oldlen:
            log.info(
                "Removing %d notes from %s that were marked for deletion",
                oldlen - len(newlist),
                notelist["title"],
            )
            notelist["notes"] = newlist


def update_board(
    work: WorkUnitCollection,
    board: Dict[str, Any],
    note_text_maker: Callable[[WorkUnit], str] = make_note_text,
    list_guesser: Callable[[WorkUnit], str] = guess_list,
    list_titles_to_skip_adding_to=None,
    project: Optional[gitlab.v4.objects.Project] = None,
):
    """Update the JSON data for a nullboard kanban board"""
    log = logging.getLogger(__name__)

    if project is not None:
        # First merge stuff for completeness
        parse_board(project, work, board)

    # the refs for all items used to update an existing note
    existing: Set[str] = set()

    deleted_any = False
    # Go through all existing lists
    for notelist in board["lists"]:
        list_name = notelist["title"]
        log.info("Updating in list %s", list_name)

        # For each item in those lists, extract the ref, and update the text if we can
        for note in notelist["notes"]:
            refs = _REF_RE.findall(note["text"])
            log.debug("Extracted refs: %s", str(refs))
            if not refs:
                # Can't find a reference to an item in the text
                continue

            items = work.get_items_for_refs(refs)
            if not items:
                # Can't find a match for any references
                log.debug("Could not find an entry for '%s'", ",".join(refs))
                continue

            item = work.merge_many_workunits(items)
            item_refs = set(item.refs())
            num_refs = len(item_refs)
            num_existing_intersection = len(existing.intersection(item_refs))
            if num_refs == num_existing_intersection:
                # This is fully handled in an existing card
                log.info("Marking a card for deletion as it is a duplicate")
                deleted_any = True
                mark_note_for_deletion(note)
                continue
            if num_existing_intersection > 0:
                # If we had run "parse" beforehand, this wouldn't happen, because we'd
                # already have merged all refs into a single item,
                # intersection would be complete or empty
                log.warning(
                    "Found %d refs that are duplicates of earlier-parsed cards! You "
                    "may want to pass project= to update_board() to be able to merge "
                    "and clean dupes",
                    num_existing_intersection,
                )

            existing.update(item.refs())
            item.list_name = list_name

            new_text = note_text_maker(item)
            if note["text"] != new_text:
                log.info("Updated text for %s", refs[0])
                note["text"] = new_text

    if deleted_any:
        remove_marked_for_deletion(board)

    # Decide what list to put the leftovers in
    all_new: Dict[str, List[Dict[str, str]]] = {}

    for item in work.items:
        if item.ref in existing:
            # we already did this
            continue
        log.info("New item for %s" % item.title)
        note = {"text": note_text_maker(item)}
        list_name = item.list_name or list_guesser(item)
        if list_name not in all_new:
            all_new[list_name] = []
        all_new[list_name].append(note)

    handled_lists = set()

    # If we have some lists to skip, just say we already handled them.
    if list_titles_to_skip_adding_to:
        handled_lists.update(list_titles_to_skip_adding_to)

    # Now go through the lists in the json and add the appropriate new items
    for notelist in board["lists"]:
        title = notelist["title"]
        if title in all_new and title not in handled_lists:
            handled_lists.add(title)
            notelist["notes"].extend(all_new[title])
            log.info("Added new items to %s", title)

    # Add any missing lists
    missing_lists = set(all_new.keys()) - handled_lists
    for missing_title in missing_lists:
        log.info("Added new list %s", missing_title)
        board["lists"].append({"title": missing_title, "notes": all_new[missing_title]})

    board["revision"] = board["revision"] + 1
