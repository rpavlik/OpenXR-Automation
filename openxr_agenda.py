#!/usr/bin/env python3
# Copyright 2022, Collabora, Ltd.
#
# SPDX-License-Identifier: BSL-1.0
#
# Author: Rylie Pavlik <rylie.pavlik@collabora.com>

import os
from datetime import datetime, timedelta
import gitlab
import gitlab.v4.objects
from dotenv import load_dotenv
from gitlab.v4.objects import ProjectIssue, ProjectMergeRequest

# make sure to create a .env file with the following
GL_USERNAME='GITLAB_USERNAME'
GL_ACCESS_TOKEN='PERSONAL_ACCECSS_TOKEN'
GL_URL='https://gitlab.khronos.org'
load_dotenv()

# Label Definitions
NEEDS_MEETING    = "Needs Meeting"
COMMENTS_RUNTIME = "Needs Comments - Runtime"
COMMENTS_ENGINE  = "Needs Comments - Engine"
RUNTIME_SPECIFIC = "Runtime Specific"
FROM_GITHUB      = "From GitHub"
VENDOR_EXTENSION = "Vendor_Extension"

# Defines to parse Gitlab
ISSUE     = "Issue"
MERGE     = "Merge"

# Formatting Definitions
SIMPLE = "SIMPLE"
COMBO  = "COMBO"

# Ignore Issues and Merges that have no activity within the specified time
STALE_THRESHOLD = datetime.now() - timedelta(days = 21)

# Set the structure for the different sections in the agenda
class engineComments:
   title  = "Needs Comments - Engine"
   type   = [ISSUE, MERGE]
   format = SIMPLE
   includeLabels = [COMMENTS_ENGINE]
   excludeLabels = [NEEDS_MEETING]

class runtimeComments:
   title  = "Needs Comments - Runtime"
   type   = [ISSUE, MERGE]
   format = SIMPLE
   includeLabels = [COMMENTS_RUNTIME]
   excludeLabels = [NEEDS_MEETING, COMMENTS_ENGINE]

class meetingMerges:
   title  = "Merge Requests"
   type   = [MERGE]
   format = MERGE
   includeLabels = [NEEDS_MEETING]
   excludeLabels = [VENDOR_EXTENSION]

class meetingIssues:
   title  = "Issues"
   type   = [ISSUE]
   format = ISSUE
   includeLabels = [NEEDS_MEETING]
   excludeLabels = [VENDOR_EXTENSION]

class fromGithub:
   title  = "From Github"
   type   = [ISSUE, MERGE]
   format = COMBO
   includeLabels = [FROM_GITHUB]
   excludeLabels = [RUNTIME_SPECIFIC]

class vendor:
   title  = "Vendor/EXT"
   type   = [ISSUE, MERGE]
   format = COMBO
   includeLabels = [NEEDS_MEETING, VENDOR_EXTENSION]
   excludeLabels = []

# fields that we care about from issue or merge
class parsedData:
   ref = []
   title = []
   author = []
   assignee = []
   thumbs = []
   labels = []
   updateDate = []
   createDate = []
   notes = []
   type = []

# returns the labeled list of issues and merges sorted by updated date
def get_labeled_issues_mrs(proj, labels):
   issues = proj.issues.list(state='opened', labels=labels, order_by='updated_at', get_all=True, updated_after=STALE_THRESHOLD)
   merges = proj.mergerequests.list(state='opened', labels=labels, order_by='updated_at', get_all=True, updated_after=STALE_THRESHOLD)

   return issues, mergess

# removes items with the specified labels
def remove_by_label(issues, excludelabel):
   to_remove = []
   cnt = 0
   for issue in issues:
      for label in issue.labels:
         for match in excludelabel:
            if(label == match):
               to_remove.append(cnt)

      cnt = cnt + 1

   new_issues = []
   for index, element in enumerate(issues):
      if index not in to_remove:
         new_issues.append(element)

   return new_issues

# puts data into strings so we can easily print to file
def parsedata(obj):
   ref = obj.references["short"]
   if(ref[0] == "#"): parsedData.type = "Issue"
   else: parsedData.type = "Merge"
   parsedData.ref = "[" + ref + "](" + obj.web_url + ")"
   parsedData.title = obj.title
   author = obj.author["name"]
   parsedData.author = "[" + author + "](" + obj.author["web_url"] + ")"
   try:
      assignee = obj.assignee["name"]
      parsedData.assignee = "[" + assignee + "](" + obj.assignee["web_url"] + ")"
   except:
      parsedData.assignee = "None"

   thumbs = obj.upvotes
   parsedData.thumbs = thumbs*":+1: "
   parsedData.labels = obj.labels
   if(type(parsedData.labels) == list): parsedData.labels = ",".join(parsedData.labels)
   parsedData.updateat = obj.updated_at[:10]
   parsedData.createat = obj.created_at[:10]
   parsedData.notes = "Add Meeting Notes"

   return parsedData

