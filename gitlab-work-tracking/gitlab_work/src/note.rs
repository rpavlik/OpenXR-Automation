// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::gitlab_refs::{Issue, MergeRequest, ProjectItemReference, ProjectReference};
use gitlab::{IssueInternalId, MergeRequestInternalId};
use itertools::Itertools;
use lazy_static::lazy_static;
use log::{error, warn};
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

/// Association of an optional project item reference with a line in a note/card
#[derive(Debug, Clone)]
pub struct NoteLine {
    /// The full original line of text
    pub line: String,
    /// At most one project item reference parsed out of the line
    pub reference: Option<ProjectItemReference>,
}

impl NoteLine {
    /// Parse a single line of text into a NoteLine instance
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
            warn!(
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

/// A simplified more structured representation of a line in a note (compared to `NoteLine`),
/// as either a non-reference freeform text line, or as a single project item reference.
#[derive(Debug, Clone)]
pub enum LineOrReference {
    /// A line of freeform text with no project item reference
    Line(String),
    /// A project item reference found in a line
    Reference(ProjectItemReference),
}

impl LineOrReference {
    /// Parse a single line of text into a LineOrReference instance
    pub fn parse_line(s: &str) -> Self {
        NoteLine::parse_line(s).into()
    }

    pub fn reference(&self) -> Option<&ProjectItemReference> {
        if let LineOrReference::Reference(reference) = self {
            Some(reference)
        } else {
            None
        }
    }

    pub fn map_reference(
        &self,
        mut f: impl FnMut(&ProjectItemReference) -> ProjectItemReference,
    ) -> Self {
        if let LineOrReference::Reference(reference) = self {
            let mapped = f(reference);
            return LineOrReference::Reference(mapped);
        }
        self.clone()
    }

    pub fn try_map_reference<E: std::error::Error>(
        &self,
        mut f: impl FnMut(&ProjectItemReference) -> Result<ProjectItemReference, E>,
    ) -> Result<Self, E> {
        if let LineOrReference::Reference(reference) = self {
            let mapped = f(reference)?;
            return Ok(LineOrReference::Reference(mapped));
        }
        Ok(self.clone())
    }
}

impl From<NoteLine> for LineOrReference {
    fn from(line: NoteLine) -> Self {
        match line.reference {
            Some(reference) => LineOrReference::Reference(reference),
            None => LineOrReference::Line(line.line),
        }
    }
}
