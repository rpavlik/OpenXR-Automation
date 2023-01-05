// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab::{api::Query, ProjectId};
use gitlab_work::{
    BaseGitLabItemReference, Error, GitLabItemReferenceNormalize, LineOrReference,
    ProjectItemReference, ProjectMapper,
};
use itertools::Itertools;
use serde::Deserialize;

use crate::Lines;

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

impl From<InternalResults> for ItemResults {
    fn from(f: InternalResults) -> Self {
        Self {
            state_annotation: match f.state.as_str() {
                "closed" => Some("[CLOSED] "),
                "merged" => Some("[MERGED] "),
                "locked" => Some("[LOCKED] "),
                _ => None,
            },
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
    let query_result = query_result.map_err(|e| Error::ItemQueryError(reference.to_string(), e))?;
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
