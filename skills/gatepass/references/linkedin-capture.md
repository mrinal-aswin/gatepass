# Capturing a LinkedIn profile as text

LinkedIn blocks anonymous fetching (HTTP 999 or an auth wall), so plain web fetches fail. In order of preference:

## 1. The user's own browser, already signed in (best)

Use Claude in Chrome (`mcp__claude-in-chrome__*`) when it is available. It runs with the user's own LinkedIn session. Open a **new tab** and read these pages with `get_page_text`, waiting about 3 seconds after each navigation because sections load lazily:

```
https://www.linkedin.com/in/<id>/                       headline, location, About, counts
https://www.linkedin.com/in/<id>/details/experience/
https://www.linkedin.com/in/<id>/details/skills/
https://www.linkedin.com/in/<id>/details/education/
https://www.linkedin.com/in/<id>/details/certifications/
https://www.linkedin.com/in/<id>/details/recommendations/
https://www.linkedin.com/in/<id>/recent-activity/all/         posts and comments
```

For the user's own profile, start at `https://www.linkedin.com/in/me/`: it redirects to the current URL, which matters after they claim a custom one. The main profile page often renders only the top card. The `details/` pages are reliable.
Batch all the navigations and reads in one `browser_batch` call. The About section loads lazily: if page text skips it, scroll and read it from the page's About section before recording "(none)". Close your tab when done.

Read only. Don't click Connect, Message, Endorse, Recommend or anything else that acts on the account.

**If Chrome reports "not connected":** call `list_connected_browsers`. An empty list means the extension
isn't linked to this session yet. Ask the user to open the Claude side panel in Chrome (same account as
this app), then retry once they confirm. It often registers only after that. Don't loop on retries.
If it stays empty, offer option 3 (attach a Save to PDF export).

**Lists can be truncated.** A `details/` page sometimes renders only the first items (skills especially), and
scrolling may not load more. Record what is visible with a note such as "(10 visible; may continue)", and
don't report items as removed when they may simply not have loaded. Flag them to the user to check instead.

## 2. The built-in browser pane

This only works if the user signs in there themselves. Never type their credentials.
Offer this option if Chrome isn't connected.

## 3. A file from the person

On any profile they can view (their own, or a connection's), the user can use **More → Save to PDF** and
**attach the PDF to the chat** (if it can't be read from where it sits, use the copy command from the
SKILL.md intake, step 2). Intake it with `intake <slug> linkedin <path>` after converting it to the
snapshot format below, so later diffs compare like with like.
This is the best option for a person who isn't a connection of the user.

## Snapshot format

Save one Markdown file per capture, keeping only the profile content. Drop the "More profiles for you" sidebar, the footer and the language list. Those blocks change on every visit and would make every diff noisy.

```markdown
# LinkedIn snapshot: <Name> (<YYYY-MM-DD>)
Source: linkedin.com/in/<id>

## Top card
Headline: ...
Location: ...
Current company: ...  | Education: ...
Connections: ...  | Followers: ...
Open to work: yes/no/unknown

## About
...

## Experience
### <Title> | <Company> | <Employment type>
<Start> - <End> | <Location> | <On-site/Hybrid/Remote>
<description, verbatim>
Skills: ...

## Skills
- <Skill> (endorsements / assessment badge, if shown)

## Education
## Certifications
## Recommendations (received)
## Activity
```

**Activity:** keep the 5 most recent items the person wrote themselves (posts and comments), each as
"<post|comment>, <age>: <first 15 words>". List reposts only as a count ("3 reposts"). The aim is what a
recruiter sees, without letting every visit change the diff.

Keep the section order and headings fixed. A stable format means `pipeline.py diff` shows only real changes.
