// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use anyhow::Error;
use clap::Parser;
use dotenvy::dotenv;
use gitlab_work::{note::LineOrReference, ProjectItemReference, UnitId, WorkUnitCollection};
use log::warn;
use nullboard_tools::GenericList;
use std::{
    collections::{hash_map::Entry, HashMap},
    path::Path,
};

#[derive(Parser, Debug)]
struct Args {
    #[arg()]
    filename: String,
}

#[derive(Debug)]
struct ProcessedNote {
    unit_id: Option<UnitId>,
    lines: Vec<LineOrReference>,
    deleted: bool,
}

fn parse_and_process_note(collection: &mut WorkUnitCollection, s: &str) -> ProcessedNote {
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

fn mark_notes_for_deletion(
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

fn main() -> Result<(), anyhow::Error> {
    dotenv()?;
    env_logger::init();
    let args = Args::parse();

    let path = Path::new(&args.filename);

    // let out_fn = path
    //     .file_stem()
    //     .map(|p| {
    //         let mut p = p.to_owned();
    //         p.push(".updated.json");
    //         p
    //     })
    //     .ok_or_else(|| anyhow!("Could not get file stem"))?;
    // let out_path = path.with_file_name(out_fn);

    let board = nullboard_tools::Board::load_from_json(path)?;

    let mut collection = WorkUnitCollection::default();
    let mut parsed_lists = vec![];
    // Parse all notes and process them into work units
    for list in board.lists {
        parsed_lists.push(list.map_note_text(|text| parse_and_process_note(&mut collection, text)));
    }

    mark_notes_for_deletion(&mut parsed_lists, &collection)?;
    // (board.lists.iter().map(|list| GenericList { title: list.title.clone(),notes: }))
    // for note in notes_iter {
    //     let lines = parse_note(&note.text);
    //     let note = process_note(&mut collection, lines)?;
    //     info!("{:?}", note);
    // }

    Ok(())
}
