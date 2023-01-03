// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use std::{
    borrow::Borrow,
    collections::{hash_map::Entry, HashMap, HashSet},
    fmt::Display,
};

use gitlab::Project;
use log::{debug, info};
use typed_index_collections::TiVec;

use crate::{gitlab_refs::ProjectItemReference, Error};
use derive_more::{From, Into};

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
    // refs_set: HashSet<ProjectItemReference>,
    extincted_by: Option<UnitId>,
}

impl WorkUnit {
    pub fn new(projref: ProjectItemReference) -> Self {
        // let refs_set = HashSet::new();
        // refs_set.insert(projref);
        Self {
            refs: vec![projref],
            // refs_set,
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

    fn emplace(&mut self, reference: ProjectItemReference) -> UnitId {
        self.0.push_and_get_key(WorkUnit::new(reference))
    }

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
        let unit_ids = self.get_ids_for_refs(refs.iter());
        if let Some((&unit_id, remaining_unit_ids)) = unit_ids.split_first() {
            // we have at least one existing unit
            debug!("Will use work unit {}", unit_id);
            for src_id in remaining_unit_ids {
                debug!("Merging {} into {}", unit_id, src_id);
                self.merge_work_units(unit_id, *src_id)?;
            }
            for reference in refs {
                self.add_ref_to_unit_id(unit_id, &reference)?;
            }
            Ok(unit_id)
        } else {
            if let Some((first_ref, rest_of_refs)) = refs.split_first() {
                // we have some refs
                let unit_id = self.units.emplace(first_ref.clone());

                debug!("Created new work unit {}", unit_id);
                for reference in rest_of_refs {
                    self.add_ref_to_unit_id(unit_id, reference)?;
                }

                Ok(unit_id)
            } else {
                Err(Error::NoReferences)
            }
        }
    }

    fn add_ref_to_unit_id(
        &mut self,
        id: UnitId,
        reference: &ProjectItemReference,
    ) -> Result<(), Error> {
        // let mut do_insert = false;
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
        // self.unit_by_ref
        //     .entry(reference.clone())
        //     .and_modify(|id_in_map| {
        //         if id_in_map != &id {
        //             // ref is not in this unit
        //             unit.refs.push(reference.clone());
        //             *id_in_map = id;
        //         }
        //         // else the ref is already in this unit
        //     })
        //     .or_insert_with(|| {
        //         unit.refs.push(reference.clone());
        //         id
        //     });
        Ok(())

        // } else {
        //     None
        // }
    }

    fn merge_work_units(&mut self, id: UnitId, src_id: UnitId) -> Result<(), Error> {
        let _ = self.units.get_unit_mut(id)?;
        let src = self.units.get_unit_mut(src_id)?;
        // mark as extinct
        src.extincted_by = Some(id);
        let refs_to_move: Vec<ProjectItemReference> = src.refs.drain(..).collect();
        for reference in refs_to_move {
            self.add_ref_to_unit_id(id, &reference)?;
            // self.unit_by_ref.insert(reference.clone(), id);
            // main.refs.push(reference);
        }
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

    // pub fn try_get_unit(&self, id: UnitId) -> Option<&WorkUnit> {
    //     self.units.get(id)
    // }
    // pub fn try_get_unit_mut(&mut self, id: UnitId) -> Option<&mut WorkUnit> {
    //     self.units.get_mut(id)
    // }

    //     /// Find the unit ID corresponding to the ref, if any
    //     fn get_id_for_ref(&self, reference:  &ProjectItemReference) -> Option<UnitId> {
    // if let Some(&id) = self.unit_by_ref.get(&reference) {
    //     return Some(id)
    //                 if retrieved_ids.insert(id) {
    //                     units.push(id);
    //                 }
    //             }
    //     }

    /// Find the set of unit IDs corresponding to the refs, if any.
    fn get_ids_for_refs<'a, T: Iterator<Item = &'a ProjectItemReference>>(
        &self,
        refs: T,
    ) -> Vec<UnitId> {
        let mut units: Vec<UnitId> = vec![];
        let mut retrieved_ids: HashSet<UnitId> = Default::default();

        for projref in refs {
            if let Some(&id) = self.unit_by_ref.get(&projref) {
                if retrieved_ids.insert(id) {
                    units.push(id);
                }
            } else {
                debug!("Do not yet know {:#?}", &projref)
            }
        }
        units
    }
}
