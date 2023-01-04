// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use anyhow::Error;
use gitlab_work::{note::LineOrReference, ProjectItemReference, UnitId, WorkUnitCollection};
use log::warn;
use nullboard_tools::GenericList;
use std::collections::{hash_map::Entry, HashMap};

#[derive(Debug)]
pub struct ProcessedNote {
    unit_id: Option<UnitId>,
    lines: Vec<LineOrReference>,
    deleted: bool,
}

pub fn parse_and_process_note(collection: &mut WorkUnitCollection, s: &str) -> ProcessedNote {
    let lines: Vec<_> = s.split('\n').map(LineOrReference::parse_line).collect();

    let refs: Vec<ProjectItemReference> = lines
        .iter()
        .filter_map(|line| match line {
            LineOrReference::Line(_) => None,
            LineOrReference::Reference(reference) => Some(reference),
        })
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
    ProcessedNote {
        unit_id,
        lines,
        deleted: false,
    }
}

const RECURSE_LIMIT: usize = 5;

pub fn mark_notes_for_deletion(
    lists: &mut Vec<GenericList<ProcessedNote>>,
    collection: &WorkUnitCollection,
) -> Result<(), Error> {
    // Mark those notes which should be skipped because they refer to a work unit that already has a card.
    let mut units_handled: HashMap<UnitId, ()> = Default::default();
    for list in lists.iter_mut() {
        for note in &mut list.notes {
            if let Some(id) = &note.text.unit_id {
                let id = collection.get_unit_id_following_extinction(*id, RECURSE_LIMIT)?;
                match units_handled.entry(id) {
                    Entry::Occupied(_) => {
                        note.text.deleted = true;
                        warn!(
                            "Deleting note because its work unit was already handled: {} {:?}",
                            id, note.text.lines
                        );
                    }
                    Entry::Vacant(e) => {
                        note.text.unit_id = Some(id);
                        e.insert(());
                    }
                }
            }
        }
    }
    Ok(())
}
