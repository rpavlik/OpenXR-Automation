#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Ryan Pavlik <ryan.pavlik@collabora.com>


from dataclasses import dataclass
import os
import re
from typing import Dict, Optional, cast
import xml.etree.ElementTree as etree

import gitlab
import gitlab.v4.objects

find_mr = re.compile(
    r"Main extension MR:\s*(!|https://gitlab.khronos.org/openxr/openxr/-/merge_requests/)(?P<mrnum>[0-9]+)"
)


@dataclass
class ReleaseChecklistTemplate:
    """Fills in the "fields" of the release checklist template."""

    contents: str

    def __str__(self):
        return self.contents

    def fill_in_vendor(self, vendor_name: str):
        self.contents = self.contents.replace("(_vendor name_)", vendor_name, 1)

    def fill_in_champion(self, name: str, username: str):
        self.contents = self.contents.replace(
            "(_gitlab username_)", f"{name} @{username}", 1
        )

    def fill_in_mr(self, mr_num: int):
        self.contents = self.contents.replace("(_MR_)", f"!{mr_num}", 1)


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
            "NV",
            "PLUTO",
            "UNITY",
        }

    def is_runtime_vendor(self, vendor_code: str) -> bool:
        # Just a guess/heuristic
        return vendor_code in self.known and vendor_code not in self.not_runtime_vendors

    def get_vendor_name(self, vendor_code: str) -> Optional[str]:
        return self.known.get(vendor_code)


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
        self.registry_xml = LazyGitFile(
            "specification/registry/xr.xml", "main", gl_proj
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
    r"specification/sources/chapters/extensions/"
    r"(?P<vendor>[a-z]+)/(?P=vendor)_(?P<undecorated>[^.]+)[.]adoc"
)


def get_extension_names_for_diff(diff):
    names = set()
    for d in diff:
        if not d["new_file"]:
            continue
        m = EXT_ADOC_DECOMP.match(d["new_path"])
        if m:
            name = "XR_{}_{}".format(m.group("vendor").upper(), m.group("undecorated"))
            if name not in names:
                names.add(name)
                yield {
                    "vendor": m.group("vendor").upper(),
                    "undecorated": m.group("undecorated"),
                    "full_name": name,
                }


def get_extension_names_for_mr(mr: gitlab.v4.objects.ProjectMergeRequest):
    for c in mr.commits(all=True):
        c = cast(gitlab.v4.objects.ProjectCommit, c)
        yield from get_extension_names_for_diff(c.diff())


_KHR_EXT_LABEL = "KHR Extensions"
_VENDOR_EXT_LABEL = "Vendor_Extension"


def get_labels(vendor_id):
    if is_KHR_KHX(vendor_id):
        return [_KHR_EXT_LABEL]

    return [_VENDOR_EXT_LABEL]


@dataclass
class ChecklistData:
    ext_names: str
    vendor_id: str
    mr_num: int
    mr: gitlab.v4.objects.ProjectMergeRequest
    checklist_issue: Optional[gitlab.v4.objects.ProjectIssue] = None

    def make_issue_params(
        self, vendor_names: VendorNames, checklist_factory: ReleaseChecklistFactory
    ):

        vendor_name = vendor_names.get_vendor_name(self.vendor_id)
        if not vendor_name:
            raise RuntimeError(f"Could not find vendor {self.vendor_id}")

        template = checklist_factory.make_checklist_by_vendor(self.vendor_id)

        if vendor_names.is_runtime_vendor(self.vendor_id):
            template.fill_in_vendor(vendor_name)

        template.fill_in_mr(self.mr_num)
        template.fill_in_champion(self.mr.author["name"], self.mr.author["username"])

        return {
            "title": f"Release checklist for {self.ext_names}",
            "description": str(template),
            "assignee_ids": [self.mr.author["id"]],
            "labels": ["Release Checklist"] + get_labels(self.vendor_id),
        }

    @classmethod
    def lookup(
        cls,
        proj: gitlab.v4.objects.Project,
        mr_num,
        **kwargs,
    ) -> "ChecklistData":

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
            raise RuntimeError(f"got too many vendors for {ext_names} : {mr_num}")
        vendor_id = list(vendor_ids)[0]
        return ChecklistData(
            ext_names=ext_names, vendor_id=vendor_id, mr_num=mr_num, mr=mr
        )

    def handle_mr(
        self,
        proj,
        vendor_names: VendorNames,
        checklist_factory: ReleaseChecklistFactory,
    ):
        issue_params = self.make_issue_params(vendor_names, checklist_factory)
        issue = proj.issues.create(issue_params)
        self.issue = cast(gitlab.v4.objects.ProjectIssue, issue)
        # issue_data  = typing.cast(gitlab.v4.objects.ProjectIssue,  issue_data)
        issue_link = issue.attributes["references"]["full"]
        print(self.mr_num, issue_link)

        mr = proj.mergerequests.get(self.mr_num)
        message = (
            f"A release checklist for this extension has been opened at {issue_link}. "
            f"@{mr.author['username']} please update it to reflect the current state "
            "of this extension merge request and request review, if applicable."
        )
        mr.notes.create({"body": message})

        for label in get_labels(self.vendor_id):
            if label not in self.mr.labels:
                self.mr.labels.append(label)

        mr.description = f"Release checklist: {issue_link}\n\n" + mr.description
        mr.save()


def get_issues_to_mr(proj) -> Dict[int, int]:
    issue_to_mr = {}
    for issue in proj.issues.list(labels="Release Checklist", iterator=True):
        issue: gitlab.v4.objects.ProjectIssue
        match_iter = find_mr.finditer(issue.attributes["description"])
        m = next(match_iter, None)
        if not m:
            print("Release checklist has no MR indicated:", issue.attributes["web_url"])
            continue
        issue_to_mr[issue.get_id()] = int(m.group("mrnum"))
    return issue_to_mr


class ReleaseChecklistCollection:
    def __init__(self, proj, checklist_factory, vendor_names):
        self.proj = proj
        self.checklist_factory: ReleaseChecklistFactory = checklist_factory
        self.vendor_names: VendorNames = vendor_names
        self.issue_to_mr = get_issues_to_mr(proj)
        self.mr_to_issue = {mr: issue for issue, mr in self.issue_to_mr.items()}

    def handle_mr_if_needed(self, mr_num, **kwargs):
        if mr_num not in self.mr_to_issue:
            data = ChecklistData.lookup(self.proj, mr_num, **kwargs)
            data.handle_mr(self.proj, self.vendor_names, self.checklist_factory)
            issue_num = data.issue.iid
            self.mr_to_issue[mr_num] = issue_num
            self.issue_to_mr[issue_num] = mr_num
        else:
            print(mr_num, "already processed")


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

    proj = gl.projects.get("openxr/openxr")

    collection = ReleaseChecklistCollection(
        proj,
        checklist_factory=ReleaseChecklistFactory(proj),
        vendor_names=VendorNames(proj),
    )

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

    kwargs = {}
    if "extname" in args:
        kwargs["ext_names"] = [args.extname]
    if "vendorid" in args:
        kwargs["vendor_ids"] = args.vendorid
    for num in args.mr:
        collection.handle_mr_if_needed(num, **kwargs)
