// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{
    line_or_reference::LineOrReference, LineOrReferenceCollection, UNICODE_BULLET_AND_SPACE,
};
use gitlab_work_units::{
    lookup::GitlabQueryCache, GitLabItemReferenceNormalize, ProjectItemReference, ProjectMapper,
};
use itertools::Itertools;

pub fn format_reference(
    client: &gitlab::Gitlab,
    cache: &mut GitlabQueryCache,
    reference: &ProjectItemReference,
    mapper: &ProjectMapper,
    title_mangler: impl Fn(&str) -> &str,
) -> String {
    match cache.query(client, reference) {
        Ok(info) => {
            format!(
                "{}[{}]({}) {}{}",
                UNICODE_BULLET_AND_SPACE,
                reference.clone().with_formatted_project_reference(mapper),
                info.web_url(),
                info.state_annotation().unwrap_or_default(),
                title_mangler(info.title())
            )
        }
        Err(e) => format!("{} (error in query: {})", reference, e),
    }
}

pub fn format_note(
    client: &gitlab::Gitlab,
    cache: &mut GitlabQueryCache,
    lines: LineOrReferenceCollection,
    mapper: &ProjectMapper,
    title_mangler: impl Fn(&str) -> &str,
) -> String {
    lines
        .0
        .into_iter()
        .map(|line| match line {
            LineOrReference::Line(text) => text,
            LineOrReference::Reference(reference) => {
                format_reference(client, cache, &reference, mapper, &title_mangler)
            }
        })
        .join("\n")
        .trim_start_matches(UNICODE_BULLET_AND_SPACE) // remove leading bullet from first line
        .to_owned()
}
