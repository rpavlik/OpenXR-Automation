// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use anyhow::Error;
use gitlab_work::{
    note::LineOrReference, BaseGitLabItemReference, GitLabItemReferenceNormalize,
    ProjectItemReference, ProjectMapper, UnitId, WorkUnitCollection,
};
use itertools::Itertools;
use log::warn;
use nullboard_tools::{GenericList, GenericNote};
use std::collections::{hash_map::Entry, HashMap};

use crate::map::map_note_data_in_lists;

#[derive(Debug)]
pub struct Lines(pub Vec<LineOrReference>);

#[derive(Debug)]
pub struct ProcessedNote {
    unit_id: Option<UnitId>,
    lines: Lines,
    deleted: bool,
}

impl From<ProcessedNote> for Lines {
    fn from(note: ProcessedNote) -> Self {
        note.lines
    }
}

fn map_line_or_reference_to_id(
    mapper: &mut ProjectMapper,
) -> impl FnMut(&LineOrReference) -> Result<LineOrReference, Error> + '_ {
    move |line_or_ref| {
        if let LineOrReference::Reference(reference) = line_or_ref {
            let project = reference.get_project();
            let id = mapper.try_map_project_to_id(project)?;
            return Ok(LineOrReference::Reference(reference.with_project_id(id)));
        }
        Ok(line_or_ref.clone())
    }
}

fn map_reference_to_id(
    mapper: &mut ProjectMapper,
) -> impl FnMut(&ProjectItemReference) -> Result<ProjectItemReference, gitlab_work::Error> + '_ {
    move |reference| reference.try_with_normalized_project_reference(mapper)
}

fn map_line_or_reference_to_id2(
    mapper: &mut ProjectMapper,
) -> impl FnMut(&LineOrReference) -> Result<LineOrReference, Error> + '_ {
    let mut f = map_reference_to_id(mapper);
    move |line_or_ref| Ok(line_or_ref.try_map_reference(&mut f)?)
}

// fn map_line_or_reference_to_formatted(
//     mapper: &ProjectMapper,
// ) -> impl FnMut(&LineOrReference) -> LineOrReference + '_ {
//     let mut f = |item_reference: &ProjectItemReference| {
//         item_reference.with_formatted_project_reference(mapper)
//     };
//     move |line_or_ref| line_or_ref.map_reference(&mut f)
// }

impl Lines {
    // pub fn iter(&self) -> _ {
    //     self.0.iter()
    // }

    pub fn map_projects_to_id(&self, mapper: &mut ProjectMapper) -> Result<Lines, Error> {
        let x: Vec<LineOrReference> = self
            .0
            .iter()
            .map(map_line_or_reference_to_id(mapper))
            .collect::<Result<Vec<LineOrReference>, Error>>()?;
        Ok(Lines(x))
    }

    // pub fn map_projects_to_formatted_name(&self, mapper: &ProjectMapper) -> Lines {
    //     let x: Vec<LineOrReference> = self
    //         .0
    //         .iter()
    //         .map(map_line_or_reference_to_formatted(mapper))
    //         .collect();
    //     Lines(x)
    // }
}

pub fn parse_note(s: &str) -> Lines {
    Lines(s.split('\n').map(LineOrReference::parse_line).collect())
}

pub fn process_note_and_associate_work_unit(
    collection: &mut WorkUnitCollection,
    lines: Lines,
) -> ProcessedNote {
    let refs: Vec<ProjectItemReference> = lines
        .0
        .iter()
        .filter_map(LineOrReference::reference)
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

pub fn process_lists_and_associate_work_units<'a>(
    collection: &'a mut WorkUnitCollection,
    lists: impl IntoIterator<Item = GenericList<Lines>> + 'a,
) -> impl Iterator<Item = GenericList<ProcessedNote>> + 'a {
    lists.into_iter().map(move |list| {
        list.map_notes(|text| process_note_and_associate_work_unit(collection, text))
    })
}

