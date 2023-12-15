// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Rylie Pavlik <rylie.pavlik@collabora.com>

use std::fmt::Display;

/// ID type for `WorkUnit` structures belonging to a `WorkUnitContainer`
#[derive(Debug, Clone, Copy, Hash, PartialEq, Eq, PartialOrd, Ord)]
pub struct UnitId(usize);

impl From<usize> for UnitId {
    fn from(value: usize) -> Self {
        UnitId(value)
    }
}

impl From<UnitId> for usize {
    fn from(value: UnitId) -> Self {
        value.0
    }
}

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

    pub fn from_iterator(iter: impl Iterator<Item = R>) -> Self {
        let refs: Vec<R> = iter.collect();
        Self {
            refs,
            extincted_by: None,
        }
    }

    /// Iterate through the project item references
    pub fn iter_refs(&self) -> impl Iterator<Item = &R> {
        self.refs.iter()
    }

    /// Adds ref to the list. Does not check to see if they is already in there: that is the job of the collection.
    pub(crate) fn extend_refs(&mut self, iter: impl Iterator<Item = R>) {
        self.refs.extend(iter)
    }

    /// Mark this work unit as extinct by pointing to a different work unit, and take the refs.
    /// For use in merging work units.
    pub(crate) fn extinct_by(&mut self, unit_id: UnitId) -> Vec<R> {
        self.extincted_by = Some(unit_id);
        std::mem::take(&mut self.refs)
    }

    pub fn extincted_by(&self) -> Option<UnitId> {
        self.extincted_by
    }

    pub fn is_extinct(&self) -> bool {
        self.extincted_by.is_some()
    }
}
