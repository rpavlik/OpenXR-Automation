// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::UnitId;

pub trait WorkUnitIdGetter {
    /// Access a work unit ID
    fn work_unit_id(&self) -> UnitId;
}

/// Access fields that may exist to describe the result of looking up and/or inserting a work unit for some refs.
pub trait InsertOutcomeGetter {
    /// Consume the structure and return only the contained UnitId.
    fn into_work_unit_id(self) -> UnitId;

    /// Access the work unit ID: always present
    fn work_unit_id(&self) -> UnitId;

    /// How many refs were added to the mentioned work unit?
    fn refs_added(&self) -> usize {
        0
    }
    /// How many other work units were merged into this one as a result of associating these refs together?
    fn units_merged(&self) -> usize {
        0
    }
}
