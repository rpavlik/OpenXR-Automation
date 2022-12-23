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
}

mod gitlab_refs;
pub mod note;
mod project_mapper;
mod work_item_and_collection;

pub use gitlab_refs::{ProjectItemReference, ProjectReference};
