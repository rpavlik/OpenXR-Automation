// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab::{IssueInternalId, MergeRequestInternalId};
use lazy_static::lazy_static;
use regex::Regex;

use crate::gitlab_refs::{Issue, MergeRequest, ProjectItemReference, ProjectReference};

pub fn try_parse_ref(input: &str) -> Option<ProjectItemReference> {
    lazy_static! {
        static ref RE: Regex = Regex::new(
            r"(?x)
                (?P<proj>[-._a-zA-Z0-9]+[-/._a-zA-Z0-9]+)?
                (?P<symbol>[!#])
                (?P<iid>[1-9][0-9]+)
            "
        )
        .unwrap();
    }
    RE.captures(input).and_then(|cap| {
        // this should always be found and parse right
        let iid = cap.name("iid")?;
        let iid = iid.as_str().parse().ok()?;

        // this might not be specified
        let project = cap
            .name("proj")
            .map(|p| ProjectReference::ProjectName(p.as_str().to_owned()))
            .unwrap_or_default();

        // this should always match one of the known cases
        match cap.name("symbol")?.as_str() {
            "!" => Some(MergeRequest::new(project, MergeRequestInternalId::new(iid)).into()),
            "#" => Some(Issue::new(project, IssueInternalId::new(iid)).into()),
            _ => None, // should never happen
        }
    })
}
