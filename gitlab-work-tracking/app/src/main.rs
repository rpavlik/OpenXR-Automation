use std::{
    collections::{hash_map::Entry, HashMap, HashSet},
    iter::zip,
    path::Path,
};

use anyhow::{anyhow, Error};
use clap::Parser;
use dotenvy::dotenv;
use gitlab_work::{note::NoteLine, ProjectItemReference, UnitId, WorkUnitCollection};
use itertools::{repeat_n, Itertools};
use log::{info, warn};
use nullboard_tools::{GenericList, GenericLists};

#[derive(Parser, Debug)]
struct Args {
    #[arg()]
    filename: String,
}

#[derive(Debug)]
enum LineOrGitlabRef {
    FreeformText(String),
    GitlabRef(ProjectItemReference),
}

fn parse_note(s: &str) -> Vec<LineOrGitlabRef> {
    s.split("\n")
        .map(NoteLine::parse_line)
        .map(|l| {
            if let Some(reference) = l.reference {
                LineOrGitlabRef::GitlabRef(reference)
            } else {
                LineOrGitlabRef::FreeformText(l.line)
            }
        })
        .collect()
}

#[derive(Debug)]
struct ProcessedNote {
    unit_id: Option<UnitId>,
    lines: Vec<LineOrGitlabRef>,
    deleted: bool,
}

fn parse_and_process_note(collection: &mut WorkUnitCollection, s: &str) -> ProcessedNote {
    let lines: Vec<_> = s
        .split("\n")
        .map(NoteLine::parse_line)
        .map(|l| {
            if let Some(reference) = l.reference {
                LineOrGitlabRef::GitlabRef(reference)
            } else {
                LineOrGitlabRef::FreeformText(l.line)
            }
        })
        .collect();

    let refs: Vec<ProjectItemReference> = lines
        .iter()
        .filter_map(|line| match line {
            LineOrGitlabRef::FreeformText(_) => None,
            LineOrGitlabRef::GitlabRef(reference) => Some(reference),
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

fn process_note(
    collection: &mut WorkUnitCollection,
    note: Vec<LineOrGitlabRef>,
) -> Result<ProcessedNote, Error> {
    let refs: Vec<ProjectItemReference> = note
        .iter()
        .filter_map(|line| match line {
            LineOrGitlabRef::FreeformText(_) => None,
            LineOrGitlabRef::GitlabRef(reference) => Some(reference),
        })
        .cloned()
        .collect();
    let unit_id = if refs.is_empty() {
        None
    } else {
        Some(collection.add_or_get_unit_for_refs(refs)?)
    };
    Ok(ProcessedNote {
        unit_id,
        lines: note,
        deleted: false,
    })
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

    // let notes_iter = board
    //     .lists
    //     .iter()
    //     .flat_map(|list| zip(repeat_n(list, list.notes.len()), list.notes.iter()));
    let mut collection = WorkUnitCollection::default();
    let mut parsed_lists = vec![];
    for list in board.lists {
        parsed_lists.push(list.map_note_text(|text| parse_and_process_note(&mut collection, text)));
    }
    let mut units_handled: HashMap<UnitId, ()> = Default::default();
    for list in parsed_lists.iter_mut() {
        for note in &mut list.notes {
            if let Some(id) = &note.text.unit_id {
                let (id, _) = collection.get_unit_following_extinction(*id, 5)?;
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
    // let mut updated_lists = vec![];
    // for list in parsed_lists {
    //     updated_lists.push(list.notes.into_iter().unique_by(|n| n.t))
    // }
    // let mut processed_lists = vec![];
    // let mut collection = WorkUnitCollection::default();
    // for list in parsed_lists.0.iter().rev() {
    //     /// generate units in right-to-left list order
    //     processed_lists.push(list.map_note_text(|lines| process_note(&mut collection, lines)))
    // }

    // (board.lists.iter().map(|list| GenericList { title: list.title.clone(),notes: }))
    // for note in notes_iter {
    //     let lines = parse_note(&note.text);
    //     let note = process_note(&mut collection, lines)?;
    //     info!("{:?}", note);
    // }

    Ok(())
}
