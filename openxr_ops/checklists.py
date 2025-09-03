# Copyright 2022-2025, Collabora, Ltd.
# Copyright 2024-2025, The Khronos Group Inc.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import itertools
import logging
import re
from dataclasses import dataclass
from functools import cached_property
from typing import Dict, Iterable, List, Optional, Set, cast

import gitlab
import gitlab.v4.objects
import tomllib

from .extensions import ExtensionNameGuesser
from .labels import ColumnName, GroupLabels, MainProjectLabels
from .vendors import VendorNames

_MAIN_MR_RE = re.compile(
    r"Main extension MR:\s*(openxr/openxr!|openxr!|!|https://gitlab.khronos.org/openxr/openxr/-/merge_requests/)(?P<mrnum>[0-9]+)"
)

_CHECKLIST_RE = re.compile(
    r"^(?P<line>Release [Cc]hecklist:([^\n]+))\n\n", re.MULTILINE
)

_log = logging.getLogger(__name__)


@dataclass
class ReleaseChecklistTemplate:
    """Fills in the "fields" of the release checklist template."""

    contents: str

    def __str__(self):
        return self.contents

    def fill_in_vendor(self, vendor_name: str):
        """Populate a vendor name."""
        self.contents = self.contents.replace("(_vendor name_)", vendor_name, 1)

    def fill_in_champion(self, name: str, username: str):
        """Populate an extension champion"""
        self.contents = self.contents.replace(
            "(_gitlab username_)", f"{name} @{username}", 1
        )

    def fill_in_mr(self, mr_num: int):
        """Populate the main merge request num."""
        self.contents = self.contents.replace("(_MR_)", f"openxr!{mr_num}", 1)


def is_KHR_KHX(vendor_code: str):
    return vendor_code in ("KHR", "KHX")


def is_EXT_EXTX(vendor_code: str):
    return vendor_code in ("EXT", "EXTX")


class ReleaseChecklistFactory:
    def __init__(self, gl_proj: gitlab.v4.objects.Project) -> None:
        self.proj = gl_proj

    @cached_property
    def vendor_tmpl(self):
        return (
            self.proj.files.get(
                ".gitlab/issue_templates/vendor_ext_release_checklist.md", "main"
            )
            .decode()
            .decode("utf-8")
        )

    @cached_property
    def ext_tmpl(self):
        return (
            self.proj.files.get(
                ".gitlab/issue_templates/EXT_release_checklist.md", "main"
            )
            .decode()
            .decode("utf-8")
        )

    @cached_property
    def khr_tmpl(self):
        return (
            self.proj.files.get(
                ".gitlab/issue_templates/KHR_release_checklist.md", "main"
            )
            .decode()
            .decode("utf-8")
        )

    def make_vendor_checklist(self):
        return ReleaseChecklistTemplate(str(self.vendor_tmpl))

    def make_ext_checklist(self):
        return ReleaseChecklistTemplate(str(self.ext_tmpl))

    def make_khr_checklist(self):
        return ReleaseChecklistTemplate(str(self.khr_tmpl))

    def make_checklist_by_vendor(self, vendor_id: str):
        if is_KHR_KHX(vendor_id):
            return self.make_khr_checklist()
        if is_EXT_EXTX(vendor_id):
            return self.make_ext_checklist()
        return self.make_vendor_checklist()


def get_extension_names_for_diff(guesser: ExtensionNameGuesser, diff):
    """Yield the extension names added in a git diff."""
    for diff_elt in diff:
        if not diff_elt["new_file"]:
            continue
        data = guesser.handle_path(diff_elt["new_path"])
        if data is not None:
            yield data


def get_extension_names_for_mr(mr: gitlab.v4.objects.ProjectMergeRequest):
    """Yield the unique extension names added in a merge request."""
    guesser = ExtensionNameGuesser()

    for commit in mr.commits():
        commit = cast(gitlab.v4.objects.ProjectCommit, commit)
        yield from get_extension_names_for_diff(guesser, commit.diff())