# prints the data to file
def mdprint(format, content, extras = None):
   # format for the needs comments
   if(format == SIMPLE):
      for obj in content:
         txt = parsedata(obj)
         print("- " + txt.ref + " - " + txt.title)
      # attach issues after merges
      if(extras != None):
         for obj in extras:
            txt = parsedata(obj)
            print("- " + txt.ref + " - " + txt.title)

   # format for github and vendor
   elif(format == COMBO):
      print("|Ref|Title|Type|Author|Assignee|Thumbs|Labels|Opened|Updated|Notes|")
      print("|---|-----|----|------|--------|------|------|------|-------|-----|")
      for obj in content:
         txt = parsedata(obj)
         print("|" + txt.ref + "|" + txt.title + "|" + txt.type + "|" + txt.author + "|" + txt.assignee + "|" + txt.thumbs + "|" + txt.labels + "|" + txt.createat + "|" + txt.updateat + "|" + txt.notes + "|")
      # attach issues after merges
      if(extras != None):
         for obj in extras:
            txt = parsedata(obj)
            print("|" + txt.ref + "|" + txt.title + "|" + txt.type + "|" + txt.author + "|" + txt.assignee + "|" + txt.thumbs + "|" + txt.labels + "|" + txt.createat + "|" + txt.updateat + "|" + txt.notes + "|")

   # format for meeting issues
   elif(format == ISSUE):
      print("|Ref|Title|Author|Assignee|Thumbs|Labels|Opened|Updated|Notes|")
      print("|---|-----|------|--------|------|------|------|-------|-----|")
      for obj in content:
         txt = parsedata(obj)
         print("|" + txt.ref + "|" + txt.title + "|" + txt.author + "|" + txt.assignee + "|" + txt.thumbs + "|" + txt.labels + "|" + txt.createat + "|" + txt.updateat + "|" + txt.notes + "|")

   # format for meeting merges
   elif(format == MERGE):
      print("|Ref|Title|Author|Assignee|Thumbs|Labels|Opened|Updated|Notes|")
      print("|---|-----|------|--------|------|------|------|-------|-----|")
      for obj in content:
         txt = parsedata(obj)
         print("|" + txt.ref + "|" + txt.title + "|" + txt.author + "|" + txt.assignee + "|" + txt.thumbs + "|" + txt.labels + "|" + txt.createat + "|" + txt.updateat + "|" + txt.notes + "|")

# takes a class and generates the agenda
def agenda_from_class(proj, myclass):
   issues = []
   merges = []
   for type in myclass.type:
      if(type == ISSUE):
         issues = proj.issues.list(state='opened', labels=myclass.includeLabels, order_by='updated_at', get_all=True, updated_after=STALE_THRESHOLD)
         issues = remove_by_label(issues, myclass.excludeLabels)
      elif(type == MERGE):
         merges = proj.mergerequests.list(state='opened', labels=myclass.includeLabels, order_by='updated_at', get_all=True, updated_after=STALE_THRESHOLD)
         merges = remove_by_label(merges, myclass.excludeLabels)

   print("\n## " + myclass.title)
   print()
   if((issues == []) and (merges == [])): # when both are blank we simply print "None"
      print("None")
   elif(issues == []): # add merges to agenda
      mdprint(myclass.format, merges)
   elif(merges == []): # add issues to agenda
      mdprint(myclass.format, issues)
   else: # add mrs first then issues
      mdprint(myclass.format, merges, issues)

# print using stdout >
def main():
    # connect to Gitlab
    gl = gitlab.Gitlab(
         url=os.environ["GL_URL"],
         private_token=os.environ["GL_ACCESS_TOKEN"]
    )
    gl.auth()
    proj = gl.projects.get("openxr/openxr")

    # process each class in the agenda order
    agenda_from_class(proj, engineComments)
    agenda_from_class(proj, runtimeComments)
    agenda_from_class(proj, meetingMerges)
    agenda_from_class(proj, meetingIssues)
    agenda_from_class(proj, fromGithub)
    agenda_from_class(proj, vendor)

if __name__ == "__main__":
    main()
