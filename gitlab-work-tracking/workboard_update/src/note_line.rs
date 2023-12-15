// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Rylie Pavlik <rylie.pavlik@collabora.com>

use gitlab_work_units::{find_refs, ProjectItemReference};
use itertools::Itertools;
use log::warn;

use crate::UNICODE_BULLET_AND_SPACE;

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
        let mut refs = find_refs(s).peekable();
        let first_ref = refs.next();
        if first_ref.is_some() && refs.peek().is_some() {
            warn!("Found extra refs in a single line: {}", refs.format(", "));
        }
        Self {
            line: s
                .trim_start_matches(UNICODE_BULLET_AND_SPACE)
                .trim()
                .to_owned(),
            reference: first_ref,
        }
    }
}
