#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>


from dataclasses import dataclass
import itertools
import os
import re
from typing import Dict, Optional, cast
import xml.etree.ElementTree as etree

import gitlab
import gitlab.v4.objects

_MAIN_MR_RE = re.compile(
    r"Main extension MR:\s*(openxr!|!|https://gitlab.khronos.org/openxr/openxr/-/merge_requests/)(?P<mrnum>[0-9]+)"
)

_CHECKLIST_RE = re.compile(r"^Release [Cc]hecklist:([^\n]+)$", re.MULTILINE)


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


class LazyGitFile:
    def __init__(self, path, ref, gl_proj: gitlab.v4.objects.Project):
        self._contents: Optional[str] = None
        self._path = path
        self._ref = ref
        self._proj = gl_proj

    def __str__(self):
        if not self._contents:
            pf = self._proj.files.get(self._path, self._ref)
            self._contents = pf.decode().decode("utf-8")
        return self._contents


def is_KHR_KHX(vendor_code: str):
    return vendor_code in ("KHR", "KHX")


def is_EXT_EXTX(vendor_code: str):
    return vendor_code in ("EXT", "EXTX")


class VendorNames:
    """Data structure storing vendor/author codes to vendor names."""

    def __init__(self, gl_proj: gitlab.v4.objects.Project, ref="main") -> None:
        pf = gl_proj.files.get("specification/registry/xr.xml", ref)
        self._contents = pf.decode().decode("utf-8")
        self.root = etree.fromstring(self._contents)
        self.known = {}
        for tag in self.root.findall("tags/tag"):
            self.known[tag.get("name")] = tag.get("author")
        self.known.update(
            {
                "FB": "Meta Platforms",
                "META": "Meta Platforms",
                "OCULUS": "Meta Platforms",
                # "QCOM": "Qualcomm",
                # "EPIC": "Epic Games",
                # "ML": "Magic Leap",
                # "VARJO": "Varjo",
                # "HTC": "HTC",
                "EXT": "Multi-vendor",
                "KHR": "The Khronos Group",
            }
        )
        # Author tags that are not runtime vendors
        self.not_runtime_vendors = {
            "ALMALENCE",
            "ARM",
            "EPIC",
            "EXT",
            "EXTX",
            "FREDEMMOTT",
            "INTEL",
            "KHR",
            "NV",
            "PLUTO",
            "UNITY",
        }

    def is_runtime_vendor(self, vendor_code: str) -> bool:
        """Guess if a vendor/author is a runtime vendor."""
        # Just a guess/heuristic
        return vendor_code in self.known and vendor_code not in self.not_runtime_vendors

    def get_vendor_name(self, vendor_code: str) -> Optional[str]:
        """Get the vendor's name from their author code, if possible."""
        name = self.known.get(vendor_code)
        if not name and vendor_code.endswith("X"):
            name = self.known.get(vendor_code[:-1])
        return name


class ReleaseChecklistFactory:
    def __init__(self, gl_proj: gitlab.v4.objects.Project) -> None:
        self.vendor_tmpl = LazyGitFile(
            ".gitlab/issue_templates/vendor_ext_release_checklist.md", "main", gl_proj
        )
        self.ext_tmpl = LazyGitFile(
            ".gitlab/issue_templates/EXT_release_checklist.md", "main", gl_proj
        )
        self.khr_tmpl = LazyGitFile(
            ".gitlab/issue_templates/KHR_release_checklist.md", "main", gl_proj
        )
        self.proj = gl_proj

    def make_vendor_checklist(self):
        return ReleaseChecklistTemplate(str(self.vendor_tmpl))

    def make_ext_checklist(self):
        return ReleaseChecklistTemplate(str(self.ext_tmpl))

    def make_khr_checklist(self):
        return ReleaseChecklistTemplate(str(self.khr_tmpl))

    def make_checklist_by_vendor(self, vendor_id: str):
        if vendor_id == "KHR":
            return self.make_khr_checklist()
        if vendor_id in ("EXT", "EXTX"):
            return self.make_ext_checklist()
        return self.make_vendor_checklist()


EXT_ADOC_DECOMP = re.compile(
    r"""specification/sources/chapters/extensions/
    (?P<vendor>[a-z]+)/ # vendor directory
    (?P=vendor)_(?P<undecorated>[^.]+)[.]adoc""",  # filename in two parts
    re.VERBOSE,
)


