// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>
use gitlab::ProjectId;
use gitlab_work_units::{BaseGitLabItemReference, ProjectItemReference, ProjectReference};
use pretty::{DocAllocator, DocBuilder};
use std::fmt::Display;
use workboard_update::{
    line_or_reference::{LineOrReference, ProcessedNote},
    GetWorkUnit,
};

use crate::board_operation::BoardOperation;

/// Wrap something to change how it's formatted.
struct WithDefaultProjectKnowledge<'a, T: FormatWithDefaultProject> {
    default_project: ProjectId,
    value: &'a T,
}

impl<'a, T: FormatWithDefaultProject> WithDefaultProjectKnowledge<'a, T> {
    fn new(default_project_id: ProjectId, value: &'a T) -> Self {
        Self {
            default_project: default_project_id,
            value,
        }
    }
}

impl<'a, T: FormatWithDefaultProject> Display for WithDefaultProjectKnowledge<'a, T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.value
            .format_with_default_project(self.default_project, f)
    }
}
trait FormatWithDefaultProject {
    fn format_with_default_project(
        &self,
        default_project_id: ProjectId,
        f: &mut std::fmt::Formatter<'_>,
    ) -> std::fmt::Result;
}

impl FormatWithDefaultProject for ProjectReference {
    fn format_with_default_project(
        &self,
        default_project_id: ProjectId,
        f: &mut std::fmt::Formatter<'_>,
    ) -> std::fmt::Result {
        match self {
            ProjectReference::ProjectId(proj_id) => {
                if proj_id == &default_project_id {
                    write!(f, "")
                } else {
                    write!(f, "{}", proj_id)
                }
            }
            ProjectReference::ProjectName(name) => write!(f, "{}", name),
            ProjectReference::UnknownProject => write!(f, ""),
        }
    }
}

impl FormatWithDefaultProject for ProjectItemReference {
    fn format_with_default_project(
        &self,
        default_project_id: ProjectId,
        f: &mut std::fmt::Formatter<'_>,
    ) -> std::fmt::Result {
        write!(
            f,
            "{}{}{}",
            WithDefaultProjectKnowledge::new(default_project_id, self.project()),
            self.symbol(),
            self.raw_iid()
        )
    }
}

impl FormatWithDefaultProject for LineOrReference {
    fn format_with_default_project(
        &self,
        default_project_id: ProjectId,
        f: &mut std::fmt::Formatter<'_>,
    ) -> std::fmt::Result {
        match self {
            LineOrReference::Line(line) => write!(f, "{}", line),
            LineOrReference::Reference(r) => r.format_with_default_project(default_project_id, f),
        }
    }
}

pub trait PrettyForConsole {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        default_project_id: ProjectId,
    ) -> DocBuilder<'b, D, A>
    where
        D: DocAllocator<'b, A>,
        D::Doc: Clone,
        A: Clone;
}

impl PrettyForConsole for ProjectItemReference {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        default_project_id: ProjectId,
    ) -> DocBuilder<'b, D, A>
    where
        D: DocAllocator<'b, A>,
        D::Doc: Clone,
        A: Clone,
    {
        allocator.text(format!(
            "{}",
            WithDefaultProjectKnowledge::new(default_project_id, self)
        ))
    }
}
impl PrettyForConsole for LineOrReference {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        default_project_id: ProjectId,
    ) -> DocBuilder<'b, D, A>
    where
        D: DocAllocator<'b, A>,
        D::Doc: Clone,
        A: Clone,
    {
        match self {
            LineOrReference::Line(line) => allocator.text(line.trim()),
            LineOrReference::Reference(r) => r.pretty(allocator, default_project_id),
        }
    }
}

impl PrettyForConsole for ProcessedNote {
    fn pretty<'b, D, A>(
        &'b self,
        allocator: &'b D,
        default_project_id: ProjectId,
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
            .map(|line_or_ref| line_or_ref.pretty(allocator, default_project_id));

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
        default_project_id: ProjectId,
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
                        .append(note.pretty(allocator, default_project_id))
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
