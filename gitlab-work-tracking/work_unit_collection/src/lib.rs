// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

mod collection;
pub mod error;
mod insert_outcome;
mod traits;
mod work_unit;

pub use collection::WorkUnitCollection;
pub use traits::{InsertOutcomeGetter, WorkUnitIdGetter};
pub use work_unit::{UnitId, WorkUnit};
