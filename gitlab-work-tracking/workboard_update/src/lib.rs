// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab_work_units::{
    GitLabItemReferenceNormalize, ProjectItemReference, ProjectMapper, RefAddOutcome, UnitId,
    WorkUnitCollection,
};
use line_or_reference::LineOrReferenceCollection;
use log::warn;
use nullboard_tools::{GenericList, ListIteratorAdapters};
use std::collections::{hash_map::Entry, HashMap};
use traits::{GetItemReference, ParsedLineLike};

pub mod cli;
pub mod line_or_reference;
pub mod note_formatter;
pub mod note_line;
pub mod traits;
pub use traits::GetWorkUnit;

// I think this should be more than enough: in normal operation I don't actually see this used at all.
const RECURSE_LIMIT: usize = 5;

/// Returns a closure that will filter notes based on whether another note with the same UnitId has been seen.
pub fn make_note_pruner<T: GetWorkUnit + std::fmt::Debug>(
    collection: &'_ WorkUnitCollection,
) -> impl '_ + FnMut(&T) -> bool {
    // Mark those notes which should be skipped because they refer to a work unit that already has a note.
    let mut units_handled: HashMap<UnitId, ()> = Default::default();

    // here we are creating and immediately returning this closure.
    // `move` moves the HashMap into the closure.
    move |note: &T| {
        if let Some(id) = note.work_unit_id() {
            match collection.get_unit_id_following_extinction(*id, RECURSE_LIMIT) {
                Ok(id) => match units_handled.entry(id) {
                    Entry::Occupied(_) => {
                        warn!(
                            "Skipping note because its work unit was already handled: {} {:#?}",
                            id, note
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
pub fn prune_notes<T: GetWorkUnit + std::fmt::Debug>(
    collection: &WorkUnitCollection,
    lists: impl IntoIterator<Item = GenericList<T>>,
) -> Vec<GenericList<T>> {
    lists
        .into_iter()
        .filter_notes(make_note_pruner(collection))
        .collect()
}

/// Transform an item reference line into its "normalized" state, with a numeric project ID
///
/// Turns any errors into an error message in the line.
pub fn normalize_possible_reference<T: ParsedLineLike>(mapper: &mut ProjectMapper, line: T) -> T {
    match line.try_map_reference_or_clone(|reference| {
        reference.try_with_normalized_project_reference(mapper)
    }) {
        Ok(mapped) => mapped,
        Err(_) => T::from(format!(
            "Failed trying to normalize reference {}",
            line.project_item_reference()
                .expect("only references can error")
        )),
    }
}

/// Normalize all project item refs in a note to use numeric project IDs
pub fn note_refs_to_ids<T: ParsedLineLike>(
    mapper: &mut ProjectMapper,
    lines: impl IntoIterator<Item = T>,
) -> Vec<T> {
    lines
        .into_iter()
        .map(|line| normalize_possible_reference(mapper, line))
        .collect()
}

/// Associate a work unit with these lines
pub fn associate_work_unit_with_note<'a, L, I>(
    collection: &mut WorkUnitCollection,
    lines: I,
) -> Option<UnitId>
where
    L: ParsedLineLike + 'a,
    I: Iterator<Item = &'a L>,
{
    let refs: Vec<&ProjectItemReference> = lines
        .filter_map(GetItemReference::project_item_reference)
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
    unit_id
}
