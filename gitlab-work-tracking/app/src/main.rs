// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use board_update::{mark_notes_for_deletion, parse_and_process_note};
use clap::{Args, Parser};
use gitlab_work::WorkUnitCollection;
use std::path::Path;
// use clap::{arg, command, value_parser, ArgAction, Command};
use dotenvy::dotenv;
mod board_update;

#[derive(Args, Debug, Clone)]
// #[command(PARENT CMD ATTRIBUTE)]
// #[command(next_help_heading = "GitLab access details")]
struct GitlabArgs {
    #[arg(long = "gitlab", env = "GL_URL")]
    gitlab_url: String,

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

    #[command(flatten, next_help_heading = "GitLab access details")]
    // #[arg()]
    gitlab: Option<GitlabArgs>,
}

fn main() -> Result<(), anyhow::Error> {
    dotenv()?;
    env_logger::init();
    let args = Cli::parse();

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
