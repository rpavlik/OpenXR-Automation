// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::find_more::{find_new_checklists, find_new_notes};
use board_update::{
    associate_work_unit_with_note,
    cli::{GitlabArgs, InputOutputArgs, ProjectArgs},
    note_formatter, note_refs_to_ids, parse_owned_note, prune_notes, ProcessedNote,
};
use clap::Parser;
use dotenvy::dotenv;
use env_logger::Env;
use gitlab_work::{ProjectMapper, WorkUnitCollection};
use log::info;
use nullboard_tools::{
    list::BasicList, Board, GenericNote, List, ListCollection, ListIteratorAdapters,
};
use std::path::Path;

mod find_more;

#[derive(Parser)]
struct Cli {
    #[command(flatten, next_help_heading = "Input/output")]
    input_output: InputOutputArgs,

    #[command(flatten, next_help_heading = "GitLab")]
    gitlab: GitlabArgs,

    #[command(flatten, next_help_heading = "Project")]
    project: ProjectArgs,
}

// We need extra collect calls to make sure some things are evaluated eagerly.
#[allow(clippy::needless_collect)]
fn main() -> Result<(), anyhow::Error> {
    // Load .env file if available for credentials and config
    dotenv()?;

    // Set up logging, defaulting to "info" so we actually show some progress messages
    env_logger::Builder::from_env(Env::default().default_filter_or("info")).init();

    let args = Cli::parse();

    let path = Path::new(&args.input_output.filename);

    let out_path = args.input_output.try_output_path()?;

    let gitlab = args.gitlab.as_gitlab_builder().build()?;

    let mut mapper: ProjectMapper = args.project.to_project_mapper(&gitlab)?;

    info!("Loading board from {}", path.display());

    let mut board = nullboard_tools::BasicBoard::load_from_json(path)?;

    let mut collection = WorkUnitCollection::default();

    info!("Processing board notes");
    let mut lists: Vec<_> = board
        .take_lists()
        .into_iter()
        .map_note_data(parse_owned_note)
        .map_note_data(|data| note_refs_to_ids(&mut mapper, data))
        .map_note_data(|note_data| associate_work_unit_with_note(&mut collection, note_data))
        .collect();

    info!("Looking for new checklists");
    if let Ok(new_checklists) = find_new_checklists(&gitlab, &args.project.default_project) {
        let list = lists
            .named_list_mut("Initial Composition")
            .expect("need initial composition list");
        for (issue_data, note) in find_new_notes(&mut collection, new_checklists) {
            info!("Adding note for {}", issue_data.title());
            list.notes_mut().push(GenericNote::new(note));
        }
    }

    info!("Pruning notes");
    let lists = prune_notes(&collection, lists);

    info!("Re-generating notes for export");
    let updated_board = board.make_new_revision_with_lists(
        lists
            .into_iter()
            .map_note_data(|proc_note: ProcessedNote| {
                note_formatter::format_note(proc_note.into(), &mapper, |title| {
                    title
                        .trim_start_matches("Release checklist for ")
                        .trim_start_matches("Resolve ")
                })
            })
            .map(BasicList::from),
    );

    info!("Writing to {}", out_path.display());
    updated_board.save_to_json(&out_path)?;
    Ok(())
}