pub fn parse_and_process_note(collection: &mut WorkUnitCollection, s: &str) -> ProcessedNote {
    let lines = parse_note(s);
    process_note_and_associate_work_unit(collection, lines)
}

fn normalize_line_or_reference(
    mapper: &mut ProjectMapper,
    line: LineOrReference,
) -> LineOrReference {
    match line
        .try_map_reference(|reference| reference.try_with_normalized_project_reference(mapper))
    {
        Ok(mapped) => mapped,
        Err(_) => LineOrReference::Line(format!(
            "Failed trying to normalize reference {}",
            line.reference().unwrap()
        )),
    }
}

fn note_project_refs_to_ids(mapper: &mut ProjectMapper, lines: Lines) -> Lines {
    let lines = lines
        .0
        .into_iter()
        .map(|line| normalize_line_or_reference(mapper, line))
        .collect();
    Lines(lines)
}

pub fn project_refs_to_ids<'a>(
    mapper: &'a mut ProjectMapper,
    lists: impl IntoIterator<Item = GenericList<Lines>> + 'a,
) -> impl Iterator<Item = GenericList<Lines>> + 'a {
    map_note_data_in_lists(lists, |note_lines| {
        note_project_refs_to_ids(mapper, note_lines)
    })
}

pub mod note_formatter {

    use gitlab::{api, api::Query, ProjectId};
    use gitlab_work::{
        BaseGitLabItemReference, Error, GitLabItemReferenceNormalize, LineOrReference,
        ProjectItemReference, ProjectMapper,
    };
    use itertools::Itertools;
    use log::info;
    use serde::Deserialize;

    use super::Lines;
    #[derive(Debug, Deserialize)]
    struct ProjectIssue {
        state: gitlab::IssueState,
        web_url: String,
        title: String,
    }

    #[derive(Debug, Deserialize)]
    struct InternalResults {
        state: String,
        web_url: String,
        title: String,
    }

    #[derive(Debug)]
    struct ItemResults {
        state_annotation: Option<&'static str>,
        web_url: String,
        title: String,
    }

    trait MakeStateAnnotation {
        fn as_state_annotation(self) -> Option<&'static str>;
    }

    impl MakeStateAnnotation for String {
        fn as_state_annotation(self) -> Option<&'static str> {
            match self.as_str() {
                "closed" => Some("[CLOSED] "),
                "merged" => Some("[MERGED] "),
                "locked" => Some("[LOCKED] "),
                _ => None,
            }
        }
    }

    impl From<InternalResults> for ItemResults {
        fn from(f: InternalResults) -> Self {
            Self {
                state_annotation: f.state.as_state_annotation(),
                web_url: f.web_url,
                title: f.title,
            }
        }
    }

    fn query_gitlab(
        proj_id: ProjectId,
        reference: &ProjectItemReference,
        client: &gitlab::Gitlab,
    ) -> Result<ItemResults, Error> {
        let query_result: Result<InternalResults, _> = match reference {
            ProjectItemReference::Issue(issue) => {
                let endpoint = gitlab::api::projects::issues::Issue::builder()
                    .project(proj_id.value())
                    .issue(issue.get_raw_iid())
                    .build()?;
                endpoint.query(client)
            }
            ProjectItemReference::MergeRequest(mr) => {
                let endpoint = gitlab::api::projects::merge_requests::MergeRequest::builder()
                    .project(proj_id.value())
                    .merge_request(mr.get_raw_iid())
                    .build()?;
                endpoint.query(client)
            }
        };
        let query_result =
            query_result.map_err(|e| Error::ItemQueryError(reference.to_string(), e))?;
        Ok(query_result.into())
    }

    pub fn format_reference(
        reference: &ProjectItemReference,
        mapper: &ProjectMapper,
        title_mangler: impl Fn(&str) -> &str,
    ) -> String {
        match reference.get_project().project_id() {
            Some(proj_id) => match query_gitlab(proj_id, reference, mapper.gitlab_client()) {
                Ok(info) => {
                    format!(
                        "[{}]({}) {}{}",
                        reference.clone().with_formatted_project_reference(mapper),
                        info.web_url,
                        info.state_annotation.unwrap_or(""),
                        title_mangler(info.title.as_str())
                    )
                }
                Err(e) => format!("{} (error in query: {})", reference, e),
            },
            None => format!("{} (missing project ID)", reference),
        }
    }

    pub fn format_note(
        lines: Lines,
        mapper: &ProjectMapper,
        title_mangler: impl Fn(&str) -> &str,
    ) -> String {
        lines
            .0
            .into_iter()
            .map(|line| match line {
                LineOrReference::Line(text) => text,
                LineOrReference::Reference(reference) => {
                    format_reference(&reference, mapper, &title_mangler)
                }
            })
            .join("\n\u{2022} ")
    }
}

