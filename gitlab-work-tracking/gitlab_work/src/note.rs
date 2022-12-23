// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::gitlab_refs::{Issue, MergeRequest, ProjectItemReference, ProjectReference};
use gitlab::{IssueInternalId, MergeRequestInternalId};
use itertools::Itertools;
use lazy_static::lazy_static;
use log::{error, info};
use regex::Regex;
use std::collections::VecDeque;

fn find_refs(input: &str) -> VecDeque<ProjectItemReference> {
    lazy_static! {
        static ref RE: Regex = Regex::new(
            r"(?x)
                (?P<proj>[-._a-zA-Z0-9]+[-./_a-zA-Z0-9]+)?
                (?P<symbol>[\#!])
                (?P<iid>[1-9][0-9]+)
            "
        )
        .unwrap();
    }
    RE.captures_iter(input)
        .filter_map(|cap| {
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
                _ => {
                    // should never happen
                    error!("Got an unrecognized symbol!");
                    None
                }
            }
        })
        .collect()
}

#[derive(Debug, Clone)]
pub struct NoteLine {
    pub line: String,
    pub reference: Option<ProjectItemReference>,
}

impl NoteLine {
    pub fn parse_line(s: &str) -> Self {
        let mut refs = find_refs(s);
        if refs.is_empty() {
            Self {
                line: s.to_owned(),
                reference: None,
            }
        } else if refs.len() == 1 {
            Self {
                line: s.to_owned(),
                reference: refs.pop_front(),
            }
        } else {
            let front = refs.pop_front();
            info!(
                "Found more than one ref in a single line: {}",
                refs.iter().format(", ")
            );
            Self {
                line: s.to_owned(),
                reference: front,
            }
        }
    }
}
