// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::find_more::{find_new_checklists, find_new_notes};
use clap::Parser;
use dotenvy::dotenv;
use env_logger::Env;
use gitlab::ProjectId;
use gitlab_work_units::{
    format_reference,
    lookup::{GitlabQueryCache, ItemState},
    BaseGitLabItemReference, ProjectItemReference, ProjectMapper, ProjectReference, UnitId,
    WorkUnitCollection,
};
use itertools::Itertools;
use log::info;
use nullboard_tools::{
    list::BasicList, Board, GenericList, GenericNote, List, ListCollection, ListIteratorAdapters,
    Note,
};
use pretty::{Doc, RcDoc};
use std::{fmt::Display, iter::once, path::Path};
use workboard_update::{
    associate_work_unit_with_note,
    cli::{GitlabArgs, InputOutputArgs, ProjectArgs},
    line_or_reference::{self, LineOrReference, LineOrReferenceCollection, ProcessedNote},
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

    #[command(flatten, next_help_heading = "Project")]
    project: ProjectArgs,
}

impl Display for BoardOperation {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        todo!()
    }
}
trait FormatWithDefaultProject {
    fn format_with_default_project(
        &self,
        default_project_id: ProjectId,
        f: &mut std::fmt::Formatter<'_>,
    ) -> std::fmt::Result;
}

/// Wrap something to change how it's formatted.
struct WithDefaultProjectKnowledge<'a, T: FormatWithDefaultProject> {
    default_project: ProjectId,
    value: &'a T,
}

impl<'a, T: FormatWithDefaultProject> WithDefaultProjectKnowledge<'a, T> {
    fn new(default_project_id: ProjectId, value: &'a T) -> Self {
        Self {
            default_project: default_project_id,
            value,
        }
    }
}

impl<'a, T: FormatWithDefaultProject> Display for WithDefaultProjectKnowledge<'a, T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.value
            .format_with_default_project(self.default_project, f)
    }
}

impl FormatWithDefaultProject for ProjectReference {
    fn format_with_default_project(
        &self,
        default_project_id: ProjectId,
        f: &mut std::fmt::Formatter<'_>,
    ) -> std::fmt::Result {
        match self {
            ProjectReference::ProjectId(proj_id) => {
                if proj_id == &default_project_id {
                    write!(f, "")
                } else {
                    write!(f, "{}", proj_id)
                }
            }
            ProjectReference::ProjectName(name) => write!(f, "{}", name),
            ProjectReference::UnknownProject => write!(f, ""),
        }
    }
}

impl FormatWithDefaultProject for ProjectItemReference {
    fn format_with_default_project(
        &self,
        default_project_id: ProjectId,
        f: &mut std::fmt::Formatter<'_>,
    ) -> std::fmt::Result {
        write!(
            f,
            "{}{}{}",
            WithDefaultProjectKnowledge::new(default_project_id, self.project()),
            self.symbol(),
            self.raw_iid()
        )
    }
}

impl FormatWithDefaultProject for LineOrReference {
    fn format_with_default_project(
        &self,
        default_project_id: ProjectId,
        f: &mut std::fmt::Formatter<'_>,
    ) -> std::fmt::Result {
        match self {
            LineOrReference::Line(line) => write!(f, "{}", line),
            LineOrReference::Reference(r) => r.format_with_default_project(default_project_id, f),
        }
    }
}

trait PrettyForConsole {
    fn to_console(&self, default_project_id: ProjectId) -> RcDoc<()>;

    fn format_pretty_for_console(&self, default_project_id: ProjectId) -> String {
        let mut w = Vec::new();
        self.to_console(default_project_id)
            .render(80, &mut w)
            .unwrap();
        String::from_utf8(w).unwrap()
    }
}

impl PrettyForConsole for ProjectItemReference {
    fn to_console(&self, default_project_id: ProjectId) -> RcDoc<()> {
        RcDoc::text(format!(
            "{}",
            WithDefaultProjectKnowledge::new(default_project_id, self)
        ))
    }
}
impl PrettyForConsole for LineOrReference {
    fn to_console(&self, default_project_id: ProjectId) -> RcDoc<()> {
        match self {
            LineOrReference::Line(line) => RcDoc::text(line.trim()),
            LineOrReference::Reference(r) => r.to_console(default_project_id),
        }
    }
}

impl PrettyForConsole for ProcessedNote {
    fn to_console(&self, default_project_id: ProjectId) -> RcDoc<()> {
        let maybe_unit_id = self
            .work_unit_id()
            .map(|id| RcDoc::text(format!("{:?}", id)))
            .into_iter();
        let note_lines = self
            .lines()
            .0
            .iter()
            .map(|line_or_ref| line_or_ref.to_console(default_project_id));
        RcDoc::text("ProcessedNote(")
            .append(RcDoc::hardline())
            .append(RcDoc::intersperse(maybe_unit_id.chain(note_lines), Doc::hardline()).nest(2))
            .append(RcDoc::hardline())
            .append(RcDoc::text(")"))
    }
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

impl PrettyForConsole for BoardOperation {
    fn to_console(&self, default_project_id: ProjectId) -> RcDoc<()> {
        match self {
            BoardOperation::NoOp => RcDoc::text("NoOp"),
            BoardOperation::AddNote { list_name, note } => RcDoc::text("AddNote(")
                .append(RcDoc::hardline())
                .append(
                    RcDoc::text(format!("\"{}\"", list_name))
                        .append(RcDoc::text(","))
                        .append(RcDoc::line())
                        .append(note.to_console(default_project_id))
                        .nest(4),
                )
                .append(RcDoc::hardline())
                .append(")"),
            BoardOperation::MoveNote {
                current_list_name,
                new_list_name,
                work_unit_id,
            } => {
                let words = vec![
                    RcDoc::text(current_list_name.as_str()),
                    RcDoc::text("->"),
                    RcDoc::text(new_list_name.as_str()),
                    RcDoc::text("for"),
                    RcDoc::text(format!("{:?}", work_unit_id)),
                ];
                RcDoc::text("MoveNote(")
                    .append(
                        RcDoc::intersperse(words.into_iter(), RcDoc::space())
                            .group()
                            .nest(2),
                    )
                    .append(RcDoc::text(")"))
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
        // let list = lists
        //     .named_list_mut("Initial Composition")
        //     .expect("need initial composition list");
        for (issue_data, note) in find_new_notes(&mut collection, new_checklists) {
            info!("Adding note for {}", issue_data.title());
            // list.notes_mut().push(GenericNote::new(note));
            changes.push(BoardOperation::AddNote {
                list_name: "Initial Composition".to_owned(),
                note,
            })
        }
    }

    let mut cache: GitlabQueryCache = Default::default();

    let default_project_id = mapper.default_project_id();
    {
        let doc = RcDoc::intersperse(
            changes.iter().map(|c| c.to_console(default_project_id)),
            RcDoc::hardline(),
        );

        let mut w = Vec::new();
        doc.render(80, &mut w).unwrap();

        info!("Proposed changes:\n{}", String::from_utf8(w).unwrap());
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
