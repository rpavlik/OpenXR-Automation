// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{InsertOutcomeGetter, UnitId};

/// A brand new work unit was created, with the specified number of unique refs
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct UnitCreated {
    pub unit_id: UnitId,
    pub refs_added: usize,
}

impl InsertOutcomeGetter for UnitNotUpdated {
    fn into_work_unit_id(self) -> UnitId {
        self.unit_id
    }
    fn work_unit_id(&self) -> UnitId {
        self.unit_id
    }
    fn refs_added(&self) -> usize {
        self.refs_added
    }
}

/// Corresponds to an existing unit that got updated, reporting the number of added refs
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct UnitUpdated {
    pub unit_id: UnitId,
    pub refs_added: usize,
    // how many existing work units were merged into the remaining work unit
    pub units_merged_in: usize,
}

impl InsertOutcomeGetter for UnitUpdated {
    fn into_work_unit_id(self) -> UnitId {
        self.unit_id
    }

    fn work_unit_id(&self) -> UnitId {
        self.unit_id
    }

    fn refs_added(&self) -> usize {
        self.refs_added
    }

    fn units_merged(&self) -> usize {
        self.units_merged_in
    }
}

/// Corresponds to an existing unit that did not get updated (no refs were new)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct UnitNotUpdated {
    pub unit_id: UnitId,
}
impl InsertOutcomeGetter for UnitNotUpdated {
    fn into_work_unit_id(self) -> UnitId {
        self.unit_id
    }
    fn work_unit_id(&self) -> UnitId {
        self.unit_id
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum InsertOutcome {
    Created(UnitCreated),
    Updated(UnitUpdated),
    NotUpdated(UnitNotUpdated),
}

impl From<UnitNotUpdated> for InsertOutcome {
    fn from(v: UnitNotUpdated) -> Self {
        Self::NotUpdated(v)
    }
}

impl From<UnitUpdated> for InsertOutcome {
    fn from(v: UnitUpdated) -> Self {
        Self::Updated(v)
    }
}

impl From<UnitCreated> for InsertOutcome {
    fn from(v: UnitCreated) -> Self {
        Self::Created(v)
    }
}

impl InsertOutcomeGetter for InsertOutcome {
    fn into_work_unit_id(self) -> UnitId {
        match self {
            InsertOutcome::Created(o) => o.into_work_unit_id(),
            InsertOutcome::Updated(o) => o.into_work_unit_id(),
            InsertOutcome::NotUpdated(o) => o.into_work_unit_id(),
        }
    }

    fn work_unit_id(&self) -> UnitId {
        match self {
            InsertOutcome::Created(o) => o.work_unit_id(),
            InsertOutcome::Updated(o) => o.work_unit_id(),
            InsertOutcome::NotUpdated(o) => o.work_unit_id(),
        }
    }
    fn refs_added(&self) -> usize {
        match self {
            InsertOutcome::Created(o) => o.refs_added(),
            InsertOutcome::Updated(o) => o.refs_added(),
            InsertOutcome::NotUpdated(o) => o.refs_added(),
        }
    }

    fn units_merged(&self) -> usize {
        match self {
            InsertOutcome::Created(o) => o.units_merged(),
            InsertOutcome::Updated(o) => o.units_merged(),
            InsertOutcome::NotUpdated(o) => o.units_merged(),
        }
    }
}

impl InsertOutcome {
    pub fn try_into_created(self) -> Result<UnitCreated, Self> {
        if let Self::Created(v) = self {
            Ok(v)
        } else {
            Err(self)
        }
    }
}
