# Copyright 2022, Collabora, Ltd.
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>
from typing import Optional
import kanboard


class KanboardBoard:

    def __init__(self, kb: kanboard.Client, project_id: int):
        self.kb = kb
        self.project_id = project_id
        self.col_titles: dict[str, int] = dict()

    async def fetch_col_titles(self):
        """Retrieve column titles and IDs."""

        columns = await self.kb.get_columns_async(project_id=self.project_id)
        self.col_titles.update({col["title"]: col["id"] for col in columns})

    async def get_or_create_column(self, title):
        """Get a column ID, creating the column if needed."""
        maybe_col_id = self.col_titles.get(title)
        if maybe_col_id is not None:
            return maybe_col_id

        col_id = await self.kb.add_column_async(project_id=self.project_id, title=title)
        self.col_titles[title] = col_id
        return col_id

    async def get_task_by_ref(self, ref):
        return await self.kb.get_task_by_reference_async(
            project_id=self.project_id, reference=ref
        )

    async def create_task(
        self,
        col_id,
        reference,
        title,
        description,
        gl_url,
        swimland_id: Optional[int] = None,
    ):
        pass