// fn format_notes<'a>(
//     mapper: &'a ProjectMapper,
//     lists: impl IntoIterator<Item = GenericList<Lines>> + 'a,
// )-> impl Iterator<Item = GenericList<String>> + 'a {
//     map_note_data_in_lists(lists, |lines| lines.0.into_iter().map(|line| match line {
//         LineOrReference::Line(text) => text,
//         LineOrReference::Reference(reference) => format!("{}" reference.with_formatted_project_reference(mapper),
//     }))
// }
const RECURSE_LIMIT: usize = 5;

// fn filter_note(
//     collection: &'a mut WorkUnitCollection, )

// pub fn map_note_data_in_lists<'a, T, B, F: 'a + FnMut(T) -> B>(
//     lists: impl IntoIterator<Item = GenericList<T>> + 'a,
//     f: F,
// ) -> impl Iterator<Item = GenericList<B>> + 'a {
//     let mut map_list = move |list: GenericList<T>| -> GenericList<B> { list.map_notes(f) };

//     lists.into_iter().map(&map_list)
// }

pub fn prune_notes<'a>(
    collection: &'a mut WorkUnitCollection,
    lists: impl IntoIterator<Item = GenericList<ProcessedNote>> + 'a,
) -> Vec<GenericList<ProcessedNote>> {
    // Mark those notes which should be skipped because they refer to a work unit that already has a card.
    let mut units_handled: HashMap<UnitId, ()> = Default::default();
    let mut filter_note = |note: &GenericNote<ProcessedNote>| {
        if let Some(id) = &note.text.unit_id {
            match collection.get_unit_id_following_extinction(*id, RECURSE_LIMIT) {
                Ok(id) => match units_handled.entry(id) {
                    Entry::Occupied(_) => {
                        // note.text.deleted = true;
                        warn!(
                            "Deleting note because its work unit was already handled: {} {:?}",
                            id, note.text.lines
                        );
                        false
                    }
                    Entry::Vacant(e) => {
                        e.insert(());
                        true
                    }
                },
                Err(e) => {
                    warn!("Got error trying to resolve ref, will keep: {}", e);
                    true
                }
            }
        } else {
            true
        }
    };

    lists
        .into_iter()
        .map(move |list| -> GenericList<ProcessedNote> {
            GenericList {
                title: list.title,
                notes: list.notes.into_iter().filter(&mut filter_note).collect(),
            }
        })
        .collect()
}

pub fn mark_notes_for_deletion(
    lists: &mut Vec<GenericList<ProcessedNote>>,
    collection: &WorkUnitCollection,
) -> Result<(), Error> {
    // Mark those notes which should be skipped because they refer to a work unit that already has a card.
    let mut units_handled: HashMap<UnitId, ()> = Default::default();
    for list in lists.iter_mut() {
        for note in &mut list.notes {
            if let Some(id) = &note.text.unit_id {
                let id = collection.get_unit_id_following_extinction(*id, RECURSE_LIMIT)?;
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
    Ok(())
}
