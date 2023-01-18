// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::find_more::{find_mr, process_new_issues};
use anyhow::anyhow;
use clap::Parser;
use dotenvy::dotenv;
use env_logger::Env;
use gitlab_work_units::{
    lookup::{GitlabQueryCache, ItemState},
    ProjectItemReference, ProjectMapper, UnitId, WorkUnitCollection,
};
use log::info;
use nullboard_tools::{
    list::BasicList, Board, GenericList, GenericNote, List, ListCollection, ListIteratorAdapters,
    Note,
};
use std::path::Path;
use workboard_update::{
    associate_work_unit_with_note,
    cli::{GitlabArgs, InputOutputArgs},
    find_more::find_issues_and_related_mrs,
    line_or_reference::{self, LineOrReferenceCollection, ProcessedNote},
    note_formatter, note_refs_to_ids, prune_notes,
    traits::GetItemReference,
    GetWorkUnit,
};

mod find_more;

#[derive(Parser)]
struct Cli {
    #[command(flatten, next_help_heading = "Input/output")]
    input_output: InputOutputArgs,

    #[command(flatten, next_help_heading = "GitLab")]
    gitlab: GitlabArgs,
}

#[derive(Debug)]
enum BoardOperation {
    NoOp,
    AddNote {
        list_name: String,
        note: ProcessedNote,
    },
    MoveNote {
        current_list_name: String,
        new_list_name: String,
        work_unit_id: UnitId,
    },
}
impl Default for BoardOperation {
    fn default() -> Self {
        Self::NoOp
    }
}

impl BoardOperation {
    pub fn apply(
        self,
        lists: &mut impl ListCollection<List = GenericList<ProcessedNote>>,
    ) -> Result<(), anyhow::Error> {
        match self {
            BoardOperation::NoOp => Ok(()),
            BoardOperation::AddNote { list_name, note } => {
                let list = lists
                    .named_list_mut(&list_name)
                    .ok_or_else(|| anyhow::anyhow!("Could not find list {}", &list_name))?;
                list.notes_mut().push(GenericNote::new(note));
                Ok(())
            }
            BoardOperation::MoveNote {
                current_list_name,
                new_list_name,
                work_unit_id,
            } => {
                let note = {
                    let current_list =
                        lists.named_list_mut(&current_list_name).ok_or_else(|| {
                            anyhow::anyhow!("Could not find current list {}", &current_list_name)
                        })?;
                    let needle = current_list
                        .notes_mut()
                        .iter()
                        .position(|n| n.data().work_unit_id() == &Some(work_unit_id))
                        .ok_or_else(|| {
                            anyhow::anyhow!(
                                "Could not find note with matching work unit id {}",
                                work_unit_id
                            )
                        })?;
                    current_list.notes_mut().remove(needle)
                };
                let new_list = lists
                    .named_list_mut(&new_list_name)
                    .ok_or_else(|| anyhow::anyhow!("Could not find new list {}", &new_list_name))?;
                new_list.notes_mut().push(note);
                Ok(())
            }
        }
    }
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
    info!("Setting up project mapper",);
    const PROJECT_NAME: &str = "openxr/openxr";
    let mut mapper = ProjectMapper::new(&gitlab, PROJECT_NAME)?;

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

    const APPROVED_BACKLOG: &str = "Contractor Approved Backlog";
    const CTS_IMPL: &str = "Conformance Implementation";

    let mut changes = vec![];

    info!("Looking for new data");
    let issue_endpoint = gitlab::api::projects::issues::Issues::builder()
        .project(PROJECT_NAME)
        .label(APPROVED_BACKLOG)
        .state(gitlab::api::issues::IssueState::Opened)
        .build()
        .map_err(|e| anyhow!("Endpoint issue building failed: {}", e))?;
    if let Ok(issue_data_and_ref_vecs) =
        find_issues_and_related_mrs(&gitlab, PROJECT_NAME, issue_endpoint)
    {
        let issue_data_and_ref_vecs = issue_data_and_ref_vecs.map(|(issue_data, v)| {
            let full_vec: Vec<_> = find_mr(issue_data.description())
                .into_iter()
                .chain(v.into_iter())
                .collect();
            (issue_data, full_vec)
        });
        // let list = lists
        //     .named_list_mut("Initial Composition")
        //     .expect("need initial composition list");
        for (issue_data, note) in process_new_issues(&mut collection, issue_data_and_ref_vecs) {
            info!("Adding note for {}", issue_data.title());
            // list.notes_mut().push(GenericNote::new(note));
            changes.push(BoardOperation::AddNote {
                list_name: "TODO".to_owned(),
                note,
            })
        }
    }

    let mr_endpoints: Result<Vec<_>, _> = vec![APPROVED_BACKLOG, CTS_IMPL]
        .into_iter()
        .map(|label| {
            gitlab::api::projects::merge_requests::MergeRequests::builder()
                .project(PROJECT_NAME)
                .label(label)
                .state(gitlab::api::projects::merge_requests::MergeRequestState::Opened)
                .build()
                .map_err(|e| anyhow!("Endpoint issue building failed: {}", e))
        })
        .collect();

    let mut cache: GitlabQueryCache = Default::default();

    info!("Proposed changes:\n{:#?}", changes);
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
                            .trim_start_matches("Release Checklist for ")
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
