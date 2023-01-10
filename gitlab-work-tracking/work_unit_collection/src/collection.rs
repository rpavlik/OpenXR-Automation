// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use crate::{
    error::{
        ExtinctWorkUnitId, FollowExtinctionUnitIdError, GetUnitIdError, InsertError,
        InvalidWorkUnitId, NoReferencesError, RecursionLimitReached,
    },
    insert_outcome::{InsertOutcome, UnitCreated, UnitNotUpdated, UnitUpdated},
    UnitId, WorkUnit,
};
use log::{debug, warn};
use std::{
    borrow::Borrow,
    collections::{hash_map::Entry, HashMap, HashSet},
    fmt::Debug,
    hash::Hash,
};
use typed_index_collections::TiVec;

/// A container for "work units" that are ordered collections of unique "item references" (initial use case is GitLab project item references: issues and MRs).
/// Any given item reference can only belong to a single work unit, and each work unit has an ID.
/// To ensure there are not multiple references to a work unit, recommend normalizing the project item reference first.
#[derive(Debug, Default)]
pub struct WorkUnitCollection<R> {
    units: UnitContainer<R>,
    unit_by_ref: HashMap<R, UnitId>,
}

impl<R: Hash + Debug + Eq> WorkUnitCollection<R> {
    /// Records a work unit containing the provided references (must be non-empty).
    /// If any of those references already exist in the work collection, their corresponding work units are merged.
    /// Any references not yet in the work collection are added.
    pub fn add_or_get_unit_for_refs<'a>(
        &'a mut self,
        refs: impl IntoIterator<Item = &'a R>,
    ) -> Result<InsertOutcome, InsertError>
    where
        R: Clone,
    {
        let refs: Vec<&R> = refs.into_iter().collect();
        debug!("Given {} refs", refs.len());
        let unit_ids = self.get_ids_for_refs(refs.as_slice());
        if let Some((&unit_id, remaining_unit_ids)) = unit_ids.split_first() {
            // we have at least one existing unit
            debug!("Will use work unit {}", unit_id);

            let units_merged_in = remaining_unit_ids.len();
            for src_id in remaining_unit_ids {
                debug!("Merging {} into {}", unit_id, src_id);
                self.merge_work_units(unit_id, *src_id)?;
            }
            let refs_added = self.add_refs_to_unit_id(unit_id, refs.as_slice())?;
            if refs_added == 0 && units_merged_in == 0 {
                Ok(InsertOutcome::NotUpdated(UnitNotUpdated { unit_id }))
            } else {
                Ok(InsertOutcome::Updated(UnitUpdated {
                    unit_id,
                    refs_added,
                    units_merged_in,
                }))
            }
        } else if let Some((&first_ref, rest_of_refs)) = refs.split_first() {
            // we have some refs
            let unit_id = self.units.emplace(first_ref.clone());

            debug!("Created new work unit {}", unit_id);
            let refs_added = self.add_refs_to_unit_id(unit_id, rest_of_refs)?;

            Ok(InsertOutcome::Created(UnitCreated {
                unit_id,
                refs_added,
            }))
        } else {
            Err(NoReferencesError.into())
        }
    }

    /// Return value is number of refs added
    fn add_refs_to_unit_id<'a, T>(
        &mut self,
        unit_id: UnitId,
        refs: &'a [T],
    ) -> Result<usize, GetUnitIdError>
    where
        R: Clone,
        T: Hash + Eq + ToOwned + Debug,
        &'a T: CloneOrTake<R> + Borrow<R>,
    {
        let mut count: usize = 0;
        for reference in refs.iter() {
            if self.add_ref_to_unit_id(unit_id, reference)? {
                count += 1;
            }
        }
        Ok(count)
    }

    fn add_owned_refs_to_unit_id<'a, T>(
        &mut self,
        unit_id: UnitId,
        refs: impl IntoIterator<Item = T>,
    ) -> Result<usize, GetUnitIdError>
    where
        R: Clone,
        T: 'a + Hash + Eq + ToOwned + Debug + CloneOrTake<R> + Borrow<R>,
    {
        let mut count: usize = 0;
        for reference in refs.into_iter() {
            if self.add_ref_to_unit_id(unit_id, reference)? {
                count += 1;
            }
        }
        Ok(count)
    }

    /// Returns Ok(true) if a ref was added
    fn add_ref_to_unit_id<T>(&mut self, id: UnitId, reference: &T) -> Result<bool, GetUnitIdError>
    where
        R: Clone,
        T: Hash + Eq + ToOwned + Debug + CloneOrTake<R> + Borrow<R>,
    {
        debug!(
            "Trying to add a reference to {}: {:?}",
            id,
            reference.borrow()
        );
        let owned = R::clone(reference.borrow());
        let do_insert = match self.unit_by_ref.entry(R::clone(reference.borrow())) {
            Entry::Occupied(mut entry) => {
                if entry.get() != &id {
                    debug!(
                        "Reference previously in {} being moved to {}: {:?}",
                        entry.get(),
                        id,
                        reference.borrow()
                    );
                    *entry.get_mut() = id;
                    true
                } else {
                    debug!("Reference already in {}: {:?}", id, reference.borrow());
                    false
                }
            }
            Entry::Vacant(entry) => {
                // no existing
                entry.insert(id);
                true
            }
        };
        if do_insert {
            let unit = self.units.get_unit_mut(id)?;
            debug!("New reference added to {}: {:?}", id, reference.borrow());
            unit.add_ref(reference.clone_or_take());
        }
        Ok(do_insert)
    }

    fn merge_work_units(&mut self, id: UnitId, src_id: UnitId) -> Result<(), GetUnitIdError>
    where
        R: Borrow<R> + Clone + Debug + CloneOrTake<R> + Clone,
    {
        let src = self.units.get_unit_mut(src_id)?;
        debug!(
            "Merging {} into {}, and marking the former extinct",
            src_id, id
        );
        // mark as extinct, and add its refs to the other work unit
        let refs_to_move = src.extinct_by(id);
        for reference in refs_to_move {
            self.add_ref_to_unit_id(id, reference)?;
        }
        debug!("Merging {} into {} done", src_id, id);
        Ok(())
    }

    /// Get a work unit by ID
    pub fn get_unit(&self, id: UnitId) -> Result<&WorkUnit<R>, GetUnitIdError> {
        self.units.get_unit(id)
    }

    /// Folow extinction pointers to get the valid unit ID after all populating and merging is complete
    pub fn get_unit_id_following_extinction(
        &self,
        id: UnitId,
        limit: usize,
    ) -> Result<UnitId, FollowExtinctionUnitIdError> {
        self.units.follow_extinction(id, limit)
    }

    /// Find the set of unit IDs corresponding to the refs, if any.
    fn get_ids_for_refs<T>(&self, refs: &[&T]) -> Vec<UnitId>
    where
        R: Borrow<T> + Clone,
        T: Hash + Eq + ToOwned + Debug + CloneOrTake<R> + Clone + Borrow<R>,
    {
        let mut units: Vec<UnitId> = vec![];
        let mut retrieved_ids: HashSet<UnitId> = Default::default();

        debug!(
            "Finding units for a collection of {} references",
            refs.len()
        );
        for reference in refs.iter().map(|r| r) {
            if let Some(&id) = self.unit_by_ref.get(reference.borrow()) {
                debug!("Found id {} for: {:?}", id, reference);
                if retrieved_ids.insert(id) {
                    debug!("Adding {} to our return set", id);
                    units.push(id);
                }
            } else {
                debug!("Do not yet know {:?}", reference)
            }
        }
        debug!(
            "Found {} unique work unit IDs for the provided {} references",
            units.len(),
            refs.len()
        );
        units
    }

    pub fn len(&self) -> usize {
        self.units.len()
    }

    pub fn is_empty(&self) -> bool {
        self.units.is_empty()
    }
}

