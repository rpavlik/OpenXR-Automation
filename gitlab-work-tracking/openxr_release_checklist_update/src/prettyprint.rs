// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>
use gitlab::ProjectId;
use gitlab_work_units::{
    lookup::GitlabQueryCache, BaseGitLabItemReference, ProjectItemReference, ProjectReference,
};
use pretty::{DocAllocator, DocBuilder};
use workboard_update::{
    line_or_reference::{LineOrReference, ProcessedNote},
    GetWorkUnit,
};

use crate::board_operation::BoardOperation;

pub struct PrettyData<'a> {
    pub default_project_id: ProjectId,
    pub client: &'a gitlab::Gitlab,
    pub cache: &'a mut GitlabQueryCache,
}

pub trait PrettyForConsole {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        data: &mut PrettyData<'b>,
    ) -> DocBuilder<'b, D, A>
    where
        D: DocAllocator<'b, A>,
        D::Doc: Clone,
        A: Clone;
}

impl PrettyForConsole for ProjectReference {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        data: &mut PrettyData<'b>,
    ) -> DocBuilder<'b, D, A>
    where
        D: DocAllocator<'b, A>,
        D::Doc: Clone,
        A: Clone,
    {
        match self {
            ProjectReference::ProjectId(proj_id) => {
                if proj_id == &data.default_project_id {
                    allocator.nil()
                } else {
                    allocator.as_string(proj_id.value())
                }
            }
            ProjectReference::ProjectName(name) => allocator.text(name),
            ProjectReference::UnknownProject => allocator.nil(),
        }
    }
}

impl PrettyForConsole for ProjectItemReference {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        data: &mut PrettyData<'b>,
    ) -> DocBuilder<'b, D, A>
    where
        D: DocAllocator<'b, A>,
        D::Doc: Clone,
        A: Clone,
    {
        // Try looking up the title
        let title = data
            .cache
            .query(data.client, self)
            .map(|results| {
                allocator
                    .space()
                    .append(allocator.text(results.title().to_owned()))
            })
            .unwrap_or_else(|_| allocator.nil());

        let project = self.project().pretty(allocator, data);
        project
            .append(allocator.as_string(self.symbol()))
            .append(allocator.as_string(self.raw_iid()))
            .append(title)
            .group()
    }
}

impl PrettyForConsole for LineOrReference {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        data: &mut PrettyData<'b>,
    ) -> DocBuilder<'b, D, A>
    where
        D: DocAllocator<'b, A>,
        D::Doc: Clone,
        A: Clone,
    {
        match self {
            LineOrReference::Line(line) => allocator.text(line.trim()),
            LineOrReference::Reference(r) => r.pretty(allocator, data),
        }
    }
}

impl PrettyForConsole for ProcessedNote {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        data: &mut PrettyData<'b>,
    ) -> DocBuilder<'b, D, A>
    where
        D: DocAllocator<'b, A>,
        D::Doc: Clone,
        A: Clone,
    {
        let unit_id = self
            .work_unit_id()
            .map(|id| allocator.text(format!("{:?}", id)))
            .unwrap_or_else(|| allocator.nil());

        let lines = self
            .lines()
            .0
            .iter()
            .map(|line_or_ref| line_or_ref.pretty(allocator, data));

        allocator
            .text("ProcessedNote(")
            .append(
                unit_id
                    .append(allocator.hardline())
                    .append(allocator.intersperse(lines, allocator.hardline()))
                    .nest(4),
            )
            .append(allocator.hardline())
            .append(allocator.text(")"))
    }
}

impl PrettyForConsole for BoardOperation {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        data: &mut PrettyData<'b>,
    ) -> DocBuilder<'b, D, A>
    where
        D: DocAllocator<'b, A>,
        D::Doc: Clone,
        A: Clone,
    {
        match self {
            BoardOperation::NoOp => allocator.text("NoOp"),

            BoardOperation::AddNote { list_name, note } => allocator
                .text("AddNote(")
                .append(
                    allocator
                        .text(list_name)
                        .double_quotes()
                        .append(allocator.text(","))
                        .append(allocator.hardline())
                        .append(note.pretty(allocator, data))
                        .nest(4),
                )
                .append(allocator.hardline())
                .append(")"),

            BoardOperation::MoveNote {
                current_list_name,
                new_list_name,
                work_unit_id,
            } => {
                let words = vec![
                    allocator.text(current_list_name.as_str()),
                    allocator.text("->"),
                    allocator.text(new_list_name.as_str()),
                    allocator.text("for"),
                    allocator.text(format!("{:?}", work_unit_id)),
                ];
                allocator
                    .text("MoveNote(")
                    .append(
                        allocator
                            .intersperse(words.into_iter(), allocator.space())
                            .group()
                            .nest(2),
                    )
                    .append(allocator.text(")"))
            }
        }
    }
}
