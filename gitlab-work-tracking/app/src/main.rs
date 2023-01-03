use std::path::Path;

use anyhow::{anyhow, Error};
use clap::Parser;
use dotenvy::dotenv;
use gitlab_work::{note::NoteLine, ProjectItemReference, UnitId, WorkUnitCollection};
use log::info;

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

    let notes_iter = board.lists.iter().flat_map(|list| list.notes.iter());
    let mut collection = WorkUnitCollection::default();
    for note in notes_iter {
        let lines = parse_note(&note.text);
        let note = process_note(&mut collection, lines)?;
        info!("{:?}", note);
    }

    Ok(())
}
