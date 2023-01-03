// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{gitlab_refs::ProjectItemReference, Error};
use derive_more::{From, Into};
use log::debug;
use std::{
    collections::{hash_map::Entry, HashMap, HashSet},
    fmt::Display,
};
use typed_index_collections::TiVec;

/// ID type for `WorkUnit` structures belonging to a `WorkUnitContainer`
#[derive(Debug, Clone, Copy, From, Into, Hash, PartialEq, Eq, PartialOrd, Ord)]
pub struct UnitId(usize);

impl Display for UnitId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Unit({})", self.0)
    }
}

#[derive(Debug)]
pub struct WorkUnit {
    refs: Vec<ProjectItemReference>,
    extincted_by: Option<UnitId>,
}

impl WorkUnit {
    pub fn new(reference: ProjectItemReference) -> Self {
        Self {
            refs: vec![reference],
            extincted_by: None,
        }
    }
}

#[derive(Debug, Default)]
struct UnitContainer(TiVec<UnitId, WorkUnit>);

impl UnitContainer {
    /// Get a mutable work unit by ID
    fn get_unit_mut(&mut self, id: UnitId) -> Result<&mut WorkUnit, Error> {
        let unit = self.0.get_mut(id).ok_or(Error::InvalidWorkUnitId(id))?;
        if let Some(extincted_by) = &unit.extincted_by {
            return Err(Error::ExtinctWorkUnitId(id, *extincted_by));
        }
        Ok(unit)
    }

    /// Get a work unit by ID
    fn get_unit(&self, id: UnitId) -> Result<&WorkUnit, Error> {
        let unit = self.0.get(id).ok_or(Error::InvalidWorkUnitId(id))?;
        if let Some(extincted_by) = &unit.extincted_by {
            return Err(Error::ExtinctWorkUnitId(id, *extincted_by));
        }
        Ok(unit)
    }

    /// Create a new work unit from the given reference and return its id
    fn emplace(&mut self, reference: ProjectItemReference) -> UnitId {
        self.0.push_and_get_key(WorkUnit::new(reference))
    }

    /// If the ID is extinct, follow the extincted-by field, repeatedly, at most `limit` steps.
    fn follow_extinction(&self, id: UnitId, limit: usize) -> Result<UnitId, Error> {
        let mut result_id = id;
        for _i in [0..limit] {
            let unit = self.0.get(result_id).ok_or(Error::InvalidWorkUnitId(id))?;
            match &unit.extincted_by {
                Some(successor) => {
                    result_id = *successor;
                }
                None => return Ok(result_id),
            }
        }
        Err(Error::RecursionLimitReached(id))
    }
}

/// A container for "work units" that are ordered collections of GitLab project item references (issues and MRs).
/// Any given item reference can only belong to a single work unit, and each work unit has an ID.
/// To ensure there are not multiple references to a work unit, recommend normalizing the project item reference first.
#[derive(Debug, Default)]
pub struct WorkUnitCollection {
    units: UnitContainer,
    unit_by_ref: HashMap<ProjectItemReference, UnitId>,
}

impl WorkUnitCollection {
    /// Records a work unit containing the provided references (must be non-empty).
    /// If any of those references already exist in the work collection, their corresponding work units are merged.
    /// Any references not yet in the work collection are added.
    pub fn add_or_get_unit_for_refs(
        &mut self,
        refs: impl IntoIterator<Item = ProjectItemReference>,
    ) -> Result<UnitId, Error> {
        let refs: Vec<ProjectItemReference> = refs.into_iter().collect();
        debug!("Given {} refs", refs.len());
        let unit_ids = self.get_ids_for_refs(&refs);
        if let Some((&unit_id, remaining_unit_ids)) = unit_ids.split_first() {
            // we have at least one existing unit
            debug!("Will use work unit {}", unit_id);
            for src_id in remaining_unit_ids {
                debug!("Merging {} into {}", unit_id, src_id);
                self.merge_work_units(unit_id, *src_id)?;
            }
            self.add_refs_to_unit_id(unit_id, &refs[..])?;
            Ok(unit_id)
        } else {
            if let Some((first_ref, rest_of_refs)) = refs.split_first() {
                // we have some refs
                let unit_id = self.units.emplace(first_ref.clone());

                debug!("Created new work unit {}", unit_id);
                self.add_refs_to_unit_id(unit_id, rest_of_refs)?;

                Ok(unit_id)
            } else {
                Err(Error::NoReferences)
            }
        }
    }