def get_extension_names_for_diff(diff):
    """Yield the extension names added in a git diff."""
    names = set()
    for diff_elt in diff:
        if not diff_elt["new_file"]:
            continue
        path_match = EXT_ADOC_DECOMP.match(diff_elt["new_path"])
        if path_match:
            vendor = path_match.group("vendor").upper()
            undecorated = path_match.group("undecorated")
            name = f"XR_{vendor}_{undecorated}"
            if name not in names:
                names.add(name)
                yield {
                    "vendor": vendor,
                    "undecorated": undecorated,
                    "full_name": name,
                }


def get_extension_names_for_mr(mr: gitlab.v4.objects.ProjectMergeRequest):
    """Yield the unique extension names added in a merge request."""
    yielded = set()
    for commit in mr.commits():
        commit = cast(gitlab.v4.objects.ProjectCommit, commit)
        for ext in get_extension_names_for_diff(commit.diff()):
            if ext["full_name"] not in yielded:
                yielded.add(ext["full_name"])
                yield ext


KHR_EXT_LABEL = "KHR_Extension"
VENDOR_EXT_LABEL = "Vendor_Extension"


def get_labels(vendor_id):
    if is_KHR_KHX(vendor_id):
        return [KHR_EXT_LABEL]

    return [VENDOR_EXT_LABEL]


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
            "labels": ["status:InitialComposition"] + get_labels(self.vendor_id),
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
                ext_names = ", ".join(x["full_name"] for x in ext_name_data)
            if not vendor_ids:
                vendor_ids = {x["vendor"] for x in ext_name_data}

        if len(vendor_ids) != 1:
            print(vendor_ids)
            raise RuntimeError(f"wrong number of vendors for {ext_names} : {mr_num}")
        vendor_id = list(vendor_ids)[0]
        return ChecklistData(
            ext_names=ext_names, vendor_id=vendor_id, mr_num=mr_num, merge_request=mr
        )

    def handle_mr(
        self,
        proj: gitlab.v4.objects.Project,
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
        print(self.mr_num, issue_link, issue.attributes["web_url"])

        may_or_must = "may also want to"
        reviews_suffix = ""
        if self.vendor_id == "KHR":
            may_or_must = "must"
            reviews_suffix = " as well as discussion in weekly calls"

        merge_request = proj.mergerequests.get(self.mr_num)
        message = (
            f"A release checklist for this extension has been opened at {issue_link}. "
            f"@{merge_request.author['username']} please update it to reflect the "
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
        merge_request.notes.create({"body": message})

        for label in get_labels(self.vendor_id):
            if label not in self.merge_request.labels:
                self.merge_request.labels.append(label)

        merge_request.description = (
            f"Release checklist: {issue_link}\n\n" + merge_request.description
        )
        merge_request.save()


def get_issues_to_mr(
    proj: gitlab.v4.objects.Project, ops_proj: gitlab.v4.objects.Project
) -> Dict[str, int]:
    issue_to_mr = {}
    for issue in itertools.chain(
        proj.issues.list(labels="Release Checklist", iterator=True),
        ops_proj.issues.list(iterator=True),
    ):
        issue = cast(gitlab.v4.objects.ProjectIssue, issue)
        match_iter = _MAIN_MR_RE.finditer(issue.attributes["description"])
        match = next(match_iter, None)
        if not match:
            print("Release checklist has no MR indicated:", issue.attributes["web_url"])
            continue
        issue_to_mr[issue.attributes["references"]["full"]] = int(match.group("mrnum"))
    return issue_to_mr


class ReleaseChecklistCollection:
    """The main object associating checklists and MRs."""

    def __init__(self, proj, ops_proj, checklist_factory, vendor_names):
        self.proj = proj
        """Main project"""
        self.ops_proj = ops_proj
        """Operations project containing (some) release checklists"""
        self.checklist_factory: ReleaseChecklistFactory = checklist_factory
        self.vendor_names: VendorNames = vendor_names
        self.issue_to_mr: Dict[str, int] = get_issues_to_mr(proj, ops_proj)
        self.mr_to_issue: Dict[int, str] = {
            mr: issue for issue, mr in self.issue_to_mr.items()
        }

    def mr_has_checklist(self, mr_num):
        """Return true if the MR already has a checklist."""
        return mr_num in self.mr_to_issue

    def handle_mr_if_needed(self, mr_num, **kwargs):
        """Create a release checklist issue if one is not already created for this MR."""
        if mr_num not in self.mr_to_issue:
            data = ChecklistData.lookup(self.proj, mr_num, **kwargs)
            data.handle_mr(
                self.proj, self.ops_proj, self.vendor_names, self.checklist_factory
            )
            assert data.checklist_issue
            issue_ref = data.checklist_issue.attributes["references"]["full"]
            self.mr_to_issue[mr_num] = issue_ref
            self.issue_to_mr[issue_ref] = mr_num
        else:
            print(mr_num, "already processed")

    def update_mr_desc(self):
        for issue_ref, mr_num in self.issue_to_mr.items():
            merge_request: gitlab.v4.objects.ProjectMergeRequest = (
                self.proj.mergerequests.get(mr_num)
            )
            new_front = f"Release checklist: {issue_ref}"
            prepend = f"{new_front}\n\n"
            if merge_request.description == new_front:
                # minimal MR desc
                continue
            matches = _CHECKLIST_RE.findall(merge_request.description)
            if not matches:
                url = merge_request.attributes["web_url"]
                print(f"MR does not mention its issue: {url}")
                if merge_request.attributes["state"] not in ("closed", "merged"):
                    print("Updating it")
                    merge_request.description = prepend + merge_request.description
                    print(merge_request.description)
                    merge_request.save()
            else:
                if not matches[0].startswith(new_front):
                    print(f"Updating MR {merge_request.get_id()} description")
                    merge_request.description = _CHECKLIST_RE.sub(
                        prepend, merge_request.description, 1
                    )
                    merge_request.save()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mr",
        type=int,
        nargs="+",
        help="MR number to generate an extension checklist for",
    )
    parser.add_argument(
        "--extname", type=str, help="Manually specify the extension name"
    )
    parser.add_argument(
        "-i", "--vendorid", type=str, action="append", help="Specify the vendor ID"
    )

    args = parser.parse_args()

    gl = gitlab.Gitlab(
        url=os.environ["GL_URL"], private_token=os.environ["GL_ACCESS_TOKEN"]
    )

    main_proj = gl.projects.get("openxr/openxr")
    operations_proj = gl.projects.get("openxr/openxr-operations")

    print("Performing startup queries")
    collection = ReleaseChecklistCollection(
        main_proj,
        operations_proj,
        checklist_factory=ReleaseChecklistFactory(operations_proj),
        vendor_names=VendorNames(main_proj),
    )
    # from pprint import pprint

    # pprint(collection.issue_to_mr)
    # pprint(collection.mr_to_issue)
    # collection.handle_mr_if_needed(2208)
    # collection.handle_mr_if_needed(2288)
    # collection.handle_mr_if_needed(2299)
    # collection.handle_mr_if_needed(2312)
    # collection.handle_mr_if_needed(2313)
    # collection.handle_mr_if_needed(2329)
    # collection.handle_mr_if_needed(2331)
    # collection.handle_mr_if_needed(2332)
    # collection.handle_mr_if_needed(2334)
    # collection.handle_mr_if_needed(2336)
    # collection.handle_mr_if_needed(2339)
    # collection.handle_mr_if_needed(2344)
    # collection.handle_mr_if_needed(2347)
    # collection.handle_mr_if_needed(2349)
    # collection.handle_mr_if_needed(2344)
    # collection.handle_mr_if_needed(2385)
    # collection.handle_mr_if_needed(2377)
    # collection.handle_mr_if_needed(2407)
    # collection.handle_mr_if_needed(2138)
    # collection.handle_mr_if_needed(2410)
    # collection.handle_mr_if_needed(2555)
    # collection.update_mr_desc()

    kwargs = {}
    if "extname" in args and args.extname:
        kwargs["ext_names"] = [args.extname]
    if "vendorid" in args and args.vendorid:
        kwargs["vendor_ids"] = args.vendorid
    for num in args.mr:
        collection.handle_mr_if_needed(num, **kwargs)
