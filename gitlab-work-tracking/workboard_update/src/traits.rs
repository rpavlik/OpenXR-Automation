// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab_work_units::ProjectItemReference;
use work_unit_collection::UnitId;

/// Uniform access to things that have an Option<UnitId> in them
pub trait GetWorkUnit {
    /// Access the work unit ID, if any
    fn work_unit_id(&self) -> &Option<UnitId>;

    /// Mutably borrow the optional work unit ID
    fn work_unit_id_mut(&mut self) -> &mut Option<UnitId>;

    /// Does this struct have an associated work unit?
    fn has_work_unit_id(&self) -> bool;
}

/// Uniform access to things that may have a GitLabItemReference in them
pub trait GetItemReference {
    fn project_item_reference(&self) -> Option<&ProjectItemReference>;
    fn set_project_item_reference(&mut self, reference: ProjectItemReference);

    /// Clone and try to transform the stored reference, if any
    fn try_map_reference_or_clone<E: std::error::Error>(
        &self,
        f: impl FnMut(&ProjectItemReference) -> Result<ProjectItemReference, E>,
    ) -> Result<Self, E>
    where
        Self: Sized;
}

pub trait ParsedLineLike: GetItemReference + From<String> {
    // fn from_string<S: Into<String>>(s: S) -> Self;

    fn line(&self) -> Option<&str>;
}
