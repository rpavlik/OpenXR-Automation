// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab::MergeRequestInternalId;
use gitlab_work_units::{
    regex::{PROJECT_NAME_PATTERN, REFERENCE_IID_PATTERN},
    MergeRequest, ProjectItemReference, ProjectReference, WorkUnitCollection,
};
use lazy_static::lazy_static;
use log::debug;
use regex::Regex;
use work_unit_collection::{AsCreated, InsertOutcomeGetter};
use workboard_update::{
    find_more::IssueData,
    line_or_reference::{LineOrReference, LineOrReferenceCollection, ProcessedNote},
};

pub fn find_mr(description: &str) -> Option<ProjectItemReference> {
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

        Some(MergeRequest::new(project, MergeRequestInternalId::new(iid)).into())
    })
}

pub fn process_new_issues<'a>(
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
                    "Results of loading GitLab {} ({}): {:?}",
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
