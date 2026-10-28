# Future features

Ideas the owner wants to come back to. Not started unless marked.

## Mission requests from GitHub issues

**Status:** proposed 2026-10-27, not set up.

Open an issue describing a mission, and Claude builds it and opens a pull request.

### How it would work

1. The owner opens an issue (e.g. "Night SEAD mission for the F-16 near Maykop") and labels it `mission-request` or mentions `@claude`.
2. A GitHub Action runs Claude Code on GitHub's servers. Claude reads the issue, writes `missions/<id>/mission.yaml`, checks the geography, renders everything into `hangar/`, runs the tests and opens a **pull request**.
3. The owner reviews the briefing and director pages on the PR branch and comments to ask for changes (Claude replies and updates the PR). Merging the PR puts the mission into the hangar.

### Setup

- Run `/install-github-app` in Claude Code. It installs the Claude GitHub app on `CGelet/DCS_Missions` and adds the API key or subscription token as a repo secret.
- `.github/workflows/claude.yml`: the Action. Before Claude runs it installs uv, `requirements.txt` and Playwright Chromium, so the renders match local builds (kneeboard PNGs included).
- `.github/ISSUE_TEMPLATE/mission-request.yml`, with fields for aircraft, theater area, mission type, the story idea, and where it falls in the campaign (date).
- Promote `CLAUDE_DEV.md` to `CLAUDE.md`. The Action reads `CLAUDE.md` automatically, and that's how it learns the repo rules: no spoilers in pilot outputs, check geography, rebuild everything, byte-reproducible builds.

### Decisions to make first

- **PRs instead of pushing to master.** Today Claude commits full renders straight to master. For changes nobody is watching, a PR the owner merges is safer. Claude still does the rendering, just on GitHub.
- **Who can trigger it.** The repo is public, so anyone can open an issue. Keep the Action's default: only users with write access can trigger it. That also stops a stranger's issue text from steering Claude.
- **Cost.** Each request is a full Claude run, roughly what one mission build costs in a terminal session.

### Alternatives considered

- A scheduled cloud agent (`/schedule`) that checks issues, say, daily. It works without the owner's machine, but has a delay and isn't tied to issue events.
- `/loop` in a local Claude Code session, which only watches while the terminal is open.

### Variant the owner prefers (discussed 2026-10-28)

A **daily scheduled** Action instead of an instant one. The owner's choices: open a PR rather than push, and pay with the Claude subscription.
- **Trigger:** `.github/workflows/claude-issues.yml` with `schedule: cron "0 6 * * *"` plus `workflow_dispatch`, and `concurrency` so runs never overlap.
- **Auth:** `anthropics/claude-code-action@v1` with `claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}`. The token comes from running `claude setup-token` locally.
- **Which issues:** it picks up to 3 open issues labelled `claude` that have no open `claude/issue-<n>` PR. Only people with triage access can add labels, so the label is the gate; a scheduled run doesn't check who opened the issue.
- **What Claude does for each issue:**
  - Branch, make the change, rebuild everything and run the tests.
  - Restore kneeboard PNGs for missions the issue didn't touch, because runner fonts differ from local ones.
  - Run `gh pr create` with "Closes #n" and comment the link on the issue.
  - If the issue is unclear or breaks a repo rule, ask in a comment instead of guessing.
- **Repo settings:** allow Actions to create PRs, install the Claude GitHub app, and create the `claude` and `claude-working` labels.
- **Doc changes:** in CLAUDE_DEV.md, note that the "push to master" rule is for local sessions only; CI opens PRs.

### First test

Once it's set up, run one real mission request end to end and check the PR's renders against a local build.
