// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::fmt::Display;

/// ID type for `WorkUnit` structures belonging to a `WorkUnitContainer`
#[derive(Debug, Clone, Copy, Hash, PartialEq, Eq, PartialOrd, Ord)]
pub struct UnitId(usize);

impl Display for UnitId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Unit({})", self.0)
    }
}

/// A single logical task encompassing one or more project item references (issue or MR) in an ordered list.
#[derive(Debug)]
pub struct WorkUnit<R> {
    refs: Vec<R>,
    extincted_by: Option<UnitId>,
}

impl<R> WorkUnit<R> {
    /// Create a new WorkUnit
    pub fn new(reference: R) -> Self {
        Self {
            refs: vec![reference],
            extincted_by: None,
        }
    }

    /// Iterate through the project item references
    pub fn iter_refs(&self) -> impl Iterator<Item = &R> {
        self.refs.iter()
    }

    /// Add a ref to the list. Does not check to see if it is already in there: that is the job of the collection.
    pub(crate) fn add_ref(&mut self, reference: R) {
        self.refs.push(reference)
    }

    /// Mark this work unit as extinct by pointing to a different work unit, and take the refs.
    /// For use in merging work units.
    pub(crate) fn extinct_by(&mut self, unit_id: UnitId) -> Vec<R> {
        self.extincted_by = Some(unit_id);
        std::mem::take(&mut self.refs)
    }
}
