// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use board_update::{
    mark_notes_for_deletion, parse_and_process_note, parse_note,
    process_note_and_associate_work_unit, Lines,
};
use clap::{Args, Parser};
use gitlab_work::{LineOrReference, ProjectMapper, TypedGitLabItemReference, WorkUnitCollection};
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

    #[command(flatten, next_help_heading = "GitLab details")]
    gitlab: GitlabArgs,
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

    let gitlab =
        gitlab::GitlabBuilder::new(args.gitlab.gitlab_url, args.gitlab.gitlab_access_token)
            .build()?;
    let mut mapper = ProjectMapper::new(gitlab, &args.gitlab.default_project)?;
    if let Some(default_formatting) = args.gitlab.default_project_format_as {
        mapper.try_set_project_name_formatting(None, &default_formatting)?;
    }

    let board = nullboard_tools::Board::load_from_json(path)?;

    let mut parsed_lists = vec![];
    // Parse all notes
    for list in board.lists {
        parsed_lists.push(list.map_note_text(|text| parse_note(text)));
    }

    // Map all references
    // parsed_lists.into_iter().map(|)
    for list in &mut parsed_lists {

        // for note: &mut Vec<LineOrReference> in &mut list {
        //     for line: &mut LineOrReference in &mut note {

        //     }
        // }
    }

    let mut collection = WorkUnitCollection::default();

    let mut processed_lists = vec![];

    for list in parsed_lists {
        processed_lists.push(list.map_note_text(|text| {
            process_note_and_associate_work_unit(&mut collection, Lines(text.0.clone()))
        }));
    }

    mark_notes_for_deletion(&mut processed_lists, &collection)?;
    // (board.lists.iter().map(|list| GenericList { title: list.title.clone(),notes: }))
    // for note in notes_iter {
    //     let lines = parse_note(&note.text);
    //     let note = process_note(&mut collection, lines)?;
    //     info!("{:?}", note);
    // }

    Ok(())
}
