// Copyright 2022-2023, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Rylie Pavlik <rylie.pavlik@collabora.com>

use crate::UnitId;

#[derive(Debug, thiserror::Error)]
#[error("No references provided to a WorkUnitCollection method that requires at least one.")]
pub struct NoReferencesError;

#[derive(Debug, thiserror::Error)]
#[error("Invalid work unit ID {0} - internal data structure error")]
pub struct InvalidWorkUnitId(pub(crate) UnitId);

#[derive(Debug, thiserror::Error)]
#[error("Recursion limit reached when resolving work unit ID {0}")]
pub struct RecursionLimitReached(pub(crate) UnitId);

#[derive(Debug, thiserror::Error)]
#[error("Extinct work unit ID {0}, extincted by {1} - internal data structure error")]
pub struct ExtinctWorkUnitId(pub(crate) UnitId, pub(crate) UnitId);

/// An error type when trying to follow extinction pointers:
/// might hit the limit, might hit an invalid ID, but won't error because of extinction.
#[derive(Debug, thiserror::Error)]
pub enum FollowExtinctionUnitIdError {
    #[error(transparent)]
    InvalidWorkUnitId(#[from] InvalidWorkUnitId),

    #[error(transparent)]
    RecursionLimitReached(#[from] RecursionLimitReached),
}

/// An error type when trying to get a work unit without following extinction pointers:
/// might hit an invalid ID, might hit an extinct ID.
#[derive(Debug, thiserror::Error)]
pub enum GetUnitIdError {
    #[error(transparent)]
    InvalidWorkUnitId(#[from] InvalidWorkUnitId),

    #[error(transparent)]
    ExtinctWorkUnitId(#[from] ExtinctWorkUnitId),
}

/// The union of the errors in `FollowExtinctionUnitIdError` and `GetUnitIdError`.
/// Try not to return this since it makes handling errors sensibly harder.
#[derive(Debug, thiserror::Error)]
pub enum GeneralUnitIdError {
    #[error(transparent)]
    InvalidWorkUnitId(#[from] InvalidWorkUnitId),

    #[error(transparent)]
    ExtinctWorkUnitId(#[from] ExtinctWorkUnitId),

    #[error(transparent)]
    RecursionLimitReached(#[from] RecursionLimitReached),
}

impl From<FollowExtinctionUnitIdError> for GeneralUnitIdError {
    fn from(err: FollowExtinctionUnitIdError) -> Self {
        match err {
            FollowExtinctionUnitIdError::InvalidWorkUnitId(err) => err.into(),
            FollowExtinctionUnitIdError::RecursionLimitReached(err) => err.into(),
        }
    }
}

impl From<GetUnitIdError> for GeneralUnitIdError {
    fn from(err: GetUnitIdError) -> Self {
        match err {
            GetUnitIdError::InvalidWorkUnitId(err) => err.into(),
            GetUnitIdError::ExtinctWorkUnitId(err) => err.into(),
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum InsertError {
    #[error(transparent)]
    NoReferences(#[from] NoReferencesError),

    #[error(transparent)]
    InvalidWorkUnitId(#[from] InvalidWorkUnitId),

    #[error(transparent)]
    ExtinctWorkUnitId(#[from] ExtinctWorkUnitId),
}

impl From<GetUnitIdError> for InsertError {
    fn from(err: GetUnitIdError) -> Self {
        match err {
            GetUnitIdError::InvalidWorkUnitId(e) => e.into(),
            GetUnitIdError::ExtinctWorkUnitId(e) => e.into(),
        }
    }
}

// impl From<GeneralUnitIdError> for Error {
//     fn from(err: GeneralUnitIdError) -> Self {
//         match err {
//             GeneralUnitIdError::InvalidWorkUnitId(err) => err.into(),
//             GeneralUnitIdError::ExtinctWorkUnitId(err) => err.into(),
//             GeneralUnitIdError::RecursionLimitReached(err) => err.into(),
//         }
//     }
// }

// impl From<FollowExtinctionUnitIdError> for Error {
//     fn from(err: FollowExtinctionUnitIdError) -> Self {
//         GeneralUnitIdError::from(err).into()
//     }
// }
