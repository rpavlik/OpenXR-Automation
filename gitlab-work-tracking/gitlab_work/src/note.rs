// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::borrow::Cow;

use crate::refs::{find_refs, ProjectItemReference};
use itertools::Itertools;
use log::warn;

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

impl<'a> From<ProjectItemReference> for LineOrReference<'a> {
    fn from(v: ProjectItemReference) -> Self {
        Self::Reference(v)
    }
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
