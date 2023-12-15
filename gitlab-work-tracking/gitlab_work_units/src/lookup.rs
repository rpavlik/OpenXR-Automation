// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Rylie Pavlik <rylie.pavlik@collabora.com>

use crate::{BaseGitLabItemReference, Error, ProjectItemReference};
use gitlab::api::{common::NameOrId, Query};
use serde::Deserialize;
use std::collections::{hash_map::Entry, HashMap};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum ItemState {
    Closed,
    Merged,
    Locked,
    Opened,
}

impl ItemState {
    pub fn to_state_annotation(&self) -> Option<&'static str> {
        match self {
            ItemState::Closed => Some("[CLOSED] "),
            ItemState::Merged => Some("[MERGED] "),
            ItemState::Locked => Some("[LOCKED] "),
            _ => None,
        }
    }
}

impl From<gitlab::IssueState> for ItemState {
    fn from(value: gitlab::IssueState) -> Self {
        match value {
            gitlab::IssueState::Opened => ItemState::Opened,
            gitlab::IssueState::Closed => ItemState::Closed,
            gitlab::IssueState::Reopened => ItemState::Opened,
        }
    }
}

impl From<gitlab::MergeRequestState> for ItemState {
    fn from(value: gitlab::MergeRequestState) -> Self {
        match value {
            gitlab::MergeRequestState::Opened => ItemState::Opened,
            gitlab::MergeRequestState::Closed => ItemState::Closed,
            gitlab::MergeRequestState::Reopened => ItemState::Opened,
            gitlab::MergeRequestState::Merged => ItemState::Merged,
            gitlab::MergeRequestState::Locked => ItemState::Locked,
        }
    }
}

#[derive(Debug, Deserialize, Clone)]
struct InternalResults<T: Into<ItemState>> {
    state: T,
    web_url: String,
    title: String,
}

#[derive(Debug, Clone)]
pub struct ItemResults {
    state: ItemState,
    state_annotation: Option<&'static str>,
    web_url: String,
    title: String,
}

impl ItemResults {
    pub fn state(&self) -> ItemState {
        self.state
    }

    pub fn state_annotation(&self) -> Option<&str> {
        self.state_annotation
    }

    pub fn web_url(&self) -> &str {
        self.web_url.as_ref()
    }

    pub fn title(&self) -> &str {
        self.title.as_ref()
    }
}

impl<T: Into<ItemState>> From<InternalResults<T>> for ItemResults {
    fn from(value: InternalResults<T>) -> Self {
        let state: ItemState = value.state.into();
        let state_annotation = state.to_state_annotation();
        Self {
            state,
            state_annotation,
            web_url: value.web_url,
            title: value.title,
        }
    }
}

#[derive(Debug, Default)]
pub struct GitlabQueryCache {
    cache: HashMap<ProjectItemReference, ItemResults>,
    queries: u16,
    cache_hits: u16,
}

impl GitlabQueryCache {
    pub fn cache_stats(&self) -> (u16, u16) {
        (self.cache_hits, self.queries)
    }

    pub fn query(
        &mut self,
        client: &gitlab::Gitlab,
        reference: &ProjectItemReference,
    ) -> Result<ItemResults, Error> {
        self.queries += 1;
        match self.cache.entry(reference.clone()) {
            Entry::Occupied(e) => {
                self.cache_hits += 1;
                Ok(e.get().clone())
            }
            Entry::Vacant(e) => {
                let proj: NameOrId = reference.project().try_into()?;

                let query_result: Result<_, _> = match reference {
                    ProjectItemReference::Issue(issue) => {
                        let endpoint = gitlab::api::projects::issues::Issue::builder()
                            .project(proj)
                            .issue(issue.raw_iid())
                            .build()?;
                        let query_result: Result<InternalResults<gitlab::IssueState>, _> =
                            endpoint.query(client);
                        query_result.map(ItemResults::from)
                    }
                    ProjectItemReference::MergeRequest(mr) => {
                        let endpoint =
                            gitlab::api::projects::merge_requests::MergeRequest::builder()
                                .project(proj)
                                .merge_request(mr.raw_iid())
                                .build()?;

                        let query_result: Result<InternalResults<gitlab::MergeRequestState>, _> =
                            endpoint.query(client);
                        query_result.map(ItemResults::from)
                    }
                };
                let query_result =
                    query_result.map_err(|e| Error::ItemQueryError(reference.to_string(), e))?;

                e.insert(query_result.clone());
                Ok(query_result)
            }
        }
    }
}
