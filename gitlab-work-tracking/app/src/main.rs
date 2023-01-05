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
use nullboard_tools::map_note_data_in_lists;
use std::path::{Path, PathBuf};

#[derive(Args, Debug, Clone)]
struct GitlabArgs {
    /// Domain name hosting your GitLab instance
    #[arg(long = "gitlab", env = "GL_DOMAIN")]
    gitlab_domain: String,

    /// Private access token to use when accessing GitLab.
    #[arg(long = "token", env = "GL_ACCESS_TOKEN", hide_env_values = true)]
    gitlab_access_token: String,

    /// Fully qualified project name to assume for MRs and issues with no project specified
    #[arg(long, short = 'p', env = "GL_DEFAULT_PROJECT")]
    default_project: String,

    /// How to format the default project in the output. If not specified, the default project name is omitted from exported text references.
    #[arg(long, env = "GL_DEFAULT_PROJECT_FORMAT_AS")]
    default_project_format_as: Option<String>,
}

#[derive(Parser)]
struct Cli {
    /// The JSON export from Nullboard (or compatible format) - usually ends in .nbx
    #[arg()]
    filename: PathBuf,

    /// Output filename: the extension .nbx is suggested. Will be computed if not specified.
    #[arg(short, long)]
    output: Option<PathBuf>,

    #[command(flatten, next_help_heading = "GitLab details")]
    gitlab: GitlabArgs,
}

fn main() -> Result<(), anyhow::Error> {
    dotenv()?;
    env_logger::init();
    let args = Cli::parse();

    let path = Path::new(&args.filename);

    let out_path = args.output.map_or_else(
        // come up with a default output name
        || {
            path.file_stem()
                .map(|p| {
                    let mut p = p.to_owned();
                    p.push(".updated.nbx");
                    p
                })
                .map(|file_name| path.with_file_name(file_name))
                .ok_or_else(|| anyhow!("Could not get file stem"))
        },
        // or wrap our existing one in Ok
        Ok,
    )?;

    println!("Connecting to GitLab: {}", &args.gitlab.gitlab_domain);

    let gitlab =
        gitlab::GitlabBuilder::new(args.gitlab.gitlab_domain, args.gitlab.gitlab_access_token)
            .build()?;
    let mut mapper = ProjectMapper::new(gitlab, &args.gitlab.default_project)?;
    if let Some(default_formatting) = args.gitlab.default_project_format_as {
        mapper.try_set_project_name_formatting(None, &default_formatting)?;
    }

    println!("Loading board from {}", path.display());

    let mut board = nullboard_tools::Board::load_from_json(path)?;

    println!("Parsing notes");
    let mut parsed_lists = vec![];
    // Parse all notes
    for list in board.take_lists() {
        parsed_lists.push(list.map_notes(parse_note));
    }

    println!("Normalizing item references");
    let parsed_lists: Vec<_> = project_refs_to_ids(&mut mapper, parsed_lists).collect();

    println!("Processing notes and associating with work units");
    let mut collection = WorkUnitCollection::default();

    let lists: Vec<_> =
        process_lists_and_associate_work_units(&mut collection, parsed_lists).collect();

    println!("Pruning notes");
    let lists = prune_notes(&mut collection, lists);

    println!("Re-generating notes for export");
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