trait CloneOrTake<T> {
    fn clone_or_take(self) -> T;
}
impl<T> CloneOrTake<T> for T {
    fn clone_or_take(self) -> T {
        self
    }
}

impl<T: Clone> CloneOrTake<T> for &T {
    fn clone_or_take(self) -> T {
        Clone::clone(&self)
    }
}

trait AsRefCloneTake<T> {
    type Value;
    // fn ref_borrow(&self) -> &Self::Value;
    fn ref_clone(&self) -> Self::Value;
    fn ref_take(self) -> Self::Value;
}
impl<T> AsRefCloneTake<T> for &T
where
    T: Hash + Eq + Clone + Borrow<T>,
{
    type Value = T;
    // fn ref_borrow(&self) -> &R {
    //     self
    // }

    fn ref_clone(&self) -> T {
        Clone::clone(self)
    }

    fn ref_take(self) -> T {
        Clone::clone(self)
    }
}
impl<T> AsRefCloneTake<T> for T
where
    T: Hash + Eq + Clone + Borrow<T>,
{
    type Value = T;

    fn ref_clone(&self) -> Self::Value {
        Clone::clone(&self)
    }

    fn ref_take(self) -> Self::Value {
        self
    }
}

/// Internal newtype to provide utility functions over a TiVec<UnitId, WorkUnit>
/// `R` is your "ItemReference" type: e.g. for GitLab, it would be an enum that can refer
/// to an issue or merge request.
#[derive(Default)]
struct UnitContainer<R>(TiVec<UnitId, WorkUnit<R>>);

