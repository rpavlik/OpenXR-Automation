// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab_work::{
    note::LineOrReference, GitLabItemReferenceNormalize, ProjectItemReference, ProjectMapper,
    UnitId, WorkUnitCollection,
};
use log::warn;
use nullboard_tools::{GenericList, ListIteratorAdapters};
use std::collections::{hash_map::Entry, HashMap};

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

pub fn parse_note(s: String) -> Lines {
    Lines(s.split('\n').map(LineOrReference::parse_line).collect())
}

pub fn process_note_and_associate_work_unit(
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

pub fn normalize_line_or_reference(
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

pub fn note_project_refs_to_ids(mapper: &mut ProjectMapper, lines: Lines) -> Lines {
    let lines = lines
        .0
        .into_iter()
        .map(|line| normalize_line_or_reference(mapper, line))
        .collect();
    Lines(lines)
}

const RECURSE_LIMIT: usize = 5;

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
