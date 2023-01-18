// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::iter::once;

use anyhow::anyhow;
use gitlab::{
    api::{common::NameOrId, endpoint_prelude::Method, Endpoint, Query},
    MergeRequestInternalId,
};
use gitlab_work_units::{
    regex::{PROJECT_NAME_PATTERN, REFERENCE_IID_PATTERN},
    MergeRequest, ProjectItemReference, ProjectReference, WorkUnitCollection,
};
use lazy_static::lazy_static;
use log::debug;
use regex::Regex;
use work_unit_collection::{AsCreated, InsertOutcomeGetter};
use workboard_update::{
    find_more::{find_related_mrs, IssueData},
    line_or_reference::{LineOrReference, LineOrReferenceCollection, ProcessedNote},
};

pub fn find_mr(description: &str) -> Option<MergeRequest> {
    lazy_static! {
        static ref RE: Regex = Regex::new(
            format!(
                r"(?x)
                Main extension MR:\s*
                {}?
                !
                {}
            ",
                PROJECT_NAME_PATTERN, REFERENCE_IID_PATTERN
            )
            .as_str()
        )
        .expect("valid regex");
    }
    RE.captures_iter(description).find_map(|cap| {
        // this should always be found and parse right
        let iid = cap.name("iid")?;
        let iid = iid.as_str().parse().ok()?;

        // this might not be specified
        let project = cap
            .name("proj")
            .map(|p| ProjectReference::ProjectName(p.as_str().to_owned()))
            .unwrap_or_default();

        Some(MergeRequest::new(project, MergeRequestInternalId::new(iid)))
    })
}

/// Temporary impl to get related merge requests until https://gitlab.kitware.com/utils/rust-gitlab/-/merge_requests/373
/// is merged and released
struct RelatedMergeRequests<'a> {
    project: NameOrId<'a>,
    issue: u64,
}
impl Endpoint for RelatedMergeRequests<'_> {
    fn method(&self) -> gitlab::api::endpoint_prelude::Method {
        Method::GET
    }

    fn endpoint(&self) -> std::borrow::Cow<'static, str> {
        format!(
            "projects/{}/issues/{}/related_merge_requests",
            self.project, self.issue
        )
        .into()
    }
}

fn lookup_from_checklist(
    client: &gitlab::Gitlab,
    project_name: &str,
    issue: &IssueData,
) -> Vec<ProjectItemReference> {
    let current_issue: gitlab_work_units::Issue = issue.into();
    let current_ref = ProjectItemReference::from(issue);

    let mr = find_mr(issue.description());
    let mrs = mr.into_iter().chain(
        find_related_mrs(client, project_name, &current_issue)
            .into_iter()
            .flat_map(|v| v.into_iter().map(gitlab_work_units::MergeRequest::from)),
    );

    let ret: Vec<ProjectItemReference> = once(current_ref.clone())
        .chain(mrs.map(ProjectItemReference::from))
        .collect();

    ret
}

pub fn find_new_checklists<'a>(
    client: &'a gitlab::Gitlab,
    project_name: &'a str,
) -> Result<impl 'a + Iterator<Item = (IssueData, Vec<ProjectItemReference>)>, anyhow::Error> {
    let opened_endpoint = gitlab::api::projects::issues::Issues::builder()
        .project(project_name)
        .label("Release Checklist")
        .state(gitlab::api::issues::IssueState::Opened)
        .build()
        .map_err(|e| anyhow!("Endpoint issue building failed: {}", e))?;

    let vec: Vec<IssueData> = gitlab::api::paged(opened_endpoint, gitlab::api::Pagination::All)
        .query(client)
        .map_err(|e| anyhow!("Query for opened issues failed: {}", e))?;

    Ok(vec.into_iter().map(|issue| {
        let references = lookup_from_checklist(client, project_name, &issue);
        (issue, references)
    }))
}

pub fn find_new_notes<'a>(
    collection: &'a mut WorkUnitCollection,
    iter: impl 'a + Iterator<Item = (IssueData, Vec<ProjectItemReference>)>,
) -> impl 'a + Iterator<Item = (IssueData, ProcessedNote)> {
    // For each...
    iter.filter_map(|(issue_data, refs)| {
        // Try adding all the refs as a group.
        let created_unit_id = collection
            .get_or_insert_from_iterator(refs.iter().cloned())
            .ok() // disregard errors
            .as_ref()
            .and_then(|o| {
                // show the results
                debug!(
                    "Results of loading checklist {} ({}): {:?}",
                    ProjectItemReference::from(&issue_data),
                    issue_data.title(),
                    &o
                );
                // only keep ones where a new unit was created
                o.as_created()
            })
            .map(|o| o.work_unit_id());

        // Split into two steps since the previous chain borrows refs
        // Pass along issue_data, unit ID, and refs to next step
        created_unit_id.map(|unit_id| (issue_data, unit_id, refs))
    })
    .map(|(issue_data, unit_id, refs)| {
        (
            issue_data,
            // convert unit ID and refs to a ProcessedNote
            ProcessedNote::new(
                Some(unit_id),
                LineOrReferenceCollection(refs.into_iter().map(LineOrReference::from).collect()),
            ),
        )
    })
}