def get_labels(vendor_id):
    if is_KHR_KHX(vendor_id):
        return [
            MainProjectLabels.EXTENSION,
            GroupLabels.KHR_EXT,
        ]
    if is_EXT_EXTX(vendor_id):
        # multi-vendor
        return [MainProjectLabels.EXTENSION]
    return [
        MainProjectLabels.EXTENSION,
        GroupLabels.VENDOR_EXT,
        GroupLabels.OUTSIDE_IPR_FRAMEWORK,
    ]


@dataclass
class ChecklistData:
    ext_names: str
    vendor_id: str
    mr_num: int
    merge_request: gitlab.v4.objects.ProjectMergeRequest
    checklist_issue: Optional[gitlab.v4.objects.ProjectIssue] = None
    checklist_issue_ref: Optional[str] = None

    def make_issue_params(
        self, vendor_names: VendorNames, checklist_factory: ReleaseChecklistFactory
    ):
        """Produce the dict used for the checklist template"""

        vendor_name = vendor_names.get_vendor_name(self.vendor_id)
        if not vendor_name:
            raise RuntimeError(f"Could not find vendor {self.vendor_id}")

        template = checklist_factory.make_checklist_by_vendor(self.vendor_id)

        if vendor_names.is_runtime_vendor(self.vendor_id):
            template.fill_in_vendor(vendor_name)

        template.fill_in_mr(self.mr_num)
        template.fill_in_champion(
            self.merge_request.author["name"], self.merge_request.author["username"]
        )
        if not self.ext_names:
            raise RuntimeError("ext names not detected")
        return {
            "title": f"{self.ext_names}",
            "description": str(template),
            "assignee_ids": [self.merge_request.author["id"]],
            "labels": [ColumnName.INITIAL_DESIGN.value] + get_labels(self.vendor_id),
        }

    @classmethod
    def lookup(
        cls,
        proj: gitlab.v4.objects.Project,
        mr_num,
        **kwargs,
    ) -> "ChecklistData":
        """Create a ChecklistData based on a merge request number."""

        mr = proj.mergerequests.get(mr_num)

        ext_names = kwargs.get("ext_names")
        vendor_ids = kwargs.get("vendor_ids")
        if not ext_names or not vendor_ids:
            ext_name_data = list(get_extension_names_for_mr(mr))
            if not ext_names:
                ext_names = ", ".join(x.full_name for x in ext_name_data)
            if not vendor_ids:
                vendor_ids = {x.vendor for x in ext_name_data}

        if len(vendor_ids) != 1:
            _log.error(
                "wrong number of vendors for %s : %d : %s",
                ext_names,
                mr_num,
                str(vendor_ids),
            )
            raise RuntimeError(f"wrong number of vendors for {ext_names} : {mr_num}")
        vendor_id = list(vendor_ids)[0]
        return ChecklistData(
            ext_names=ext_names, vendor_id=vendor_id, mr_num=mr_num, merge_request=mr
        )

    def add_mr_labels(self):
        changed = False
        for label in get_labels(self.vendor_id):
            if label not in self.merge_request.labels:
                self.merge_request.labels.append(label)
                changed = True
        self.merge_request.save()
        return changed

    def handle_mr(
        self,
        ops_proj: gitlab.v4.objects.Project,
        vendor_names: VendorNames,
        checklist_factory: ReleaseChecklistFactory,
    ):
        """Create a release checklist issue for an MR."""
        issue_params = self.make_issue_params(vendor_names, checklist_factory)
        issue = ops_proj.issues.create(issue_params)
        self.checklist_issue = cast(gitlab.v4.objects.ProjectIssue, issue)
        # issue_data  = typing.cast(gitlab.v4.objects.ProjectIssue,  issue_data)
        issue_link = issue.attributes["references"]["full"]
        self.checklist_issue_ref = issue_link
        _log.info("%d: %s %s", self.mr_num, issue_link, issue.attributes["web_url"])

        may_or_must = "may also want to"
        reviews_suffix = ""
        if self.vendor_id == "KHR":
            may_or_must = "must"
            reviews_suffix = " as well as discussion in weekly calls"

        message = (
            f"A release checklist for this extension has been opened at {issue_link}. "
            f"@{self.merge_request.author['username']} please update it to reflect the "
            "current state of this extension merge request and request review, "
            "if applicable.\n\n"
            "You should also update the [OpenXR Operations Workboard]"
            "(https://gitlab.khronos.org/openxr/openxr-operations/-/boards) "
            "according to the status of your extension: most likely this means "
            "moving it to 'NeedsReview' once you complete the self-review steps in "
            "the checklist.\n\n"
            "See the [OpenXR Operations Readme]("
            "https://gitlab.khronos.org/openxr/openxr-operations/-/blob/main/README.md"
            ") for the flowchart showing the extension workboard process.\n\n"
            f"You {may_or_must} request feedback from other WG members through our "
            f"chat at <https://chat.khronos.org>{reviews_suffix}."
        )
        self.merge_request.notes.create({"body": message})

        self.merge_request.description = (
            f"Release checklist: {issue_link}\n\n{self.merge_request.description}"
        )
        self.add_mr_labels()