impl<R> Debug for UnitContainer<R>
where
    R: Debug,
{
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_tuple("UnitContainer").field(&self.0).finish()
    }
}
impl<R> UnitContainer<R> {
    /// Get a mutable work unit by ID
    fn get_unit_mut(&mut self, id: UnitId) -> Result<&mut WorkUnit<R>, GetUnitIdError> {
        let unit = self.0.get_mut(id).ok_or(InvalidWorkUnitId(id))?;
        if let Some(extincted_by) = &unit.extincted_by() {
            return Err(ExtinctWorkUnitId(id, *extincted_by).into());
        }
        Ok(unit)
    }

    /// Get a work unit by ID
    fn get_unit(&self, id: UnitId) -> Result<&WorkUnit<R>, GetUnitIdError> {
        let unit = self.0.get(id).ok_or(InvalidWorkUnitId(id))?;
        if let Some(extincted_by) = &unit.extincted_by() {
            return Err(ExtinctWorkUnitId(id, *extincted_by).into());
        }
        Ok(unit)
    }

    /// Create a new work unit from the given reference and return its id
    fn emplace(&mut self, reference: R) -> UnitId {
        self.0.push_and_get_key(WorkUnit::new(reference))
    }

    /// If the ID is extinct, follow the extincted-by field, repeatedly, at most `limit` steps.
    fn follow_extinction(
        &self,
        id: UnitId,
        limit: usize,
    ) -> Result<UnitId, FollowExtinctionUnitIdError> {
        let mut result_id = id;
        for _i in 0..limit {
            let unit = self.0.get(result_id).ok_or(InvalidWorkUnitId(id))?;
            match unit.extincted_by() {
                Some(successor) => {
                    warn!(
                        "Following extinction pointer: {} to {}",
                        &result_id, successor
                    );
                    result_id = successor;
                }
                None => return Ok(result_id),
            }
        }
        Err(RecursionLimitReached(id).into())
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use crate::{UnitId, WorkUnitCollection};

    #[test]
    fn test_collection() {
        let collection: WorkUnitCollection<i32> = Default::default();
        assert!(collection.get_unit(UnitId::from(1)).is_err());
    }
}
