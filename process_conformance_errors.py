#!/usr/bin/env python3
# Copyright 2022-2023, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>

from dataclasses import dataclass
import os
from typing import Any, Dict, List, Optional, cast
import json

import gitlab
import gitlab.v4.objects

RUNTIME_LABEL_COLOR = "#36454f"
RUNTIME_LABEL_PREFIX = "runtime"


@dataclass
class Runtime:
    slug: str
    name: str
    contact_username: Optional[str] = None
    contact_user_id: Optional[int] = None

    @classmethod
    def from_json_key_value(cls, key: str, value_obj: Dict[str, Any]):
        user: Optional[str] = None
        maybe_user = value_obj.get("contact")
        name: str = value_obj["name"]
        if maybe_user and str(maybe_user).startswith("@"):
            # strip the @
            user = maybe_user[1:]
        return cls(slug=key, name=name, contact_username=user)

    @property
    def label_name(self) -> str:
        return f"{RUNTIME_LABEL_PREFIX}:{self.slug}"

    @property
    def label_description(self) -> str:
        common = f"Issues for the {self.name} runtime"
        if self.contact_username:
            return f"{common}: contact person @{self.contact_username}"
        return f"{common}: no known contact person"

    def find_contact_user_id(self, proj: gitlab.v4.objects.Project) -> int:
        if self.contact_user_id is not None:
            return self.contact_user_id
        if self.contact_username is None:
            raise RuntimeError("Cannot look up a null contact user")

        search_result = proj.users.list(search=self.contact_username, all=True)
        if not search_result:
            raise RuntimeError(f"Could not find {self.contact_username} in the project")

        self.contact_user_id = search_result[0].attributes["id"]  # type: ignore

        print(f"Looked up {self.contact_username}: {self.contact_user_id}")
        return self.contact_user_id


def populate_contact_user_ids(proj: gitlab.v4.objects.Project, runtimes: List[Runtime]):
    print("Iterating through runtimes to populate user ID")
    known_users: Dict[str, int] = {}
    for runtime in runtimes:
        if not runtime.contact_username:
            # no contact
            continue
        if runtime.contact_user_id:
            # already know user ID
            continue
        user_id = known_users.get(runtime.contact_username)
        if user_id is not None:
            runtime.contact_user_id = user_id
            continue
        user_id = runtime.find_contact_user_id(proj)
        known_users[runtime.contact_username] = user_id


def parse_runtimes(filename: str) -> List[Runtime]:
    with open(filename, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    return [Runtime.from_json_key_value(k, v) for k, v in data.items()]


def create_or_update_runtime_label(
    proj: gitlab.v4.objects.Project,
    runtime: Runtime,
    existing_label: Optional[gitlab.v4.objects.ProjectLabel],
):
    label_name = runtime.label_name
    if existing_label:
        # See if the existing label needs updating
        needs_save = False

        if existing_label.color != RUNTIME_LABEL_COLOR:
            print(f"Updating {label_name} color")
            existing_label.color = RUNTIME_LABEL_COLOR
            needs_save = True

        if existing_label.description != runtime.label_description:
            print(f"Updating {label_name} description")
            existing_label.description = runtime.label_description
            needs_save = True

        if needs_save:
            print(f"Saving {label_name} updates")
            existing_label.save()
        else:
            print(f"Label {label_name} needs no changes")

        return

    # Label does not exist yet: create it!
    print(f"Creating {label_name}")
    proj.labels.create(
        {
            "name": label_name,
            "color": RUNTIME_LABEL_COLOR,
            "description": runtime.label_description,
        }
    )


def update_runtime_labels(proj: gitlab.v4.objects.Project, runtimes: List[Runtime]):
    known_labels: Dict[str, gitlab.v4.objects.ProjectLabel] = {
        cast(str, label.name): cast(gitlab.v4.objects.ProjectLabel, label)
        for label in proj.labels.list(iterator=True)
    }

    for runtime in runtimes:
        label_name = runtime.label_name
        create_or_update_runtime_label(proj, runtime, known_labels.get(label_name))


def assign_contact_person(proj: gitlab.v4.objects.Project, runtimes: List[Runtime]):
    runtimes_by_label = {r.label_name: r for r in runtimes}

    for issue in proj.issues.list(state="opened", iterator=True):
        issue = cast(gitlab.v4.objects.ProjectIssue, issue)
        runtime_label = [
            label
            for label in issue.labels
            if cast(str, label).startswith(RUNTIME_LABEL_PREFIX)
        ]

        if not runtime_label:
            print(f"Warning: no runtime label on issue {issue.web_url}")
            continue

        runtime_label = runtime_label[0]
        runtime = runtimes_by_label.get(runtime_label)

        if not runtime:
            print(
                f"Warning: runtime label on issue {issue.web_url} does not match any "
                f"known runtime: out of date data file? {runtime_label}"
            )
            continue

        if not issue.assignees:
            # Default to the contact person
            if runtime.contact_username and runtime.contact_user_id:
                print(f"Assigning to {runtime.contact_username}: issue {issue.web_url}")
                issue.save(assignee_ids=[runtime.contact_user_id])

            else:
                print(
                    f"Cannot assign: no contact person for runtime {runtime.name} "
                    f"- reported issue {issue.web_url}"
                )


def main(proj: gitlab.v4.objects.Project, runtimes_filename: str):
    runtimes = parse_runtimes(runtimes_filename)
    update_runtime_labels(proj, runtimes)
    populate_contact_user_ids(proj, runtimes)
    assign_contact_person(proj, runtimes)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )
    proj = gl.projects.get("openxr/openxr-conformance-errors")

    main(proj, "runtimes.json")
