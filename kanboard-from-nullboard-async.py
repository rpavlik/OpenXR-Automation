#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import asyncio
import json
import logging
import os

import kanboard

_SERVER = "openxr-boards.khronos.org"
_USERNAME = "khronos-bot"
_PROJ_NAME = "CTS Test"


async def handle_list(
    kb: kanboard.Client, proj_id: int, col_titles: dict[str, int], nb_list: dict
):
    title = nb_list["title"]
    print("Column title:", title)
    maybe_col_id = col_titles.get(title)
    if maybe_col_id is not None:
        col_id = maybe_col_id
    else:
        col_id = await kb.add_column_async(project_id=proj_id, title=title)

    subhead = ""
    results = []
    to_gather = []
    for note in nb_list["notes"]:
        note_text: str = note["text"]
        if note.get("raw"):
            # This is a subsection
            subhead = note_text
            continue
        # Just a regular note. Split up the parts, though.
        parts = [part.strip("•").strip() for part in note_text.split("\n")]
        main_part = parts[0]
        # outline.add_item(main_part)
        results.append((subhead, note_text))
        to_gather.append(
            asyncio.Task(
                kb.create_task_async(
                    title=main_part,
                    project_id=proj_id,
                    column_id=col_id,
                    description=note_text,
                )
            )
        )
        # sub_parts = parts[1:]
        # if sub_parts:
        #     outline.current_indent_level += 1
        #     for part in sub_parts:
        #         if part.strip():
        #             outline.add_item(part)
        #     outline.current_indent_level -= 1

    # return str(outline)
    await asyncio.gather(*to_gather)
    # return results


async def async_main(in_filename):
    log = logging.getLogger(__name__)
    token = os.environ.get("KANBOARD_API_TOKEN", "")
    kb = kanboard.Client(
        url=f"https://{_SERVER}/jsonrpc.php",
        username=_USERNAME,
        password=token,
        # cafile="/path/to/my/cert.pem",
        ignore_hostname_verification=True,
        insecure=True,
    )
    proj = kb.get_project_by_name_async(name=_PROJ_NAME)

    log.info("Reading %s", in_filename)
    with open(in_filename, "r") as fp:
        existing_board = json.load(fp)

    proj = await proj
    print(proj["url"]["board"])
    proj_id = proj["id"]

    columns = await kb.get_columns_async(project_id=proj_id)
    column_titles = {col["title"]: col["id"] for col in columns}
    await asyncio.gather(
        *[
            handle_list(kb, proj_id=proj_id, col_titles=column_titles, nb_list=nb_list)
            for nb_list in existing_board["lists"]
        ]
    )


def main(in_filename):
    token = os.environ.get("KANBOARD_API_TOKEN", "")
    kb = kanboard.Client(
        url=f"https://{_SERVER}/jsonrpc.php",
        username=_USERNAME,
        password=token,
        # cafile="/path/to/my/cert.pem",
        ignore_hostname_verification=True,
        insecure=True,
    )

    kb.get_my_projects()


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv

    load_dotenv()

    asyncio.run(async_main("Nullboard-1661530413298-OpenXR-CTS.nbx"))
