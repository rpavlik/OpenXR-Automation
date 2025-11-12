# Copyright (c) 2014-2023 Frédéric Guillot
# Copyright 2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: MIT
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import asyncio
from typing import Optional

DEFAULT_AUTH_HEADER = "Authorization"

class Client:
    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        auth_header: str = DEFAULT_AUTH_HEADER,
        cafile: Optional[str] = None,
        insecure: bool = False,
        ignore_hostname_verification: bool = False,
        user_agent: str = "Kanboard Python API Client",
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None: ...

    # project_procedures

    def create_project(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        owner_id: Optional[int] = None,
        identifier: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        priority_default: Optional[int] = None,
        priority_start: Optional[int] = None,
        priority_end: Optional[int] = None,
        email: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#createproject"""

    async def create_project_async(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        owner_id: Optional[int] = None,
        identifier: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        priority_default: Optional[int] = None,
        priority_start: Optional[int] = None,
        priority_end: Optional[int] = None,
        email: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#createproject"""

    def get_project_by_id(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectbyid"""

    async def get_project_by_id_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectbyid"""

    def get_project_by_name(self, *, name: str): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectbyname"""

    async def get_project_by_name_async(self, *, name: str): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectbyname"""

    def get_project_by_identifier(self, *, identifier: str): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectbyidentifier"""

    async def get_project_by_identifier_async(self, *, identifier: str): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectbyidentifier"""

    def get_project_by_email(self, *, email: str): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectbyemail"""

    async def get_project_by_email_async(self, *, email: str): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectbyemail"""

    def get_all_projects(
        self,
    ): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getallprojects"""

    async def get_all_projects_async(
        self,
    ): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getallprojects"""

    def update_project(
        self,
        *,
        project_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        owner_id: Optional[int] = None,
        identifier: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        priority_default: Optional[int] = None,
        priority_start: Optional[int] = None,
        priority_end: Optional[int] = None,
        email: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#updateproject"""

    async def update_project_async(
        self,
        *,
        project_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        owner_id: Optional[int] = None,
        identifier: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        priority_default: Optional[int] = None,
        priority_start: Optional[int] = None,
        priority_end: Optional[int] = None,
        email: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#updateproject"""

    def enable_project(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#enableproject"""

    async def enable_project_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#enableproject"""

    def disable_project(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#disableproject"""

    async def disable_project_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#disableproject"""

    def enable_project_public_access(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#enableprojectpublicaccess"""

    async def enable_project_public_access_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#enableprojectpublicaccess"""

    def disable_project_public_access(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#disableprojectpublicaccess"""

    async def disable_project_public_access_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#disableprojectpublicaccess"""

    def get_project_activity(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectactivity"""

    async def get_project_activity_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectactivity"""

    def get_project_activities(self, *, project_ids: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectactivities"""

    async def get_project_activities_async(self, *, project_ids: int): ...
    """https://docs.kanboard.org/v1/api/project_procedures/#getprojectactivities"""

    # external_task_link_procedures

    def get_external_task_link_provider_dependencies(self, *, providerName: str): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#getexternaltasklinkproviderdependencies"""

    async def get_external_task_link_provider_dependencies_async(
        self, *, providerName: str
    ): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#getexternaltasklinkproviderdependencies"""

    def create_external_task_link(
        self,
        *,
        task_id: int,
        url: str,
        dependency: str,
        type: Optional[str] = None,
        title: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#createexternaltasklink"""

    async def create_external_task_link_async(
        self,
        *,
        task_id: int,
        url: str,
        dependency: str,
        type: Optional[str] = None,
        title: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#createexternaltasklink"""

    def update_external_task_link(
        self,
        *,
        task_id: int,
        link_id: int,
        title: str,
        url: str,
        dependency: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#updateexternaltasklink"""

    async def update_external_task_link_async(
        self,
        *,
        task_id: int,
        link_id: int,
        title: str,
        url: str,
        dependency: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#updateexternaltasklink"""

    def get_external_task_link_by_id(self, *, task_id: int, link_id: int): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#getexternaltasklinkbyid"""

    async def get_external_task_link_by_id_async(
        self, *, task_id: int, link_id: int
    ): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#getexternaltasklinkbyid"""

    def get_all_external_task_links(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#getallexternaltasklinks"""

    async def get_all_external_task_links_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#getallexternaltasklinks"""

    def remove_external_task_link(self, *, task_id: int, link_id: int): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#removeexternaltasklink"""

    async def remove_external_task_link_async(self, *, task_id: int, link_id: int): ...
    """https://docs.kanboard.org/v1/api/external_task_link_procedures/#removeexternaltasklink"""

    # group_procedures

    def create_group(self, *, name: str, external_id: Optional[str] = None): ...
    """https://docs.kanboard.org/v1/api/group_procedures/#creategroup"""

    async def create_group_async(
        self, *, name: str, external_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/group_procedures/#creategroup"""

    def update_group(
        self,
        *,
        group_id: int,
        name: Optional[str] = None,
        external_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/group_procedures/#updategroup"""

    async def update_group_async(
        self,
        *,
        group_id: int,
        name: Optional[str] = None,
        external_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/group_procedures/#updategroup"""

    def remove_group(self, *, group_id: int): ...
    """https://docs.kanboard.org/v1/api/group_procedures/#removegroup"""

    async def remove_group_async(self, *, group_id: int): ...
    """https://docs.kanboard.org/v1/api/group_procedures/#removegroup"""

    def get_group(self, *, group_id: int): ...
    """https://docs.kanboard.org/v1/api/group_procedures/#getgroup"""

    async def get_group_async(self, *, group_id: int): ...
    """https://docs.kanboard.org/v1/api/group_procedures/#getgroup"""

    # task_metadata_procedures

    def get_task_metadata(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_metadata_procedures/#gettaskmetadata"""

    async def get_task_metadata_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_metadata_procedures/#gettaskmetadata"""

    def get_task_metadata_by_name(self, *, task_id: int, name: str): ...
    """https://docs.kanboard.org/v1/api/task_metadata_procedures/#gettaskmetadatabyname"""

    async def get_task_metadata_by_name_async(self, *, task_id: int, name: str): ...
    """https://docs.kanboard.org/v1/api/task_metadata_procedures/#gettaskmetadatabyname"""

    def save_task_metadata(self, *, task_id: int, values: list): ...
    """https://docs.kanboard.org/v1/api/task_metadata_procedures/#savetaskmetadata"""

    async def save_task_metadata_async(self, *, task_id: int, values: list): ...
    """https://docs.kanboard.org/v1/api/task_metadata_procedures/#savetaskmetadata"""

    def remove_task_metadata(self, *, task_id: int, name: str): ...
    """https://docs.kanboard.org/v1/api/task_metadata_procedures/#removetaskmetadata"""

    async def remove_task_metadata_async(self, *, task_id: int, name: str): ...
    """https://docs.kanboard.org/v1/api/task_metadata_procedures/#removetaskmetadata"""

    # tags_procedures

    def get_tags_by_project(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#gettagsbyproject"""

    async def get_tags_by_project_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#gettagsbyproject"""

    def create_tag(
        self, *, project_id: int, tag: str, color_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#createtag"""

    async def create_tag_async(
        self, *, project_id: int, tag: str, color_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#createtag"""

    def update_tag(self, *, tag_id: int, tag: str, color_id: Optional[str] = None): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#updatetag"""

    async def update_tag_async(
        self, *, tag_id: int, tag: str, color_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#updatetag"""

    def remove_tag(self, *, tag_id: int): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#removetag"""

    async def remove_tag_async(self, *, tag_id: int): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#removetag"""

    def set_task_tags(self, *, project_id: int, task_id: int, tags: list[str]): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#settasktags"""

    async def set_task_tags_async(
        self, *, project_id: int, task_id: int, tags: list[str]
    ): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#settasktags"""

    def get_task_tags(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#gettasktags"""

    async def get_task_tags_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/tags_procedures/#gettasktags"""

    # application_procedures

    # task_file_procedures

    def create_task_file(
        self, *, project_id: int, task_id: int, filename: str, blob: str
    ): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#createtaskfile"""

    async def create_task_file_async(
        self, *, project_id: int, task_id: int, filename: str, blob: str
    ): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#createtaskfile"""

    def get_all_task_files(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#getalltaskfiles"""

    async def get_all_task_files_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#getalltaskfiles"""

    def get_task_file(self, *, file_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#gettaskfile"""

    async def get_task_file_async(self, *, file_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#gettaskfile"""

    def download_task_file(self, *, file_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#downloadtaskfile"""

    async def download_task_file_async(self, *, file_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#downloadtaskfile"""

    def remove_task_file(self, *, file_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#removetaskfile"""

    async def remove_task_file_async(self, *, file_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#removetaskfile"""

    def remove_all_task_files(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#removealltaskfiles"""

    async def remove_all_task_files_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_file_procedures/#removealltaskfiles"""

    # comment_procedures

    def create_comment(
        self,
        *,
        task_id: int,
        user_id: int,
        content: str,
        reference: Optional[str] = None,
        visibility: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#createcomment"""

    async def create_comment_async(
        self,
        *,
        task_id: int,
        user_id: int,
        content: str,
        reference: Optional[str] = None,
        visibility: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#createcomment"""

    def get_comment(self, *, comment_id: int): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#getcomment"""

    async def get_comment_async(self, *, comment_id: int): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#getcomment"""

    def get_all_comments(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#getallcomments"""

    async def get_all_comments_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#getallcomments"""

    def update_comment(self, *, id: int, content: str): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#updatecomment"""

    async def update_comment_async(self, *, id: int, content: str): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#updatecomment"""

    def remove_comment(self, *, comment_id: int): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#removecomment"""

    async def remove_comment_async(self, *, comment_id: int): ...
    """https://docs.kanboard.org/v1/api/comment_procedures/#removecomment"""

    # category_procedures

    def create_category(
        self, *, project_id: int, name: str, color_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#createcategory"""

    async def create_category_async(
        self, *, project_id: int, name: str, color_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#createcategory"""

    def get_category(self, *, category_id: int): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#getcategory"""

    async def get_category_async(self, *, category_id: int): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#getcategory"""

    def get_all_categories(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#getallcategories"""

    async def get_all_categories_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#getallcategories"""

    def update_category(
        self, *, id: int, name: str, color_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#updatecategory"""

    async def update_category_async(
        self, *, id: int, name: str, color_id: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#updatecategory"""

    def remove_category(self, *, category_id: int): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#removecategory"""

    async def remove_category_async(self, *, category_id: int): ...
    """https://docs.kanboard.org/v1/api/category_procedures/#removecategory"""

    # board_procedures

    def get_board(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/board_procedures/#getboard"""

    async def get_board_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/board_procedures/#getboard"""

    # me_procedures

    def create_my_private_project(
        self, *, name: str, description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/me_procedures/#createmyprivateproject"""

    async def create_my_private_project_async(
        self, *, name: str, description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/me_procedures/#createmyprivateproject"""

    def get_my_projects(
        self,
    ): ...
    """https://docs.kanboard.org/v1/api/me_procedures/#getmyprojects"""

    async def get_my_projects_async(
        self,
    ): ...
    """https://docs.kanboard.org/v1/api/me_procedures/#getmyprojects"""

    # project_metadata_procedures

    def get_project_metadata(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_metadata_procedures/#getprojectmetadata"""

    async def get_project_metadata_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_metadata_procedures/#getprojectmetadata"""

    def get_project_metadata_by_name(self, *, project_id: int, name: str): ...
    """https://docs.kanboard.org/v1/api/project_metadata_procedures/#getprojectmetadatabyname"""

    async def get_project_metadata_by_name_async(
        self, *, project_id: int, name: str
    ): ...
    """https://docs.kanboard.org/v1/api/project_metadata_procedures/#getprojectmetadatabyname"""

    def save_project_metadata(self, *, project_id: int, values: dict): ...
    """https://docs.kanboard.org/v1/api/project_metadata_procedures/#saveprojectmetadata"""

    async def save_project_metadata_async(self, *, project_id: int, values: dict): ...
    """https://docs.kanboard.org/v1/api/project_metadata_procedures/#saveprojectmetadata"""

    def remove_project_metadata(self, *, project_id: int, name: str): ...
    """https://docs.kanboard.org/v1/api/project_metadata_procedures/#removeprojectmetadata"""

    async def remove_project_metadata_async(self, *, project_id: int, name: str): ...
    """https://docs.kanboard.org/v1/api/project_metadata_procedures/#removeprojectmetadata"""

    # internal_task_link_procedures

    def create_task_link(
        self, *, task_id: int, opposite_task_id: int, link_id: int
    ): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#createtasklink"""

    async def create_task_link_async(
        self, *, task_id: int, opposite_task_id: int, link_id: int
    ): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#createtasklink"""

    def update_task_link(
        self, *, task_link_id: int, task_id: int, opposite_task_id: int, link_id: int
    ): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#updatetasklink"""

    async def update_task_link_async(
        self, *, task_link_id: int, task_id: int, opposite_task_id: int, link_id: int
    ): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#updatetasklink"""

    def get_task_link_by_id(self, *, task_link_id: int): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#gettasklinkbyid"""

    async def get_task_link_by_id_async(self, *, task_link_id: int): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#gettasklinkbyid"""

    def get_all_task_links(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#getalltasklinks"""

    async def get_all_task_links_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#getalltasklinks"""

    def remove_task_link(self, *, task_link_id: int): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#removetasklink"""

    async def remove_task_link_async(self, *, task_link_id: int): ...
    """https://docs.kanboard.org/v1/api/internal_task_link_procedures/#removetasklink"""

    # column_procedures

    def get_columns(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#getcolumns"""

    async def get_columns_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#getcolumns"""

    def get_column(self, *, column_id: int): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#getcolumn"""

    async def get_column_async(self, *, column_id: int): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#getcolumn"""

    def change_column_position(
        self, *, project_id: int, column_id: int, position: int
    ): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#changecolumnposition"""

    async def change_column_position_async(
        self, *, project_id: int, column_id: int, position: int
    ): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#changecolumnposition"""

    def update_column(
        self,
        *,
        column_id: int,
        title: str,
        task_limit: Optional[int] = None,
        description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#updatecolumn"""

    async def update_column_async(
        self,
        *,
        column_id: int,
        title: str,
        task_limit: Optional[int] = None,
        description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#updatecolumn"""

    def add_column(
        self,
        *,
        project_id: int,
        title: str,
        task_limit: Optional[int] = None,
        description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#addcolumn"""

    async def add_column_async(
        self,
        *,
        project_id: int,
        title: str,
        task_limit: Optional[int] = None,
        description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#addcolumn"""

    def remove_column(self, *, column_id: int): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#removecolumn"""

    async def remove_column_async(self, *, column_id: int): ...
    """https://docs.kanboard.org/v1/api/column_procedures/#removecolumn"""

    # project_permission_procedures

    def get_project_users(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#getprojectusers"""

    async def get_project_users_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#getprojectusers"""

    def get_assignable_users(
        self, *, project_id: int, prepend_unassigned: Optional[bool] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#getassignableusers"""

    async def get_assignable_users_async(
        self, *, project_id: int, prepend_unassigned: Optional[bool] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#getassignableusers"""

    def add_project_user(
        self, *, project_id: int, user_id: int, role: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#addprojectuser"""

    async def add_project_user_async(
        self, *, project_id: int, user_id: int, role: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#addprojectuser"""

    def add_project_group(
        self, *, project_id: int, group_id: int, role: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#addprojectgroup"""

    async def add_project_group_async(
        self, *, project_id: int, group_id: int, role: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#addprojectgroup"""

    def remove_project_user(self, *, project_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#removeprojectuser"""

    async def remove_project_user_async(self, *, project_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#removeprojectuser"""

    def remove_project_group(self, *, project_id: int, group_id: int): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#removeprojectgroup"""

    async def remove_project_group_async(self, *, project_id: int, group_id: int): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#removeprojectgroup"""

    def change_project_user_role(self, *, project_id: int, user_id: int, role: str): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#changeprojectuserrole"""

    async def change_project_user_role_async(
        self, *, project_id: int, user_id: int, role: str
    ): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#changeprojectuserrole"""

    def change_project_group_role(
        self, *, project_id: int, group_id: int, role: str
    ): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#changeprojectgrouprole"""

    async def change_project_group_role_async(
        self, *, project_id: int, group_id: int, role: str
    ): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#changeprojectgrouprole"""

    def get_project_user_role(self, *, project_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#getprojectuserrole"""

    async def get_project_user_role_async(self, *, project_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/project_permission_procedures/#getprojectuserrole"""

    # link_procedures

    def get_opposite_link_id(self, *, link_id: int): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#getoppositelinkid"""

    async def get_opposite_link_id_async(self, *, link_id: int): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#getoppositelinkid"""

    def get_link_by_label(self, *, label: int): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#getlinkbylabel"""

    async def get_link_by_label_async(self, *, label: int): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#getlinkbylabel"""

    def get_link_by_id(self, *, link_id: int): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#getlinkbyid"""

    async def get_link_by_id_async(self, *, link_id: int): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#getlinkbyid"""

    def create_link(self, *, label: int, opposite_label: Optional[int] = None): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#createlink"""

    async def create_link_async(
        self, *, label: int, opposite_label: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#createlink"""

    def update_link(self, *, link_id: int, opposite_link_id: int, label: str): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#updatelink"""

    async def update_link_async(
        self, *, link_id: int, opposite_link_id: int, label: str
    ): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#updatelink"""

    def remove_link(self, *, link_id: int): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#removelink"""

    async def remove_link_async(self, *, link_id: int): ...
    """https://docs.kanboard.org/v1/api/link_procedures/#removelink"""

    # subtask_time_tracking_procedures

    def has_subtask_timer(self, *, subtask_id: int, user_id: Optional[int] = None): ...
    """https://docs.kanboard.org/v1/api/subtask_time_tracking_procedures/#hassubtasktimer"""

    async def has_subtask_timer_async(
        self, *, subtask_id: int, user_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_time_tracking_procedures/#hassubtasktimer"""

    def set_subtask_start_time(
        self, *, subtask_id: int, user_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_time_tracking_procedures/#setsubtaskstarttime"""

    async def set_subtask_start_time_async(
        self, *, subtask_id: int, user_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_time_tracking_procedures/#setsubtaskstarttime"""

    def set_subtask_end_time(
        self, *, subtask_id: int, user_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_time_tracking_procedures/#setsubtaskendtime"""

    async def set_subtask_end_time_async(
        self, *, subtask_id: int, user_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_time_tracking_procedures/#setsubtaskendtime"""

    def get_subtask_time_spent(
        self, *, subtask_id: int, user_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_time_tracking_procedures/#getsubtasktimespent"""

    async def get_subtask_time_spent_async(
        self, *, subtask_id: int, user_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_time_tracking_procedures/#getsubtasktimespent"""

    # group_member_procedures

    def get_member_groups(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#getmembergroups"""

    async def get_member_groups_async(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#getmembergroups"""

    def get_group_members(self, *, group_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#getgroupmembers"""

    async def get_group_members_async(self, *, group_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#getgroupmembers"""

    def add_group_member(self, *, group_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#addgroupmember"""

    async def add_group_member_async(self, *, group_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#addgroupmember"""

    def remove_group_member(self, *, group_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#removegroupmember"""

    async def remove_group_member_async(self, *, group_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#removegroupmember"""

    def is_group_member(self, *, group_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#isgroupmember"""

    async def is_group_member_async(self, *, group_id: int, user_id: int): ...
    """https://docs.kanboard.org/v1/api/group_member_procedures/#isgroupmember"""

    # user_procedures

    def create_user(
        self,
        *,
        username: str,
        password: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#createuser"""

    async def create_user_async(
        self,
        *,
        username: str,
        password: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#createuser"""

    def create_ldap_user(self, *, username: str): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#createldapuser"""

    async def create_ldap_user_async(self, *, username: str): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#createldapuser"""

    def get_user(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#getuser"""

    async def get_user_async(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#getuser"""

    def get_user_by_name(self, *, username: str): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#getuserbyname"""

    async def get_user_by_name_async(self, *, username: str): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#getuserbyname"""

    def get_all_users(
        self,
    ): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#getallusers"""

    async def get_all_users_async(
        self,
    ): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#getallusers"""

    def update_user(
        self,
        *,
        id: int,
        username: Optional[str] = None,
        name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#updateuser"""

    async def update_user_async(
        self,
        *,
        id: int,
        username: Optional[str] = None,
        name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#updateuser"""

    def remove_user(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#removeuser"""

    async def remove_user_async(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#removeuser"""

    def disable_user(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#disableuser"""

    async def disable_user_async(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#disableuser"""

    def enable_user(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#enableuser"""

    async def enable_user_async(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#enableuser"""

    def is_active_user(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#isactiveuser"""

    async def is_active_user_async(self, *, user_id: int): ...
    """https://docs.kanboard.org/v1/api/user_procedures/#isactiveuser"""

    # swimlane_procedures

    def get_active_swimlanes(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getactiveswimlanes"""

    async def get_active_swimlanes_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getactiveswimlanes"""

    def get_all_swimlanes(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getallswimlanes"""

    async def get_all_swimlanes_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getallswimlanes"""

    def get_swimlane(self, *, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getswimlane"""

    async def get_swimlane_async(self, *, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getswimlane"""

    def get_swimlane_by_id(self, *, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getswimlanebyid"""

    async def get_swimlane_by_id_async(self, *, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getswimlanebyid"""

    def get_swimlane_by_name(self, *, project_id: int, name: str): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getswimlanebyname"""

    async def get_swimlane_by_name_async(self, *, project_id: int, name: str): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#getswimlanebyname"""

    def change_swimlane_position(
        self, *, project_id: int, swimlane_id: int, position: int
    ): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#changeswimlaneposition"""

    async def change_swimlane_position_async(
        self, *, project_id: int, swimlane_id: int, position: int
    ): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#changeswimlaneposition"""

    def update_swimlane(
        self,
        *,
        project_id: int,
        swimlane_id: int,
        name: str,
        description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#updateswimlane"""

    async def update_swimlane_async(
        self,
        *,
        project_id: int,
        swimlane_id: int,
        name: str,
        description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#updateswimlane"""

    def add_swimlane(
        self, *, project_id: int, name: str, description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#addswimlane"""

    async def add_swimlane_async(
        self, *, project_id: int, name: str, description: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#addswimlane"""

    def remove_swimlane(self, *, project_id: int, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#removeswimlane"""

    async def remove_swimlane_async(self, *, project_id: int, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#removeswimlane"""

    def disable_swimlane(self, *, project_id: int, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#disableswimlane"""

    async def disable_swimlane_async(self, *, project_id: int, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#disableswimlane"""

    def enable_swimlane(self, *, project_id: int, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#enableswimlane"""

    async def enable_swimlane_async(self, *, project_id: int, swimlane_id: int): ...
    """https://docs.kanboard.org/v1/api/swimlane_procedures/#enableswimlane"""

    # subtask_procedures

    def create_subtask(
        self,
        *,
        task_id: int,
        title: str,
        user_id: Optional[int] = None,
        time_estimated: Optional[int] = None,
        time_spent: Optional[int] = None,
        status: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#createsubtask"""

    async def create_subtask_async(
        self,
        *,
        task_id: int,
        title: str,
        user_id: Optional[int] = None,
        time_estimated: Optional[int] = None,
        time_spent: Optional[int] = None,
        status: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#createsubtask"""

    def get_subtask(self, *, subtask_id: int): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#getsubtask"""

    async def get_subtask_async(self, *, subtask_id: int): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#getsubtask"""

    def get_all_subtasks(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#getallsubtasks"""

    async def get_all_subtasks_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#getallsubtasks"""

    def update_subtask(
        self,
        *,
        id: int,
        task_id: int,
        title: Optional[int] = None,
        user_id: Optional[int] = None,
        time_estimated: Optional[int] = None,
        time_spent: Optional[int] = None,
        status: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#updatesubtask"""

    async def update_subtask_async(
        self,
        *,
        id: int,
        task_id: int,
        title: Optional[str] = None,
        user_id: Optional[int] = None,
        time_estimated: Optional[int] = None,
        time_spent: Optional[int] = None,
        status: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#updatesubtask"""

    def remove_subtask(self, *, subtask_id: int): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#removesubtask"""

    async def remove_subtask_async(self, *, subtask_id: int): ...
    """https://docs.kanboard.org/v1/api/subtask_procedures/#removesubtask"""

    # task_procedures

    def create_task(
        self,
        *,
        title: str,
        project_id: int,
        color_id: Optional[str] = None,
        column_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        creator_id: Optional[int] = None,
        date_due: Optional[str] = None,
        description: Optional[str] = None,
        category_id: Optional[int] = None,
        score: Optional[int] = None,
        swimlane_id: Optional[int] = None,
        priority: Optional[int] = None,
        recurrence_status: Optional[int] = None,
        recurrence_trigger: Optional[int] = None,
        recurrence_factor: Optional[int] = None,
        recurrence_timeframe: Optional[int] = None,
        recurrence_basedate: Optional[int] = None,
        reference: Optional[str] = None,
        tags: Optional[list[str]] = None,
        date_started: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#createtask"""

    async def create_task_async(
        self,
        *,
        title: str,
        project_id: int,
        color_id: Optional[str] = None,
        column_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        creator_id: Optional[int] = None,
        date_due: Optional[str] = None,
        description: Optional[str] = None,
        category_id: Optional[int] = None,
        score: Optional[int] = None,
        swimlane_id: Optional[int] = None,
        priority: Optional[int] = None,
        recurrence_status: Optional[int] = None,
        recurrence_trigger: Optional[int] = None,
        recurrence_factor: Optional[int] = None,
        recurrence_timeframe: Optional[int] = None,
        recurrence_basedate: Optional[int] = None,
        reference: Optional[str] = None,
        tags: Optional[list[str]] = None,
        date_started: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#createtask"""

    def get_task(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#gettask"""

    async def get_task_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#gettask"""

    def get_task_by_reference(self, *, project_id: int, reference: str): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#gettaskbyreference"""

    async def get_task_by_reference_async(self, *, project_id: int, reference: str): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#gettaskbyreference"""

    def get_all_tasks(self, *, project_id: int, status_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#getalltasks"""

    async def get_all_tasks_async(self, *, project_id: int, status_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#getalltasks"""

    def update_task(
        self,
        *,
        id: int,
        title: Optional[str] = None,
        color_id: Optional[str] = None,
        owner_id: Optional[int] = None,
        date_due: Optional[str] = None,
        description: Optional[str] = None,
        category_id: Optional[int] = None,
        score: Optional[int] = None,
        priority: Optional[int] = None,
        recurrence_status: Optional[int] = None,
        recurrence_trigger: Optional[int] = None,
        recurrence_factor: Optional[int] = None,
        recurrence_timeframe: Optional[int] = None,
        recurrence_basedate: Optional[int] = None,
        reference: Optional[str] = None,
        tags: Optional[list[str]] = None,
        date_started: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#updatetask"""

    async def update_task_async(
        self,
        *,
        id: int,
        title: Optional[str] = None,
        color_id: Optional[str] = None,
        owner_id: Optional[int] = None,
        date_due: Optional[str] = None,
        description: Optional[str] = None,
        category_id: Optional[int] = None,
        score: Optional[int] = None,
        priority: Optional[int] = None,
        recurrence_status: Optional[int] = None,
        recurrence_trigger: Optional[int] = None,
        recurrence_factor: Optional[int] = None,
        recurrence_timeframe: Optional[int] = None,
        recurrence_basedate: Optional[int] = None,
        reference: Optional[str] = None,
        tags: Optional[list[str]] = None,
        date_started: Optional[str] = None
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#updatetask"""

    def open_task(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#opentask"""

    async def open_task_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#opentask"""

    def close_task(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#closetask"""

    async def close_task_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#closetask"""

    def remove_task(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#removetask"""

    async def remove_task_async(self, *, task_id: int): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#removetask"""

    def move_task_position(
        self,
        *,
        project_id: int,
        task_id: int,
        column_id: int,
        position: int,
        swimlane_id: int
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#movetaskposition"""

    async def move_task_position_async(
        self,
        *,
        project_id: int,
        task_id: int,
        column_id: int,
        position: int,
        swimlane_id: int
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#movetaskposition"""

    def move_task_to_project(
        self,
        *,
        task_id: int,
        project_id: int,
        swimlane_id: Optional[int] = None,
        column_id: Optional[int] = None,
        category_id: Optional[int] = None,
        owner_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#movetasktoproject"""

    async def move_task_to_project_async(
        self,
        *,
        task_id: int,
        project_id: int,
        swimlane_id: Optional[int] = None,
        column_id: Optional[int] = None,
        category_id: Optional[int] = None,
        owner_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#movetasktoproject"""

    def duplicate_task_to_project(
        self,
        *,
        task_id: int,
        project_id: int,
        swimlane_id: Optional[int] = None,
        column_id: Optional[int] = None,
        category_id: Optional[int] = None,
        owner_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#duplicatetasktoproject"""

    async def duplicate_task_to_project_async(
        self,
        *,
        task_id: int,
        project_id: int,
        swimlane_id: Optional[int] = None,
        column_id: Optional[int] = None,
        category_id: Optional[int] = None,
        owner_id: Optional[int] = None
    ): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#duplicatetasktoproject"""

    def search_tasks(self, *, project_id: int, query: str): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#searchtasks"""

    async def search_tasks_async(self, *, project_id: int, query: str): ...
    """https://docs.kanboard.org/v1/api/task_procedures/#searchtasks"""

    # project_file_procedures

    def create_project_file(self, *, project_id: int, filename: int, blob: str): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#createprojectfile"""

    async def create_project_file_async(
        self, *, project_id: int, filename: int, blob: str
    ): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#createprojectfile"""

    def get_all_project_files(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#getallprojectfiles"""

    async def get_all_project_files_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#getallprojectfiles"""

    def get_project_file(self, *, project_id: int, file_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#getprojectfile"""

    async def get_project_file_async(self, *, project_id: int, file_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#getprojectfile"""

    def download_project_file(self, *, project_id: int, file_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#downloadprojectfile"""

    async def download_project_file_async(self, *, project_id: int, file_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#downloadprojectfile"""

    def remove_project_file(self, *, project_id: int, file_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#removeprojectfile"""

    async def remove_project_file_async(self, *, project_id: int, file_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#removeprojectfile"""

    def remove_all_project_files(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#removeallprojectfiles"""

    async def remove_all_project_files_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/project_file_procedures/#removeallprojectfiles"""

    # action_procedures

    def get_compatible_action_events(self, *, action_name: str): ...
    """https://docs.kanboard.org/v1/api/action_procedures/#getcompatibleactionevents"""

    async def get_compatible_action_events_async(self, *, action_name: str): ...
    """https://docs.kanboard.org/v1/api/action_procedures/#getcompatibleactionevents"""

    def get_actions(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/action_procedures/#getactions"""

    async def get_actions_async(self, *, project_id: int): ...
    """https://docs.kanboard.org/v1/api/action_procedures/#getactions"""

    def create_action(
        self, *, project_id: int, event_name: str, action_name: str, params: dict
    ): ...
    """https://docs.kanboard.org/v1/api/action_procedures/#createaction"""

    async def create_action_async(
        self, *, project_id: int, event_name: str, action_name: str, params: dict
    ): ...
    """https://docs.kanboard.org/v1/api/action_procedures/#createaction"""

    def remove_action(self, *, action_id: int): ...
    """https://docs.kanboard.org/v1/api/action_procedures/#removeaction"""

    async def remove_action_async(self, *, action_id: int): ...
    """https://docs.kanboard.org/v1/api/action_procedures/#removeaction"""
