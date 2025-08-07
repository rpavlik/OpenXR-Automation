import csv
import logging
import pprint
from typing import Generator, Optional, cast, Union
import gitlab.base
import gitlab.v4.objects
from gitlab.v4.objects import ProjectMergeRequest
from datetime import datetime
import zoneinfo

from .checklists import ReleaseChecklistCollection
from .priority_results import is_note_a_push
from .vendors import VendorNames
from .gitlab import OpenXRGitlab

# from .checklists import ReleaseChecklistCollection

# from .vendors import VendorNames


def _date_range_filter(
    gl_iter: gitlab.base.RESTObjectList,
    not_before: datetime,
    not_after: Optional[datetime] = None,
    attribute_name: str = "updated_at",
) -> Generator[gitlab.base.RESTObject]:
    log = logging.getLogger("_date_range_filter")
    for item in gl_iter:
        stamp = datetime.fromisoformat(item.attributes[attribute_name]).replace(
            tzinfo=zoneinfo.ZoneInfo("UTC")
        )

        if not_after is not None:
            if stamp > not_after:
                log.debug(
                    "Skipping, datestamp of %s is newer than not_after date of %s",
                    stamp.isoformat(),
                    not_after.isoformat(),
                )
                continue
        if stamp < not_before:
            log.info(
                "Ending iteration, reached %s which is earlier than our not_before date of %s",
                stamp.isoformat(),
                not_before.isoformat(),
            )
            return
        yield item


def _yield_merge_request_notes(
    mr: ProjectMergeRequest,
    include_users: list[str],
    not_before: datetime,
    not_after: Optional[datetime] = None,
):
    log = logging.getLogger("_yield_merge_request_notes")

    for n in _date_range_filter(
        cast(
            gitlab.base.RESTObjectList,
            mr.notes.list(order_by="updated_at", iterator=True),
        ),
        not_before=not_before,
        not_after=not_after,
    ):
        note = cast(gitlab.v4.objects.ProjectMergeRequestNote, n)
        user = note.attributes["author"]["username"]
        if note.attributes["author"]["username"] not in include_users:
            log.debug("Skipping note from user %s", user)
            continue
        yield note


# def _yield_merge_request_root_discussions(
#     mr: ProjectMergeRequest,
#     not_before: datetime,
#     not_after: Optional[datetime] = None,):
#     for n i
class MRActivity:
    """Information on selected activity for an MR."""

    def _process_note(
        self,
        note: Union[
            gitlab.v4.objects.ProjectMergeRequestNote,
            gitlab.v4.objects.ProjectMergeRequestDiscussionNote,
        ],
    ):
        note_id = note.attributes["id"]
        if note_id in self.known_note_ids:
            return False

        self.known_note_ids.add(note_id)
        if "position" in note.attributes:
            # This is an in-line comment/discussion
            self.inline_comments.append(note)
            return True

        if note.system:
            # this might be a push, or a notification of change.
            if is_note_a_push(note):
                self.pushes.append(note)
                return True
            # otherwise it's a "user changed this in version xyz" in an inline comment
            return False

        # this is just a comment
        self.other_comments.append(note)
        return True

    def __init__(
        self,
        mr: ProjectMergeRequest,
        include_users: list[str],
        not_before: datetime,
        not_after: Optional[datetime] = None,
        deep_discussions: bool = False,
    ):
        # include_users: list[str]
        # not_before: datetime,
        # not_after: Optional[datetime] = None,
        self.mr: ProjectMergeRequest = mr
        self._log = logging.getLogger(f"MRActivity({mr.title})")

        if not_after is None:
            self._log.info(
                "Retrieving activity since %s by %s",
                not_before.isoformat(),
                ", ".join(include_users),
            )
        else:

            self._log.info(
                "Retrieving activity between %s and %s by %s",
                not_before.isoformat(),
                not_after.isoformat(),
                ", ".join(include_users),
            )
            pass

        self.known_note_ids = set()
        self.pushes = []
        self.inline_comments = []
        self.other_comments = []
        self.other_discussion_notes = []
        for note in _yield_merge_request_notes(
            mr=self.mr,
            include_users=include_users,
            not_before=not_before,
            not_after=not_after,
        ):
            self.known_note_ids.add(note.get_id())
            if "position" in note.attributes:
                # This is an in-line comment/discussion
                self.inline_comments.append(note)
            elif note.system:
                # this might be a pushid': 502136, or a notification of change.
                if is_note_a_push(note):
                    self.pushes.append(note)
                # otherwise it's a "user changed this in version xyz" in an inline comment
            else:
                # this is just a comment
                self.other_comments.append(note)

        if not deep_discussions:
            return
        for root_disc in self.mr.discussions.list(iterator=True):
            # _date_range_filter(

            #     not_before=not_before,
            #     attribute_name="created_at",
            # ):
            disc = cast(gitlab.v4.objects.ProjectMergeRequestDiscussion, root_disc)
            if disc.attributes["individual_note"]:
                # Skip, we already got it earlier
                continue
            # disc.pprint()
            # fp.write(disc.pformat())
            # fp.write("\n")
            for note in disc.attributes["notes"]:
                if note["id"] in self.known_note_ids:
                    continue
                if note["author"]["username"] not in users:
                    continue
                full_disc_note = disc.notes.get(note["id"])
                if self._process_note(full_disc_note):
                    log.warning(
                        "Hey we found one via discussion we didn't know before!"
                    )
                    full_disc_note.pprint()
                    # if "position" in note:
                    #     log.warning(
                    #         "Found a discussion note with position we didn't see before, id %d",
                    #         note["id"],
                    #     )
                    # elif note["system"]:
                    #     pass
                    # else:
                    #     self.other_discussion_notes.append(disc.notes.get(note["id"]))


