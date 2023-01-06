// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::borrow::Cow;

use crate::gitlab_refs::{Issue, MergeRequest, ProjectItemReference, ProjectReference};
use gitlab::{IssueInternalId, MergeRequestInternalId};
use itertools::Itertools;
use lazy_static::lazy_static;
use log::{error, warn};
use regex::Regex;

fn find_refs(input: &str) -> impl Iterator<Item = ProjectItemReference> + '_ {
    lazy_static! {
        static ref RE: Regex = Regex::new(
            r"(?x)
                (?P<proj>[-._a-zA-Z0-9]+[-./_a-zA-Z0-9]+)?
                (?P<symbol>[\#!])
                (?P<iid>[1-9][0-9]+)
            "
        )
        .expect("valid regex");
    }
    RE.captures_iter(input).filter_map(|cap| {
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
}

/// Association of an optional project item reference with a line in a note/card
#[derive(Debug, Clone)]
pub struct NoteLine<'a> {
    /// The full original line of text
    pub line: Cow<'a, str>,
    /// At most one project item reference parsed out of the line
    pub reference: Option<ProjectItemReference>,
}

impl<'a> NoteLine<'a> {
    /// Parse a single line of text into a NoteLine instance
    pub fn parse_line(s: Cow<'a, str>) -> Self {
        let first_ref = {
            let mut refs = find_refs(&s).peekable();
            let first_ref = refs.next();
            if first_ref.is_some() && refs.peek().is_some() {
                warn!("Found extra refs in a single line: {}", refs.format(", "));
            }
            first_ref
        };
        Self {
            line: s,
            reference: first_ref,
        }
    }
}

/// A simplified more structured representation of a line in a note (compared to `NoteLine`),
/// as either a non-reference freeform text line, or as a single project item reference.
#[derive(Debug, Clone)]
pub enum LineOrReference<'a> {
    /// A line of freeform text with no project item reference
    Line(Cow<'a, str>),
    /// A project item reference found in a line
    Reference(ProjectItemReference),
}

impl LineOrReference<'_> {
    /// Get the stored reference, or None
    pub fn into_reference(self) -> Option<ProjectItemReference> {
        match self {
            LineOrReference::Reference(reference) => Some(reference),
            _ => None,
        }
    }

    /// Get the stored reference, or None
    pub fn as_reference(&self) -> Option<&ProjectItemReference> {
        match self {
            LineOrReference::Reference(reference) => Some(reference),
            _ => None,
        }
    }

    /// Clone and transform the stored reference, if any
    pub fn map_reference_or_clone(
        &self,
        mut f: impl FnMut(&ProjectItemReference) -> ProjectItemReference,
    ) -> Self {
        if let LineOrReference::Reference(reference) = self {
            let mapped = f(reference);
            return LineOrReference::Reference(mapped);
        }
        self.clone()
    }

    /// Transform the stored reference, if any
    pub fn map_reference(
        self,
        mut f: impl FnMut(ProjectItemReference) -> ProjectItemReference,
    ) -> Self {
        match self {
            LineOrReference::Reference(reference) => {
                let mapped = f(reference);
                LineOrReference::Reference(mapped)
            }
            LineOrReference::Line(line) => LineOrReference::Line(line),
        }
    }

    /// Clone and try to transform the stored reference, if any
    pub fn try_map_reference_or_clone<E: std::error::Error>(
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

impl<'a> LineOrReference<'a> {
    /// Parse a single line of text into a LineOrReference instance
    pub fn parse_line(s: &'a str) -> Self {
        NoteLine::parse_line(Cow::Borrowed(s)).into()
    }

    /// Parse a single line of text into a LineOrReference instance
    pub fn parse_owned_line(s: String) -> Self {
        NoteLine::parse_line(Cow::Owned(s)).into()
    }

    /// Turn this enum into a string, calling the provided function if it is an item reference
    pub fn format_to_string(
        self,
        f: impl FnOnce(ProjectItemReference) -> Cow<'a, str>,
    ) -> Cow<'a, str> {
        match self {
            LineOrReference::Line(text) => text,
            LineOrReference::Reference(reference) => f(reference),
        }
    }
}

impl<'b, 'a: 'b> From<NoteLine<'a>> for LineOrReference<'b> {
    fn from(line: NoteLine<'a>) -> Self {
        match line.reference {
            Some(reference) => LineOrReference::Reference(reference),
            None => LineOrReference::Line(line.line),
        }
    }
}
