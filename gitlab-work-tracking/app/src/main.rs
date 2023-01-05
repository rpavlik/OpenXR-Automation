// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use anyhow::anyhow;
use board_update::{
    note_formatter, parse_note, process_lists_and_associate_work_units, project_refs_to_ids,
    prune_notes,
};
use clap::{Args, Parser};
use dotenvy::dotenv;
use gitlab_work::{ProjectMapper, WorkUnitCollection};
use log::info;
use nullboard_tools::map_note_data_in_lists;
use std::path::Path;

#[derive(Args, Debug, Clone)]
// #[command(PARENT CMD ATTRIBUTE)]
// #[command(next_help_heading = "GitLab access details")]
struct GitlabArgs {
    #[arg(long = "gitlab", env = "GL_DOMAIN")]
    gitlab_domain: String,

    #[arg(long = "username", env = "GL_USERNAME")]
    gitlab_username: String,

    #[arg(long = "token", env = "GL_ACCESS_TOKEN", hide_env_values = true)]
    gitlab_access_token: String,

    #[arg(long, short = 'p', env = "GL_DEFAULT_PROJECT")]
    default_project: String,

    #[arg(long, env = "GL_DEFAULT_PROJECT_FORMAT_AS")]
    default_project_format_as: Option<String>,
}

#[derive(Parser)]
struct Cli {
    #[arg()]
    filename: String,

    #[command(flatten, next_help_heading = "GitLab details")]
    gitlab: GitlabArgs,
}

fn main() -> Result<(), anyhow::Error> {
    dotenv()?;
    env_logger::init();
    let args = Cli::parse();

    let path = Path::new(&args.filename);

    let out_fn = path
        .file_stem()
        .map(|p| {
            let mut p = p.to_owned();
            p.push(".updated.json");
            p
        })
        .ok_or_else(|| anyhow!("Could not get file stem"))?;
    let out_path = path.with_file_name(out_fn);

    info!("Connecting to GitLab: {}", &args.gitlab.gitlab_domain);

    let gitlab =
        gitlab::GitlabBuilder::new(args.gitlab.gitlab_domain, args.gitlab.gitlab_access_token)
            .build()?;
    let mut mapper = ProjectMapper::new(gitlab, &args.gitlab.default_project)?;
    if let Some(default_formatting) = args.gitlab.default_project_format_as {
        mapper.try_set_project_name_formatting(None, &default_formatting)?;
    }

    info!("Loading board from {}", path.display());

    let mut board = nullboard_tools::Board::load_from_json(path)?;

    info!("Parsing notes");
    let mut parsed_lists = vec![];
    // Parse all notes
    for list in board.take_lists() {
        parsed_lists.push(list.map_notes(parse_note));
    }

    info!("Normalizing item references");
    let parsed_lists: Vec<_> = project_refs_to_ids(&mut mapper, parsed_lists).collect();

    info!("Processing notes and associating with work units");
    let mut collection = WorkUnitCollection::default();

    let lists: Vec<_> =
        process_lists_and_associate_work_units(&mut collection, parsed_lists).collect();

    info!("Pruning notes");
    let lists = prune_notes(&mut collection, lists);

    info!("Re-generating notes for export");
    let updated_board =
        board.make_new_revision_with_lists(map_note_data_in_lists(lists, |proc_note| {
            note_formatter::format_note(proc_note.into(), &mapper, |title| {
                title
                    .trim_start_matches("Release checklist for ")
                    .trim_start_matches("Resolve ")
            })
        }));

    println!("Writing to {}", out_path.display());
    updated_board.save_to_json(&out_path)?;
    Ok(())
}
