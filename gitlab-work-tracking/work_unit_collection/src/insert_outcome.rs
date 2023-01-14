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

impl InsertOutcomeGetter for UnitCreated {
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
pub struct UnitUnchanged {
    pub unit_id: UnitId,
}

impl InsertOutcomeGetter for UnitUnchanged {
    fn into_work_unit_id(self) -> UnitId {
        self.unit_id
    }
    fn work_unit_id(&self) -> UnitId {
        self.unit_id
    }
}

/// The outcome of getting or inserting a group of one or more references
/// into a [`WorkUnitCollection`].
///
/// [`WorkUnitCollection`]: crate::collection::WorkUnitCollection
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum InsertRefGroupOutcome {
    Created(UnitCreated),
    Updated(UnitUpdated),
    Unchanged(UnitUnchanged),
}

impl From<UnitUnchanged> for InsertRefGroupOutcome {
    fn from(v: UnitUnchanged) -> Self {
        Self::Unchanged(v)
    }
}

impl From<UnitUpdated> for InsertRefGroupOutcome {
    fn from(v: UnitUpdated) -> Self {
        Self::Updated(v)
    }
}

impl From<UnitCreated> for InsertRefGroupOutcome {
    fn from(v: UnitCreated) -> Self {
        Self::Created(v)
    }
}

impl InsertOutcomeGetter for InsertRefGroupOutcome {
    #[must_use]
    fn into_work_unit_id(self) -> UnitId {
        match self {
            InsertRefGroupOutcome::Created(o) => o.into_work_unit_id(),
            InsertRefGroupOutcome::Updated(o) => o.into_work_unit_id(),
            InsertRefGroupOutcome::Unchanged(o) => o.into_work_unit_id(),
        }
    }

    #[must_use]
    fn work_unit_id(&self) -> UnitId {
        match self {
            InsertRefGroupOutcome::Created(o) => o.work_unit_id(),
            InsertRefGroupOutcome::Updated(o) => o.work_unit_id(),
            InsertRefGroupOutcome::Unchanged(o) => o.work_unit_id(),
        }
    }

    #[must_use]
    fn refs_added(&self) -> usize {
        match self {
            InsertRefGroupOutcome::Created(o) => o.refs_added(),
            InsertRefGroupOutcome::Updated(o) => o.refs_added(),
            InsertRefGroupOutcome::Unchanged(o) => o.refs_added(),
        }
    }

    #[must_use]
    fn units_merged(&self) -> usize {
        match self {
            InsertRefGroupOutcome::Created(o) => o.units_merged(),
            InsertRefGroupOutcome::Updated(o) => o.units_merged(),
            InsertRefGroupOutcome::Unchanged(o) => o.units_merged(),
        }
    }
}

impl InsertRefGroupOutcome {
    /// Returns `true` if the insert outcome is [`Updated`].
    ///
    /// [`Updated`]: InsertRefsOutcome::Updated
    #[must_use]
    pub fn is_updated(&self) -> bool {
        matches!(self, Self::Updated(..))
    }
}

/// The outcome of getting or inserting a single reference into a [`WorkUnitCollection`]
///
/// [`WorkUnitCollection`]: crate::collection::WorkUnitCollection
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum InsertRefOutcome {
    Created(UnitCreated),
    Unchanged(UnitUnchanged),
}

impl InsertOutcomeGetter for InsertRefOutcome {
    #[must_use]
    fn into_work_unit_id(self) -> UnitId {
        match self {
            InsertRefOutcome::Created(o) => o.into_work_unit_id(),
            InsertRefOutcome::Unchanged(o) => o.into_work_unit_id(),
        }
    }

    #[must_use]
    fn work_unit_id(&self) -> UnitId {
        match self {
            InsertRefOutcome::Created(o) => o.work_unit_id(),
            InsertRefOutcome::Unchanged(o) => o.work_unit_id(),
        }
    }

    #[must_use]
    fn refs_added(&self) -> usize {
        match self {
            InsertRefOutcome::Created(o) => o.refs_added(),
            InsertRefOutcome::Unchanged(o) => o.refs_added(),
        }
    }
}

impl From<UnitUnchanged> for InsertRefOutcome {
    fn from(v: UnitUnchanged) -> Self {
        Self::Unchanged(v)
    }
}

impl From<UnitCreated> for InsertRefOutcome {
    fn from(v: UnitCreated) -> Self {
        Self::Created(v)
    }
}
impl From<InsertRefOutcome> for InsertRefGroupOutcome {
    fn from(value: InsertRefOutcome) -> Self {
        match value {
            InsertRefOutcome::Created(o) => o.into(),
            InsertRefOutcome::Unchanged(o) => o.into(),
        }
    }
}

pub trait IsUnchanged {
    /// Returns `true` if the insert outcome is [`Unchanged`].
    ///
    /// [`Unchanged`]: UnitUnchanged
    #[must_use]
    fn is_unchanged(&self) -> bool;
}

impl IsUnchanged for InsertRefOutcome {
    fn is_unchanged(&self) -> bool {
        matches!(self, Self::Unchanged(..))
    }
}

impl IsUnchanged for InsertRefGroupOutcome {
    fn is_unchanged(&self) -> bool {
        matches!(self, Self::Unchanged(..))
    }
}

pub trait AsCreated: Sized {
    /// Returns `true` if the insert outcome is [`Created`].
    ///
    /// [`Created`]: UnitCreated
    #[must_use]
    fn is_created(&self) -> bool;

    /// Returns the [`UnitCreated`] if the insert outcome is `Created`,
    /// otherwise returns itself as an error.
    ///
    /// [`UnitCreated`]: UnitCreated
    fn try_into_created(self) -> Result<UnitCreated, Self>;

    /// Returns the [`UnitCreated`] if the insert outcome is `Created`,
    /// otherwise None.
    ///
    /// [`UnitCreated`]: UnitCreated
    fn as_created(&self) -> Option<&UnitCreated>;
}

impl AsCreated for InsertRefOutcome {
    fn try_into_created(self) -> Result<UnitCreated, Self> {
        if let Self::Created(v) = self {
            Ok(v)
        } else {
            Err(self)
        }
    }
    fn is_created(&self) -> bool {
        matches!(self, Self::Created(..))
    }
    fn as_created(&self) -> Option<&UnitCreated> {
        if let Self::Created(v) = self {
            Some(v)
        } else {
            None
        }
    }
}

impl AsCreated for InsertRefGroupOutcome {
    fn try_into_created(self) -> Result<UnitCreated, Self> {
        if let Self::Created(v) = self {
            Ok(v)
        } else {
            Err(self)
        }
    }
    fn is_created(&self) -> bool {
        matches!(self, Self::Created(..))
    }
    fn as_created(&self) -> Option<&UnitCreated> {
        if let Self::Created(v) = self {
            Some(v)
        } else {
            None
        }
    }
}
