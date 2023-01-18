// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab_work_units::UnitId;
use nullboard_tools::{GenericList, GenericNote, List, ListCollection, Note};
use workboard_update::{line_or_reference::ProcessedNote, GetWorkUnit};

#[derive(Debug)]
pub enum BoardOperation {
    NoOp,
    AddNote {
        list_name: String,
        note: ProcessedNote,
    },
    MoveNote {
        current_list_name: String,
        new_list_name: String,
        work_unit_id: UnitId,
    },
}
impl Default for BoardOperation {
    fn default() -> Self {
        Self::NoOp
    }
}

impl BoardOperation {
    pub fn apply(
        self,
        lists: &mut impl ListCollection<List = GenericList<ProcessedNote>>,
    ) -> Result<(), anyhow::Error> {
        match self {
            BoardOperation::NoOp => Ok(()),
            BoardOperation::AddNote { list_name, note } => {
                let list = lists
                    .named_list_mut(&list_name)
                    .ok_or_else(|| anyhow::anyhow!("Could not find list {}", &list_name))?;
                list.notes_mut().push(GenericNote::new(note));
                Ok(())
            }
            BoardOperation::MoveNote {
                current_list_name,
                new_list_name,
                work_unit_id,
            } => {
                let note = {
                    let current_list =
                        lists.named_list_mut(&current_list_name).ok_or_else(|| {
                            anyhow::anyhow!("Could not find current list {}", &current_list_name)
                        })?;
                    let needle = current_list
                        .notes_mut()
                        .iter()
                        .position(|n| n.data().work_unit_id() == &Some(work_unit_id))
                        .ok_or_else(|| {
                            anyhow::anyhow!(
                                "Could not find note with matching work unit id {}",
                                work_unit_id
                            )
                        })?;
                    current_list.notes_mut().remove(needle)
                };
                let new_list = lists
                    .named_list_mut(&new_list_name)
                    .ok_or_else(|| anyhow::anyhow!("Could not find new list {}", &new_list_name))?;
                new_list.notes_mut().push(note);
                Ok(())
            }
        }
    }
}