    fn add_refs_to_unit_id(
        &mut self,
        unit_id: UnitId,
        refs: &[ProjectItemReference],
    ) -> Result<(), Error> {
        for reference in refs.into_iter() {
            self.add_ref_to_unit_id(unit_id, reference)?;
        }
        Ok(())
    }

    fn add_ref_to_unit_id(
        &mut self,
        id: UnitId,
        reference: &ProjectItemReference,
    ) -> Result<(), Error> {
        debug!("Trying to add a reference to {}: {:?}", id, reference);
        let do_insert = match self.unit_by_ref.entry(reference.clone()) {
            Entry::Occupied(mut entry) => {
                if entry.get() != &id {
                    debug!(
                        "Reference previously in {} being moved to {}: {:?}",
                        entry.get(),
                        id,
                        reference
                    );
                    *entry.get_mut() = id;
                    true
                } else {
                    debug!("Reference already in {}: {:?}", id, reference);
                    false
                }
            }
            Entry::Vacant(entry) => {
                // no existing
                entry.insert(id);
                true
            }
        };
        let unit = self.units.get_unit_mut(id)?;

        if do_insert {
            debug!("New reference added to {}: {:?}", id, reference);
            unit.refs.push(reference.clone());
        }
        Ok(())
    }

    fn merge_work_units(&mut self, id: UnitId, src_id: UnitId) -> Result<(), Error> {
        let _ = self.units.get_unit_mut(id)?;
        let src = self.units.get_unit_mut(src_id)?;
        debug!(
            "Merging {} into {}, and marking the former extinct",
            src_id, id
        );
        // mark as extinct
        src.extincted_by = Some(id);
        let refs_to_move: Vec<ProjectItemReference> = src.refs.drain(..).collect();
        for reference in refs_to_move {
            self.add_ref_to_unit_id(id, &reference)?;
        }
        debug!("Merging {} into {} done", src_id, id);
        Ok(())
    }

    /// Get a work unit by ID
    pub fn get_unit(&self, id: UnitId) -> Result<&WorkUnit, Error> {
        self.units.get_unit(id)
    }

    /// Get a work unit by ID, following extinction pointers
    pub fn get_unit_following_extinction(
        &self,
        id: UnitId,
        limit: usize,
    ) -> Result<(UnitId, &WorkUnit), Error> {
        let valid_id = self.units.follow_extinction(id, limit)?;
        Ok((valid_id, self.units.get_unit(valid_id)?))
    }

    /// Find the set of unit IDs corresponding to the refs, if any.
    fn get_ids_for_refs(&self, refs: &Vec<ProjectItemReference>) -> Vec<UnitId> {
        let mut units: Vec<UnitId> = vec![];
        let mut retrieved_ids: HashSet<UnitId> = Default::default();

        debug!(
            "Finding units for a collection of {} references",
            refs.len()
        );
        for reference in refs {
            if let Some(&id) = self.unit_by_ref.get(&reference) {
                debug!("Found id {} for: {:#?}", id, &reference);
                if retrieved_ids.insert(id) {
                    debug!("Adding {} to our return set", id);
                    units.push(id);
                }
            } else {
                debug!("Do not yet know {:#?}", &reference)
            }
        }
        debug!(
            "Found {} unique work unit IDs for the provided {} references",
            units.len(),
            refs.len()
        );
        units
    }
}