class ReleaseChecklistCollection:
    """The main object associating checklists and MRs."""

    def __init__(
        self,
        proj,
        ops_proj,
        checklist_factory: Optional[ReleaseChecklistFactory],
        vendor_names,
        data: Optional[dict] = None,
    ):
        self.proj: gitlab.v4.objects.Project = proj
        """Main project"""
        self.ops_proj: gitlab.v4.objects.Project = ops_proj
        """Operations project containing (some) release checklists"""
        self.checklist_factory: Optional[ReleaseChecklistFactory] = checklist_factory
        self.vendor_names: VendorNames = vendor_names

        self.issue_to_mr: Dict[str, int] = {}
        self.mr_to_issue_object: Dict[int, gitlab.v4.objects.ProjectIssue] = {}
        self.mr_to_issue: Dict[int, str] = {}
        self.ignore_issues: Set[str] = set()
        self.include_issues: List[int] = []

    def load_config(self, fn: str):
        with open(fn, "rb") as fp:
            config = tomllib.load(fp)

            for ignore in config.get("ignore", []):
                if isinstance(ignore, str):
                    self.ignore_issues.add(ignore)
                else:
                    self.ignore_issues.add(f"openxr/openxr-operations#{ignore}")

            for include in config.get("include", []):
                self.include_issues.append(include)

    def _handle_issue(self, issue: gitlab.v4.objects.ProjectIssue):
        issue_ref = issue.attributes["references"]["full"]

        if issue_ref in self.ignore_issues:
            # skip
            return

        if issue_ref in self.issue_to_mr:
            # we already processed this
            return

        desc = issue.attributes["description"]
        if not desc:
            _log.warning(
                "Operations issue has no description: %s %s",
                issue.attributes["title"],
                issue.attributes["web_url"],
            )
            return
        match_iter = _MAIN_MR_RE.finditer(issue.attributes["description"])
        match = next(match_iter, None)
        if not match:
            _log.info(
                "Release checklist has no MR indicated: %s <%s>",
                issue.attributes["title"],
                issue.attributes["web_url"],
            )
            return

        mr_num = int(match.group("mrnum"))
        self.issue_to_mr[issue_ref] = mr_num
        self.mr_to_issue_object[mr_num] = issue
        self.mr_to_issue[mr_num] = issue_ref

    def load_initial_data(self, deep: bool = False):

        _log.info("Parsing all opened release checklists...")

        queries = [
            self.proj.issues.list(
                labels="Release Checklist", state="opened", iterator=True
            ),
            self.ops_proj.issues.list(state="opened", iterator=True),
        ]

        if deep:
            queries.append(
                self.ops_proj.issues.list(
                    state="closed",
                    label=ColumnName.RELEASE_PENDING.value,
                    iterator=True,
                ),
            )

        for issue in itertools.chain(*queries):
            issue = cast(gitlab.v4.objects.ProjectIssue, issue)
            self._handle_issue(issue)

        if self.include_issues:
            _log.info("Parsing explicitly included release checklists...")

            for issue_num in self.include_issues:
                self._handle_issue(self.ops_proj.issues.get(issue_num))

        _log.info(
            "Loaded %d release checklists with associated MR", len(self.issue_to_mr)
        )

    def issue_str_to_cached_issue_object(
        self, issue_ref: str
    ) -> Optional[gitlab.v4.objects.ProjectIssue]:
        mr = self.issue_to_mr.get(issue_ref)
        if mr is None:
            return None
        return self.mr_to_issue_object[mr]

    def mr_has_checklist(self, mr_num):
        """Return true if the MR already has a checklist."""
        return mr_num in self.mr_to_issue

    def handle_mr_if_needed(self, mr_num, **kwargs) -> None:
        """Create a release checklist issue if one is not already created for this MR."""
        if mr_num in self.mr_to_issue:
            _log.info("MR number %d is already processed", mr_num)
            return

        data = ChecklistData.lookup(self.proj, mr_num, **kwargs)
        if not self.checklist_factory:
            raise RuntimeError("Cannot handle this MR without a checklist factory")
        data.handle_mr(self.ops_proj, self.vendor_names, self.checklist_factory)
        assert data.checklist_issue
        issue_ref = data.checklist_issue.attributes["references"]["full"]
        self.mr_to_issue[mr_num] = issue_ref
        self.issue_to_mr[issue_ref] = mr_num

    def update_mr_labels(self) -> None:
        """Update the labels on the merge requests if needed."""
        _log.info("Checking open extension MRs to verify their labels")
        for mr_num, issue in self.mr_to_issue_object.items():
            merge_request: gitlab.v4.objects.ProjectMergeRequest = (
                self.proj.mergerequests.get(mr_num)
            )
            if merge_request.state != "opened":
                # only touch open MRs
                continue

            made_change = False
            for label in (GroupLabels.KHR_EXT, GroupLabels.VENDOR_EXT):
                if label in issue.labels and label not in merge_request.labels:
                    merge_request.labels.append(label)
                    made_change = True
            try:
                data = ChecklistData.lookup(self.proj, mr_num)
                if data.add_mr_labels():
                    made_change = True
            except RuntimeError as e:
                _log.warning("ugh got an error: %s", e)
            if made_change:
                _log.info("Updating labels on MR %d", mr_num)
                merge_request.save()

    def update_mr_descriptions(self) -> None:
        """Prepend the release checklist link to all MRs that need it."""
        _log.info("Checking open extension MRs to verify they link to their checklist")
        for issue_ref, mr_num in self.issue_to_mr.items():
            merge_request: gitlab.v4.objects.ProjectMergeRequest = (
                self.proj.mergerequests.get(mr_num)
            )
            if merge_request.state != "opened":
                # only touch open MRs
                continue

            new_front = f"Release checklist: {issue_ref}"
            prepend = f"{new_front}\n\n"
            if merge_request.description.strip() == new_front:
                # minimal MR desc
                continue
            match = _CHECKLIST_RE.search(merge_request.description)
            if not match:
                url = merge_request.attributes["web_url"]
                _log.info(f"MR does not mention its issue: {url}")
                if merge_request.attributes["state"] not in ("closed", "merged"):
                    _log.info("Updating it")
                    merge_request.description = prepend + merge_request.description
                    _log.info(merge_request.description)
                    merge_request.save()
            else:
                new_desc = (
                    prepend
                    + _CHECKLIST_RE.sub("", merge_request.description, 1).strip()
                )

                if not match.group("line").startswith(new_front):
                    _log.info(f"Updating MR {merge_request.get_id()} description")

                    merge_request.description = new_desc
                    merge_request.save()

    def mr_set_column(
        self,
        mr_num: int,
        new_column: ColumnName,
        add_labels: Optional[Iterable[str]] = None,
        remove_labels: Optional[Iterable[str]] = None,
    ) -> None:
        issue = self.mr_to_issue_object[mr_num]
        labels = set(issue.attributes["labels"])
        orig_column = ColumnName.from_labels(labels)
        if orig_column is None:
            orig_column = ColumnName.INITIAL_DESIGN

        if orig_column == new_column:
            _log.warning("Issue %s is already in '%s'", issue.web_url, str(orig_column))

        new_labels: set[str] = set(new_column.compute_new_labels(labels))
        if add_labels:
            new_labels.update(add_labels)
        if remove_labels:
            new_labels.difference_update(remove_labels)

        if new_labels != labels:
            title = issue.attributes["title"]

            _log.info(
                f"Updating labels: {issue.references['short']} aka <{issue.web_url}>: {title}: {repr(new_labels)}",
            )
            issue.labels = list(new_labels)
            issue.save()
