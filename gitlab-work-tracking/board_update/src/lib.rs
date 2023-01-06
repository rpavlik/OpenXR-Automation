// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab_work::{
    note::LineOrReference, GitLabItemReferenceNormalize, ProjectItemReference, ProjectMapper,
    UnitId, WorkUnitCollection,
};
use log::{info, warn};
use nullboard_tools::{GenericList, IntoGenericIter, List, ListIteratorAdapters};
use std::collections::{hash_map::Entry, HashMap};

pub mod cli;
pub mod note_formatter;

#[derive(Debug)]
pub struct Lines(pub Vec<LineOrReference>);

#[derive(Debug)]
pub struct ProcessedNote {
    unit_id: Option<UnitId>,
    lines: Lines,
}

impl From<ProcessedNote> for Lines {
    fn from(note: ProcessedNote) -> Self {
        note.lines
    }
}

/// Parse a (possibly multiline) string into lines that are each LineOrReference
pub fn parse_note(s: String) -> Lines {
    Lines(s.split('\n').map(LineOrReference::parse_line).collect())
}

/// Parse lists of notes, each containing a (possibly multiline) string into
/// lists of notes with data `Lines` that are each LineOrReference
pub fn parse_notes(lists: Vec<List>) -> Vec<GenericList<Lines>> {
    info!("Parsing notes");
    lists
        .into_generic_iter()
        .map_note_data(parse_note)
        .collect()
}

/// Associate a work unit with these lines
pub fn associate_work_unit_with_note(
    collection: &mut WorkUnitCollection,
    lines: Lines,
) -> ProcessedNote {
    let refs: Vec<ProjectItemReference> = lines
        .0
        .iter()
        .filter_map(LineOrReference::as_reference)
        .cloned()
        .collect();

    let unit_id = if refs.is_empty() {
        None
    } else {
        let result = collection.add_or_get_unit_for_refs(refs);
        if let Err(e) = &result {
            warn!("Problem calling add/get unit for refs: {}", e);
        }
        result.ok()
    };
    ProcessedNote { unit_id, lines }
}

// pub fn associate_work_unit_with_notes(
//     collection: &mut WorkUnitCollection,)
// {}

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
            line.as_reference().expect("only references can error")
        )),
    }
}

/// Normalize all project item refs in a note to use numeric project IDs
pub fn note_refs_to_ids(mapper: &mut ProjectMapper, lines: Lines) -> Lines {
    let lines = lines
        .0
        .into_iter()
        .map(|line| normalize_line_or_reference(mapper, line))
        .collect();
    Lines(lines)
}

const RECURSE_LIMIT: usize = 5;

/// Iterate through lists, removing notes that refer to a work unit
/// which already had a note output.
pub fn prune_notes<'a>(
    collection: &'a mut WorkUnitCollection,
    lists: impl IntoIterator<Item = GenericList<ProcessedNote>> + 'a,
) -> Vec<GenericList<ProcessedNote>> {
    // Mark those notes which should be skipped because they refer to a work unit that already has a card.
    let mut units_handled: HashMap<UnitId, ()> = Default::default();
    let filter_note = move |note: &ProcessedNote| {
        if let Some(id) = &note.unit_id {
            match collection.get_unit_id_following_extinction(*id, RECURSE_LIMIT) {
                Ok(id) => match units_handled.entry(id) {
                    Entry::Occupied(_) => {
                        // note.text.deleted = true;
                        warn!(
                            "Deleting note because its work unit was already handled: {} {:?}",
                            id, note.lines
                        );
                        false
                    }
                    Entry::Vacant(e) => {
                        e.insert(());
                        true
                    }
                },
                Err(e) => {
                    warn!("Got error trying to resolve ref, will keep: {}", e);
                    true
                }
            }
        } else {
            true
        }
    };

    lists.into_iter().filter_notes(filter_note).collect()
}