# pushes = [
#     cast(gitlab.v4.objects.ProjectMergeRequestNote, n)
#     for n in self.mr_notes
#     if is_note_a_push(cast(gitlab.v4.objects.ProjectMergeRequestNote, n))
# ]


users = ["rpavlik", "haagch", "safarimonkey"]
not_before = datetime(2024, 11, 1, tzinfo=zoneinfo.ZoneInfo("UTC"))


def do_one(mr_num, oxr_gitlab: OpenXRGitlab):
    mr: ProjectMergeRequest = oxr_gitlab.main_proj.mergerequests.get(mr_num)

    activity = MRActivity(mr, include_users=users, not_before=not_before)
    gitlab.v4.objects.ProjectMergeRequestDiscussionNoteManager
    mr.discussions.list(iterator=True)
    print(len(activity.inline_comments), "inline comments")
    print(len(activity.pushes), "pushes")
    print(len(activity.other_comments), "other comments")

    with open(f"other_comments.{mr_num}.txt", "w", encoding="utf-8") as fp:
        for comment in activity.other_comments:
            fp.write(comment.pformat())
            fp.write("\n")

    with open(f"inline_comments.{mr_num}.txt", "w", encoding="utf-8") as fp:
        for comment in activity.inline_comments:
            fp.write(comment.pformat())
            fp.write("\n")

    with open(f"discussions.{mr_num}.txt", "w", encoding="utf-8") as fp:
        for root_disc in mr.discussions.list(iterator=True):
            # _date_range_filter(

            #     not_before=not_before,
            #     attribute_name="created_at",
            # ):
            disc = cast(gitlab.v4.objects.ProjectMergeRequestDiscussion, root_disc)
            if disc.attributes["individual_note"]:
                # Skip, we already got it earlier
                continue
            disc.pprint()
            # fp.write(disc.pformat())
            # fp.write("\n")
            for note in disc.attributes["notes"]:
                if note["id"] in activity.known_note_ids:
                    continue
                if note["author"]["username"] not in users:
                    continue
                fp.write(pprint.pformat(note))
                fp.write("\n")


def process_all(oxr_gitlab):

    log.info("Performing startup queries")
    vendor_names = VendorNames.from_git(oxr_gitlab.main_proj)
    collection = ReleaseChecklistCollection(
        oxr_gitlab.main_proj,
        oxr_gitlab.operations_proj,
        checklist_factory=None,
        vendor_names=vendor_names,
    )

    try:
        collection.load_config("ops_issues.toml")
    except IOError:
        print("Could not load config")

    collection.load_initial_data()

    with open("stats2.csv", "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["URL", "Title", "inline_comments", "pushes", "other_comments"])
        for issue in collection.issue_to_mr.keys():
            issue_obj = collection.issue_str_to_cached_issue_object(issue)

            if not issue_obj:
                continue

            mr = oxr_gitlab.main_proj.mergerequests.get(collection.issue_to_mr[issue])
            activity = MRActivity(
                mr,
                include_users=users,
                not_before=not_before,
            )
            row = [
                issue_obj.attributes["web_url"],
                mr.attributes["title"],
                str(len(activity.inline_comments)),
                str(len(activity.pushes)),
                str(len(activity.other_comments)),
            ]
            writer.writerow(row)
            print(row)


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser()

    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG)

    log = logging.getLogger(__name__)

    oxr_gitlab = OpenXRGitlab.create()

    mr_num = 2963  # XR_META_body_tracking_calibration
    # not_before = datetime(2025, 7, 1, tzinfo=zoneinfo.ZoneInfo("UTC"))

    # do_one(mr_num, oxr_gitlab)
    process_all(oxr_gitlab)
