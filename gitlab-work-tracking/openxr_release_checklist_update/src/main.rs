// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{
    board_operation::BoardOperation,
    find_more::{find_new_checklists, find_new_notes},
    prettyprint::{PrettyData, PrettyForConsole},
};
use anyhow::anyhow;
use clap::Parser;
use dotenvy::dotenv;
use env_logger::Env;
use gitlab_work_units::{
    lookup::{GitlabQueryCache, ItemState},
    ProjectItemReference, ProjectMapper, WorkUnitCollection,
};
use log::{info, warn};
use nullboard_tools::{list::BasicList, Board, ListCollection, ListIteratorAdapters};
use pretty::DocAllocator;
use std::path::Path;
use workboard_update::{
    associate_work_unit_with_note,
    cli::{GitlabArgs, InputOutputArgs, ProjectArgs},
    find_more::find_issues,
    line_or_reference::{self, LineOrReferenceCollection, ProcessedNote},
    note_formatter, note_refs_to_ids, prune_notes,
    traits::GetItemReference,
};

mod board_operation;
mod find_more;
mod prettyprint;

#[derive(Parser)]
struct Cli {
    #[command(flatten, next_help_heading = "Input/output")]
    input_output: InputOutputArgs,

    #[command(flatten, next_help_heading = "GitLab")]
    gitlab: GitlabArgs,

    #[command(flatten, next_help_heading = "Project")]
    project: ProjectArgs,
}

fn get_mr_statuses<'a, L: GetItemReference + 'a, I: Iterator<Item = &'a L>>(
    client: &gitlab::Gitlab,
    cache: &mut GitlabQueryCache,
    lines: I,
) -> Result<Vec<ItemState>, gitlab_work_units::Error> {
    lines
        .filter_map(GetItemReference::project_item_reference)
        .filter(|&reference| ProjectItemReference::is_merge_request(reference))
        .map(|reference| cache.query(client, reference).map(|data| data.state()))
        .collect()
}

fn get_mr_merged_closed_count<'a, L: GetItemReference + 'a, I: Iterator<Item = &'a L>>(
    client: &gitlab::Gitlab,
    cache: &mut GitlabQueryCache,
    lines: I,
) -> Result<(usize, usize, usize), gitlab_work_units::Error> {
    let statuses = get_mr_statuses(client, cache, lines)?;
    let (num_merged, num_closed) = statuses.iter().fold((0, 0), |(merged, closed), state| {
        (
            (merged + usize::from(state == &ItemState::Merged)),
            (closed + usize::from(state == &ItemState::Closed)),
        )
    });
    Ok((statuses.len(), num_merged, num_closed))
}

fn all_mrs_merged<'a, L: GetItemReference + 'a, I: Iterator<Item = &'a L>>(
    client: &gitlab::Gitlab,
    cache: &mut GitlabQueryCache,
    lines: I,
) -> Result<bool, anyhow::Error> {
    let (num_mrs, num_merged, num_closed) = get_mr_merged_closed_count(client, cache, lines)?;

    if num_mrs == 0 || num_mrs > (num_merged + num_closed) {
        Ok(false)
    } else {
        Ok(num_merged > num_closed)
    }
}

fn find_notes_to_move(_ops: &mut Vec<BoardOperation>, _lists: impl ListCollection) {}

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
        .map_note_data(line_or_reference::parse_note)
        .map_note_data(|data| {
            LineOrReferenceCollection(note_refs_to_ids(&mut mapper, data.0.into_iter()))
        })
        .map_note_data(|note_data| {
            let unit_id = associate_work_unit_with_note(&mut collection, note_data.0.iter());
            ProcessedNote::new(unit_id, note_data)
        })
        .collect();

    let mut changes = vec![];

    info!("Looking for new checklists");
    if let Ok(new_checklists) = find_new_checklists(&gitlab, &args.project.default_project) {
        for (issue_data, note) in find_new_notes(&mut collection, new_checklists) {
            changes.push(BoardOperation::AddNote {
                list_name: "Initial Composition".to_owned(),
                note,
            })
        }
    }

    let mut cache: GitlabQueryCache = Default::default();
    let project_name = args.project.default_project.as_str();
    info!("Seeing if any are missing labels");
    {
        let issue_endpoint = gitlab::api::projects::issues::Issues::builder()
            .project(project_name)
            .search("\"Release checklist for\"")
            .state(gitlab::api::issues::IssueState::Opened)
            .build()
            .map_err(|e| anyhow!("Endpoint issue building failed: {}", e))?;
        let issues_and_refs = find_issues(&gitlab, issue_endpoint)?.and_related_mrs(project_name);
        for (issue_data, refs) in issues_and_refs {
            if issue_data.title().starts_with("Release") {
                let reference = ProjectItemReference::from(&issue_data);
                if collection.try_get_unit_for_ref(&reference).is_none() {
                    warn!(
                        "Found an issue that looks like a checklist but missing the label: {} {}\n{}",
                        reference,
                        issue_data.title(),
                        issue_data.web_url()
                    );
                }
            }
        }
    }

    let default_project_id = mapper.default_project_id();
    {
        let allocator = pretty::BoxAllocator;

        let mut w = Vec::new();
        let mut data = PrettyData {
            default_project_id,
            client: &gitlab,
            cache: &mut cache,
        };
        allocator
            .intersperse(
                changes
                    .iter()
                    .map(|c| c.pretty::<_, ()>(&allocator, &mut data)),
                allocator.hardline(),
            )
            .into_doc()
            .render(80, &mut w)?;
        let s = std::str::from_utf8(&w).unwrap_or("<invalid utf-8>");

        info!("Proposed changes:\n{}", s);
    }

    for change in changes {
        change.apply(&mut lists)?;
    }

    info!("Pruning notes");
    let lists = prune_notes(&collection, lists);

    info!("Re-generating notes for export");
    let updated_board = board.make_new_revision_with_lists(
        lists
            .into_iter()
            .map_note_data(|proc_note: ProcessedNote| {
                note_formatter::format_note(
                    &gitlab,
                    &mut cache,
                    proc_note.into(),
                    &mapper,
                    |title| {
                        title
                            .trim_start_matches("Release checklist for ")
                            .trim_start_matches("Resolve ")
                    },
                )
            })
            .map(BasicList::from),
    );

    let (hits, queries) = cache.cache_stats();
    let percent = if queries == 0 {
        f64::from(0)
    } else {
        f64::from(hits) / f64::from(queries)
    };

    info!(
        "Cache stats: {} hits out of {} queries ({} %)",
        hits, queries, percent
    );

    info!("Writing to {}", out_path.display());
    updated_board.save_to_json(&out_path)?;
    Ok(())
}
