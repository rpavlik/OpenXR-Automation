// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

use gitlab::{
    api::{
        projects::{
            issues::IssueBuilderError, merge_requests::MergeRequestBuilderError,
            ProjectBuilderError,
        },
        ApiError, RestClient,
    },
    Gitlab,
};
use refs::UnknownProjectError;
use work_unit_and_collection::{FollowExtinctionUnitIdError, GeneralUnitIdError, GetUnitIdError};

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("Could not parse string to GitLab ref")]
    RefParseError,

    #[error("Problem preparing project query endpoint")]
    ProjectBuilder(#[from] ProjectBuilderError),

    #[error("Problem preparing issue query endpoint")]
    IssueBuilder(#[from] IssueBuilderError),

    #[error("Problem preparing merge request query endpoint")]
    MergeRequestBuilder(#[from] MergeRequestBuilderError),

    #[error("API call error when querying project {0}: {1}")]
    ProjectQueryError(String, #[source] ApiError<<Gitlab as RestClient>::Error>),

    #[error("API call error when querying item {0}: {1}")]
    ItemQueryError(String, #[source] ApiError<<Gitlab as RestClient>::Error>),

    #[error("No references passed, at least one required")]
    NoReferences,

    #[error("Somehow we managed to not populate the project reference - internal error. {0}")]
    UnknownProject(#[from] UnknownProjectError),

    #[error(transparent)]
    InvalidWorkUnitId(#[from] work_unit_and_collection::InvalidWorkUnitId),

    #[error(transparent)]
    ExtinctWorkUnitId(#[from] work_unit_and_collection::ExtinctWorkUnitId),

    #[error(transparent)]
    RecursionLimitReached(#[from] work_unit_and_collection::RecursionLimitReached),
}

impl From<GeneralUnitIdError> for Error {
    fn from(err: GeneralUnitIdError) -> Self {
        match err {
            GeneralUnitIdError::InvalidWorkUnitId(err) => err.into(),
            GeneralUnitIdError::ExtinctWorkUnitId(err) => err.into(),
            GeneralUnitIdError::RecursionLimitReached(err) => err.into(),
        }
    }
}

impl From<GetUnitIdError> for Error {
    fn from(err: GetUnitIdError) -> Self {
        GeneralUnitIdError::from(err).into()
    }
}

impl From<FollowExtinctionUnitIdError> for Error {
    fn from(err: FollowExtinctionUnitIdError) -> Self {
        GeneralUnitIdError::from(err).into()
    }
}

pub mod lookup;
mod project_mapper;
mod refs;
pub mod regex;
mod work_unit_and_collection;

pub use project_mapper::{GitLabItemReferenceNormalize, ProjectMapper};
pub use refs::{
    find_refs, format_reference, BaseGitLabItemReference, Issue, MergeRequest,
    ProjectItemReference, ProjectReference, TypedGitLabItemReference, ISSUE_SYMBOL, MR_SYMBOL,
};
pub use work_unit_and_collection::{
    RefAddOutcome, UnitCreated, UnitId, UnitNotUpdated, UnitUpdated, WorkUnitCollection,
};
