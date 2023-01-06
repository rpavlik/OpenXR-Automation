// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab_work::{
    note::LineOrReference, GitLabItemReferenceNormalize, ProjectItemReference, ProjectMapper,
    RefAddOutcome, UnitId, WorkUnitCollection,
};
use log::{info, warn};
use nullboard_tools::{list::BasicList, GenericList, ListIteratorAdapters};
use std::{
    borrow::Cow,
    collections::{hash_map::Entry, HashMap},
};

pub mod cli;
pub mod note_formatter;

#[derive(Debug)]
pub struct Lines<'a>(pub Vec<LineOrReference<'a>>);

#[derive(Debug)]
pub struct ProcessedNote<'a> {
    unit_id: Option<UnitId>,
    lines: Lines<'a>,
}

impl<'a> ProcessedNote<'a> {
    pub fn new(unit_id: Option<UnitId>, lines: Lines<'a>) -> Self {
        Self { unit_id, lines }
    }
}

impl<'a> From<ProcessedNote<'a>> for Lines<'a> {
    fn from(note: ProcessedNote<'a>) -> Self {
        note.lines
    }
}

/// Parse a (possibly multiline) string into lines that are each LineOrReference
pub fn parse_note<'a>(s: &str) -> Lines<'a> {
    Lines(
        s.split('\n')
            .map(|line| LineOrReference::parse_owned_line(line.to_owned()))
            .collect(),
    )
}

/// Parse a (possibly multiline) string into lines that are each LineOrReference
pub fn parse_owned_note<'a>(s: String) -> Lines<'a> {
    Lines(
        s.split('\n')
            .map(|line| LineOrReference::parse_owned_line(line.to_owned()))
            .collect(),
    )
}

/// Parse lists of notes, each containing a (possibly multiline) string into
/// lists of notes with data `Lines` that are each LineOrReference
pub fn parse_notes<'a>(lists: Vec<BasicList>) -> Vec<GenericList<Lines<'a>>> {
    info!("Parsing notes");
    lists.into_iter().map_note_data(parse_owned_note).collect()
}

/// Associate a work unit with these lines
pub fn associate_work_unit_with_note<'a>(
    collection: &mut WorkUnitCollection,
    lines: Lines<'a>,
) -> ProcessedNote<'a> {
    let refs: Vec<&ProjectItemReference> = lines
        .0
        .iter()
        .filter_map(LineOrReference::as_reference)
        .collect();

    let unit_id = if refs.is_empty() {
        None
    } else {
        let result = collection.add_or_get_unit_for_refs(refs);
        if let Err(e) = &result {
            warn!("Problem calling add/get unit for refs: {}", e);
        }
        result.ok().map(RefAddOutcome::into_inner_unit_id)
    };
    ProcessedNote { unit_id, lines }
}

/// Transform an item reference line into its "normalized" state, with a numeric project ID
///
/// Turns any errors into an error message in the line.
fn normalize_line_or_reference<'a>(
    mapper: &mut ProjectMapper,
    line: LineOrReference<'a>,
) -> LineOrReference<'a> {
    match line.try_map_reference_or_clone(|reference| {
        reference.try_with_normalized_project_reference(mapper)
    }) {
        Ok(mapped) => mapped,
        Err(_) => {
            let message = format!(
                "Failed trying to normalize reference {}",
                line.as_reference().expect("only references can error")
            );
            LineOrReference::Line(Cow::Owned(message))
        }
    }
}

/// Normalize all project item refs in a note to use numeric project IDs
pub fn note_refs_to_ids<'a>(mapper: &mut ProjectMapper, lines: Lines<'a>) -> Lines<'a> {
    let lines = lines
        .0
        .into_iter()
        .map(|line| normalize_line_or_reference(mapper, line))
        .collect();
    Lines(lines)
}

// I think this should be more than enough: in normal operation I don't actually see this used at all.
const RECURSE_LIMIT: usize = 5;

/// Returns a closure that will filter notes based on whether another note with the same UnitId has been seen.
pub fn make_note_pruner(
    collection: &'_ WorkUnitCollection,
) -> impl '_ + FnMut(&ProcessedNote) -> bool {
    // Mark those notes which should be skipped because they refer to a work unit that already has a note.
    let mut units_handled: HashMap<UnitId, ()> = Default::default();

    // here we are creating and immediately returning this closure.
    // `move` moves the HashMap into the closure.
    move |note: &ProcessedNote| {
        if let Some(id) = &note.unit_id {
            match collection.get_unit_id_following_extinction(*id, RECURSE_LIMIT) {
                Ok(id) => match units_handled.entry(id) {
                    Entry::Occupied(_) => {
                        warn!(
                            "Skipping note because its work unit was already handled: {} {:?}",
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
    }
}

/// Iterate through lists, removing notes that refer to a work unit
/// which already had a note output.
pub fn prune_notes<'a>(
    collection: &WorkUnitCollection,
    lists: impl 'a + IntoIterator<Item = GenericList<'a, ProcessedNote<'a>>>,
) -> Vec<GenericList<'a, ProcessedNote<'a>>> {
    lists
        .into_iter()
        .filter_notes(make_note_pruner(collection))
        .collect()
}
