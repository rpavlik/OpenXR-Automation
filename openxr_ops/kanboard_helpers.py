# Copyright 2022, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
import asyncio
from dataclasses import dataclass
from typing import Literal, Union

import kanboard


@dataclass
class LinkIdData:
    link_id: int
    label: str
    opposite_id: int


class LinkIdMapping:

    def __init__(self, kb: kanboard.Client) -> None:
        self.kb = kb
        self.link_label_to_id: dict[str, int] = dict()
        self.link_id_to_label: dict[int, str] = dict()

    async def fetch_link_types(self) -> None:
        """Retrieve names and IDs for link types."""

        links: Union[Literal[False], list[dict[str, str]]] = (
            await self.kb.get_all_links_async()  # type: ignore
        )
        if not links:
            raise RuntimeError("Could not get all links!")

        for link_data in links:
            link_id = int(link_data["id"])
            label = link_data["label"]
            self.link_id_to_label[link_id] = label
            self.link_label_to_id[label] = link_id


class KanboardProject:

    def __init__(self, kb: kanboard.Client, project_id: int):
        self.kb = kb
        self.project_id = project_id
        self.col_titles: dict[str, int] = dict()
        self.col_ids_to_titles: dict[int, str] = dict()

        self.swimlane_titles: dict[str, int] = dict()
        self.swimlane_ids_to_titles: dict[int, str] = dict()

        self.category_title_to_id: dict[str, int] = dict()
        self.category_ids_to_titles: dict[int, str] = dict()

        self.link_manager = LinkIdMapping(kb)

    async def fetch_all_id_maps(self):
        """Retrieve names and IDs for categories, swimlands, columns, and links."""
        await asyncio.gather(
            self.fetch_categories(),
            self.fetch_columns(),
            self.fetch_swimlanes(),
            self.link_manager.fetch_link_types(),
        )

    async def fetch_categories(self):
        """Retrieve category names and IDs."""

        categories = await self.kb.get_all_categories_async(project_id=self.project_id)
        self.category_title_to_id.update({cat["name"]: cat["id"] for cat in categories})
        self.category_ids_to_titles = {
            v: k for k, v in self.category_title_to_id.items()
        }

    async def fetch_swimlanes(self):
        """Retrieve swimlane names and IDs."""

        swimlanes = await self.kb.get_active_swimlanes_async(project_id=self.project_id)
        self.swimlane_titles.update({sl["name"]: sl["id"] for sl in swimlanes})
        self.swimlane_ids_to_titles = {v: k for k, v in self.swimlane_titles.items()}

    async def fetch_columns(self):
        """Retrieve column titles and IDs."""

        columns = await self.kb.get_columns_async(project_id=self.project_id)
        self.col_titles.update({col["title"]: col["id"] for col in columns})
        self.col_ids_to_titles = {v: k for k, v in self.col_titles.items()}

    async def get_or_create_column(self, title):
        """Get a column ID, creating the column if needed."""
        maybe_col_id = self.col_titles.get(title)
        if maybe_col_id is not None:
            return maybe_col_id

        col_id = await self.kb.add_column_async(project_id=self.project_id, title=title)
        self.col_titles[title] = col_id
        self.col_ids_to_titles[col_id] = title
        return col_id

    async def get_all_tasks(self, only_open: bool = True):
        """Wrapper for https://docs.kanboard.org/v1/api/task_procedures/#getalltasks async."""
        status_id = 0
        if only_open:
            status_id = 1
        return await self.kb.get_all_tasks_async(
            project_id=self.project_id, status_id=status_id
        )
