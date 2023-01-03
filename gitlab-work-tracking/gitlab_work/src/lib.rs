// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab::{
    api::{projects::ProjectBuilderError, ApiError, RestClient},
    Gitlab,
};

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("Could not parse string to GitLab ref")]
    RefParseError,

    #[error("Problem looking up project")]
    ProjectBuilder(#[from] ProjectBuilderError),

    #[error("API call error when querying project {0}: {1}")]
    ProjectQueryError(String, #[source] ApiError<<Gitlab as RestClient>::Error>),

    #[error("Invalid work unit ID {0} - internal data structure error")]
    InvalidWorkUnitId(UnitId),

    #[error("Extinct work unit ID {0}, extincted by {1} - internal data structure error")]
    ExtinctWorkUnitId(UnitId, UnitId),

    #[error("No references passed, at least one required")]
    NoReferences,
}

mod gitlab_refs;
pub mod note;
mod project_mapper;
mod work_item_and_collection;

pub use gitlab_refs::{ProjectItemReference, ProjectReference};
use work_item_and_collection::UnitId;
