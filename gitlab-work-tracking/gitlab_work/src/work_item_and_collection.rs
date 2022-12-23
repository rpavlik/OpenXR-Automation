// Copyright 2022, Collabora, Ltd.
//
// SPDX-License-Identifier: BSL-1.0
//
// Author: Ryan Pavlik <ryan.pavlik@collabora.com>

pub enum ProjectRef {
    Issue(String, i32),
    MergeRequest(String, i32),
}

struct WorkUnit {}
