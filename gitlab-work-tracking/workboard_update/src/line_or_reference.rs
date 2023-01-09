// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{
    note_line::NoteLine,
    traits::{GetItemReference, ParsedLineLike},
    GetWorkUnit,
};
use gitlab_work_units::{
    GitLabItemReferenceNormalize, ProjectItemReference, ProjectMapper, UnitId, WorkUnitCollection,
};
use log::info;
use nullboard_tools::{list::BasicList, GenericList, ListIteratorAdapters};

/// A simplified more structured representation of a line in a note (compared to `NoteLine`),
/// as either a non-reference freeform text line, or as a single project item reference.
#[derive(Debug, Clone)]
pub enum LineOrReference {
    /// A line of freeform text with no project item reference
    Line(String),
    /// A project item reference found in a line
    Reference(ProjectItemReference),
}

impl LineOrReference {
    /// Parse a single line of text into a LineOrReference instance
    pub fn parse_line(s: &str) -> Self {
        NoteLine::parse_line(s).into()
    }

    /// Turn this enum into a string, calling the provided function if it is an item reference
    pub fn format_to_string(self, f: impl FnOnce(ProjectItemReference) -> String) -> String {
        match self {
            LineOrReference::Line(text) => text,
            LineOrReference::Reference(reference) => f(reference),
        }
    }
}

impl GetItemReference for LineOrReference {
    fn project_item_reference(&self) -> Option<&ProjectItemReference> {
        if let Self::Reference(v) = self {
            Some(v)
        } else {
            None
        }
    }

    fn set_project_item_reference(&mut self, reference: ProjectItemReference) {
        if let Self::Reference(v) = self {
            *v = reference;
        }
    }

    fn try_map_reference_or_clone<E: std::error::Error>(
        &self,
        mut f: impl FnMut(&ProjectItemReference) -> Result<ProjectItemReference, E>,
    ) -> Result<Self, E>
    where
        Self: Sized,
    {
        if let Self::Reference(v) = self {
            let new_ref = f(v)?;
            Ok(LineOrReference::Reference(new_ref))
        } else {
            Ok(self.clone())
        }
    }
}

impl ParsedLineLike for LineOrReference {
    fn line(&self) -> Option<&str> {
        if let LineOrReference::Line(line) = self {
            Some(line.as_str())
        } else {
            None
        }
    }
}

impl From<ProjectItemReference> for LineOrReference {
    fn from(v: ProjectItemReference) -> Self {
        Self::Reference(v)
    }
}

impl From<String> for LineOrReference {
    fn from(value: String) -> Self {
        Self::Line(value)
    }
}
impl From<&str> for LineOrReference {
    fn from(value: &str) -> Self {
        Self::Line(value.to_string())
    }
}

impl From<NoteLine> for LineOrReference {
    fn from(line: NoteLine) -> Self {
        match line.reference {
            Some(reference) => LineOrReference::Reference(reference),
            None => LineOrReference::Line(line.line),
        }
    }
}

#[derive(Debug)]
pub struct LineOrReferenceCollection(pub Vec<LineOrReference>);

#[derive(Debug)]
pub struct ProcessedNote {
    pub(crate) unit_id: Option<UnitId>,
    pub(crate) lines: LineOrReferenceCollection,
}

impl ProcessedNote {
    pub fn new(unit_id: Option<UnitId>, lines: LineOrReferenceCollection) -> Self {
        Self { unit_id, lines }
    }
}

impl GetWorkUnit for ProcessedNote {
    fn work_unit_id(&self) -> &Option<UnitId> {
        &self.unit_id
    }

    fn work_unit_id_mut(&mut self) -> &mut Option<UnitId> {
        &mut self.unit_id
    }

    fn has_work_unit_id(&self) -> bool {
        self.unit_id.is_some()
    }
}

impl From<ProcessedNote> for LineOrReferenceCollection {
    fn from(note: ProcessedNote) -> Self {
        note.lines
    }
}

/// Parse a (possibly multiline) string into lines that are each LineOrReference
pub fn parse_note(s: String) -> LineOrReferenceCollection {
    LineOrReferenceCollection(s.split('\n').map(LineOrReference::parse_line).collect())
}

/// Parse lists of notes, each containing a (possibly multiline) string into
/// lists of notes with data `Lines` that are each LineOrReference
pub fn parse_notes(lists: Vec<BasicList>) -> Vec<GenericList<LineOrReferenceCollection>> {
    info!("Parsing notes");
    lists.into_iter().map_note_data(parse_note).collect()
}

/// Associate a work unit with these lines
pub fn associate_work_unit_with_note(
    collection: &mut WorkUnitCollection,
    lines: LineOrReferenceCollection,
) -> ProcessedNote {
    let unit_id = super::associate_work_unit_with_note(collection, lines.0.iter());
    ProcessedNote { unit_id, lines }
}

/// Transform an item reference line into its "normalized" state, with a numeric project ID
///
/// Turns any errors into an error message in the line.
fn normalize_line_or_reference(
    mapper: &mut ProjectMapper,
    line: LineOrReference,
) -> LineOrReference {
    match line.try_map_reference_or_clone(|reference| {
        reference.try_with_normalized_project_reference(mapper)
    }) {
        Ok(mapped) => mapped,
        Err(_) => LineOrReference::Line(format!(
            "Failed trying to normalize reference {}",
            line.project_item_reference()
                .expect("only references can error")
        )),
    }
}

/// Normalize all project item refs in a note to use numeric project IDs
pub fn note_refs_to_ids(
    mapper: &mut ProjectMapper,
    lines: LineOrReferenceCollection,
) -> LineOrReferenceCollection {
    let lines = lines
        .0
        .into_iter()
        .map(|line| normalize_line_or_reference(mapper, line))
        .collect();
    LineOrReferenceCollection(lines)
}
